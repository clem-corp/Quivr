import asyncio
import os
from functools import lru_cache
from typing import AsyncIterable, Awaitable, Callable

from auth.auth_bearer import AuthBearer, get_current_user
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain.callbacks import AsyncIteratorCallbackHandler
from langchain.chains import ConversationalRetrievalChain
from langchain.chains.llm import LLMChain
from langchain.chains.question_answering import load_qa_chain
from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from llm.prompt.CONDENSE_PROMPT import CONDENSE_QUESTION_PROMPT
from logger import get_logger
from models.chats import ChatMessage
from models.settings import CommonsDep, common_dependencies
from models.users import User
from supabase import create_client
from utils.users import fetch_user_id_from_credentials
from vectorstore.supabase import CustomSupabaseVectorStore

logger = get_logger(__name__)

stream_router = APIRouter()

openai_api_key = os.getenv("OPENAI_API_KEY")
supabase_url = os.getenv("SUPABASE_URL")
supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")


async def send_message(
    chat_message: ChatMessage, chain, callback
) -> AsyncIterable[str]:
    async def wrap_done(fn: Awaitable, event: asyncio.Event):
        """Wrap an awaitable with a event to signal when it's done or an exception is raised."""
        try:
            resp = await fn
            logger.debug("Done: %s", resp)
        except Exception as e:
            logger.error(f"Caught exception: {e}")
        finally:
            # Signal the aiter to stop.
            event.set()

    # Use the agenerate method (Supported for models not chains)
    task = asyncio.create_task(
        wrap_done(
            chain.acall(
                {
                    "question": chat_message.question,
                    "chat_history": chat_message.history,
                }
            ),
            callback.done,
        )
    )

    # Use the aiter method of the callback to stream the response with server-sent-events
    async for token in callback.aiter():
        logger.info("Token: %s", token)
        yield f"data: {token}\n\n"

    await task


def create_qa(commons: CommonsDep, current_user: User):
    user_id = fetch_user_id_from_credentials(commons, {"email": current_user.email})

    embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)

    supabase_client = create_client(supabase_url, supabase_service_key)

    vector_store = CustomSupabaseVectorStore(
        supabase_client, embeddings, table_name="vectors", user_id=user_id
    )

    generator_llm = ChatOpenAI(
        temperature=0,
    )

    # Callback provides the on_llm_new_token method
    callback = AsyncIteratorCallbackHandler()

    streaming_llm = ChatOpenAI(
        temperature=0,
        streaming=True,
        callbacks=[callback],
    )
    question_generator = LLMChain(
        llm=generator_llm,
        prompt=CONDENSE_QUESTION_PROMPT,
    )
    doc_chain = load_qa_chain(
        llm=streaming_llm,
        chain_type="stuff",
    )

    return (
        ConversationalRetrievalChain(
            combine_docs_chain=doc_chain,
            question_generator=question_generator,
            retriever=vector_store.as_retriever(),
            verbose=True,
        ),
        callback,
    )


@stream_router.post("/stream", dependencies=[Depends(AuthBearer())], tags=["Stream"])
async def stream(
    chat_message: ChatMessage,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    commons = common_dependencies()

    qa, callback = create_qa(commons, current_user)

    return StreamingResponse(
        send_message(chat_message, qa, callback),
        media_type="text/event-stream",
    )
