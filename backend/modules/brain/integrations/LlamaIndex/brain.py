import os
import json
import time
from typing import AsyncIterable
from uuid import UUID

from langchain_core.messages.ai import AIMessage
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.system import SystemMessage
from llama_index.core import (
    Settings,
    VectorStoreIndex,
    SimpleDirectoryReader,
    load_index_from_storage,
    StorageContext,
)

# from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.core.chat_engine.types import ChatMode
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.core.node_parser import MarkdownElementNodeParser
from llama_index.core.prompts import PromptTemplate, PromptType

# from llama_index.core.ingestion import (
#     DocstoreStrategy,
#     IngestionCache,
#     IngestionPipeline,
# )
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.postprocessor.flag_embedding_reranker import FlagEmbeddingReranker

# from llama_index.readers.google import GoogleDriveReader
# from llama_index.storage.kvstore.redis import RedisKVStore as RedisCache
# from llama_index.storage.docstore.redis import RedisDocumentStore
# from llama_index.vector_stores.redis import RedisVectorStore

from modules.brain.knowledge_brain_qa import KnowledgeBrainQA
from modules.chat.dto.chats import ChatQuestion

current_directory = os.path.dirname(os.path.abspath(__file__))
data_directory = os.path.join(current_directory, "luccid-data/Documents")
folder_name = "Serbia"

embed_model = OpenAIEmbedding(model="text-embedding-3-small")
llm = OpenAI(model="gpt-4-turbo-preview")

Settings.llm = llm
Settings.embed_model = embed_model


class LlamaIndexBrain(KnowledgeBrainQA):
    """This is a first implementation of LlamaIndex recursive retriever RAG class. it is a KnowledgeBrainQA has the data is stored locally.
    It is going to call the Data Store internally to get the data.

    Args:
        KnowledgeBrainQA (_type_): A brain that store the knowledge internaly
    """

    def __init__(
        self,
        **kwargs,
    ):
        super().__init__(
            **kwargs,
        )

        # self._vector_store = RedisVectorStore(
        #     index_name="redis_vectore_store",
        #     index_prefix="vector_store",
        #     redis_url="redis://redis:6379",
        # )
        # self._ingestion_cache = IngestionCache(
        #     cache=RedisCache.from_host_and_port("redis", 6379),
        #     collection="redis_cache",
        # )
        # self._ingestion_pipeline = IngestionPipeline(
        #     transformations=[
        #         MarkdownElementNodeParser(),
        #         embed_model,
        #     ],
        #     docstore=RedisDocumentStore.from_host_and_port(
        #         "localhost", 6379, namespace="document_store"
        #     ),
        #     vector_store=self._vector_store,
        #     cache=self._ingestion_cache,
        #     docstore_strategy=DocstoreStrategy.UPSERTS,
        # )
        # self._index = VectorStoreIndex.from_vector_store(
        #     self._vector_store, embed_model=embed_model
        # )
        print("####### Starting loading index from storage... #######")
        start_time = time.time()  # Record the start time

        try:
            self._storage_context = StorageContext.from_defaults(
                persist_dir=os.path.join(data_directory, folder_name, "index-data")
            )
            self._index = load_index_from_storage(
                storage_context=self._storage_context, index_id="vector_index"
            )
        except ValueError as e:
            print(e)
            self._index = None
            raise e
        except FileNotFoundError as e:
            print(e)
            self._index = None
            raise e

        end_time = time.time()  # Record the end time
        elapsed_time = end_time - start_time  # Calculate elapsed time
        print(
            f"####### Finishing loading index from storage... in {elapsed_time:.2f} seconds #######"
        )
        self._reranker = FlagEmbeddingReranker(
            top_n=7, model="BAAI/bge-reranker-large", use_fp16=True
        )

    @classmethod
    def _load_data(cls, folder_name: str, recursive: bool = False):
        # credentials_path = os.path.join(
        #     current_directory, "luccid-app-llamaindex-google-readers.json"
        # )
        # print(f"####### PG ####### credentials_path: {credentials_path}")
        # loader = GoogleDriveReader(credentials_path=credentials_path)
        # docs = loader.load_data(
        #     folder_id=folder_id,
        #     query_string="name contains 'corrected.md'",
        #     # TODO(pg): do a PR to add recursive to the GDrive loader
        #     # recursive=recursive
        # )
        # for doc in docs:
        #     doc.id_ = doc.metadata["file_name"]
        reader = SimpleDirectoryReader(
            input_dir=os.path.join(data_directory, folder_name)
        )
        docs = reader.load_data()

        return docs

    @classmethod
    def _parse_nodes(cls, folder_name, docs):
        node_parser = MarkdownElementNodeParser(llm=llm)
        nodes = node_parser.get_nodes_from_documents(docs)
        base_nodes, objects = node_parser.get_nodes_and_objects(nodes)
        index = VectorStoreIndex(nodes=base_nodes + objects)
        index.set_index_id("vector_index")
        index.storage_context.persist(
            os.path.join(data_directory, folder_name, "index-data")
        )
        print(f"Ingested {len(nodes)} Nodes")

    def _get_engine(self):
        if not self._index:
            print("### No index found...")
            return None

        DEFAULT_TEXT_QA_PROMPT_TMPL = (
            "Context information is below.\n"
            "---------------------\n"
            "{context_str}\n"
            "---------------------\n"
            "You are an experienced Serbian architect specializing in Serbian building codes, regulations, and norms. You will answer in Professional architectural Serbian Latin Language. Keep your answers short and always deliver only what was asked. Always quote the specific regulation name, paragraph, or norm depending on the case. You should use professional language and have a deep understanding of the relevant Serbian laws and guidelines in the field of architecture and construction. Be as descriptive as possible. Always make sure to provide 100% correct information. When responding, avoid giving personal opinions or advice that goes beyond the scope of Serbian regulations. In cases of conflicting information, use the most recent regulation by the date of being published. Your responses should be clear, concise, and tailored to the level of understanding of the user, ensuring they receive the most relevant and accurate information. Always answer in Serbian Latin. Your goal is to help architects with building regulations so they don't get rejected by the building inspectorate. Always do your best. If information is unavailable on a queried topic, respond with: “Na žalost, na ovo pitanje nemam odgovor"
            "Query: {query_str}\n"
            "Answer: "
        )
        DEFAULT_TEXT_QA_PROMPT = PromptTemplate(
            DEFAULT_TEXT_QA_PROMPT_TMPL, prompt_type=PromptType.QUESTION_ANSWER
        )

        return self._index.as_chat_engine(
            chat_mode=ChatMode.CONTEXT,
            similarity_top_k=10,
            node_postprocessors=[self._reranker],
            text_qa_template=DEFAULT_TEXT_QA_PROMPT,
            stream=True,
            verbose=True,
        )
        # return self._index.as_query_engine(
        #     text_qa_template=DEFAULT_TEXT_QA_PROMPT, stream=True, verbose=True
        # )

    def _format_chat_history(self, chat_history):
        return [
            ChatMessage(
                role=(
                    MessageRole.USER
                    if isinstance(message, HumanMessage)
                    else (
                        MessageRole.ASSISTANT
                        if isinstance(message, AIMessage)
                        else (
                            MessageRole.SYSTEM
                            if isinstance(message, SystemMessage)
                            else MessageRole.MODEL
                        )
                    )
                ),
                content=message.content,
            )
            for message in chat_history
        ]

    async def generate_stream(
        self, chat_id: UUID, question: ChatQuestion, save_answer: bool = True
    ) -> AsyncIterable:
        print(f"####### Calling generate_stream with question: {question} #######")
        chat_engine = self._get_engine()
        if not chat_engine:
            raise ValueError("No chat engine found")
        transformed_history, streamed_chat_history = (
            self.initialize_streamed_chat_history(chat_id, question)
        )
        print(f"####### transformed_history: {transformed_history} #######")
        llama_index_transformed_history = self._format_chat_history(transformed_history)

        response_tokens = []
        # response = await chat_engine.astream_chat(
        #     message=question.question,
        #     chat_history=llama_index_transformed_history,
        # )
        response = chat_engine.stream_chat(
            message=question.question,
            chat_history=llama_index_transformed_history,
        )
        for chunk in response.response_gen:
            print(chunk)
            response_tokens.append(chunk)
            streamed_chat_history.assistant = chunk
            yield f"data: {json.dumps(streamed_chat_history.dict())}"
        # response = await chat_engine.aquery(
        #     question.question,
        # )
        # streamed_chat_history.assistant = str(response)
        # yield f"data: {json.dumps(streamed_chat_history.dict())}"

        # self.save_answer(question, str(response), streamed_chat_history, save_answer)
        self.save_answer(question, response_tokens, streamed_chat_history, save_answer)
