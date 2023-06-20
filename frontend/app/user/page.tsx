/* eslint-disable */
"use client";
import { redirect } from "next/navigation";
import { useEffect, useState } from "react";

import Spinner from "@/lib/components/ui/Spinner";
import { UserStats } from "@/lib/types/User";
import { useAxios } from "@/lib/useAxios";

import { useSupabase } from "../supabase-provider";
import { UserStatistics } from "./components/UserStatistics";

const UserPage = (): JSX.Element => {
  const [userStats, setUserStats] = useState<UserStats>();
  const { session } = useSupabase();
  const { axiosInstance } = useAxios();
  if (session === null) {
    redirect("/login");
  }

  useEffect(() => {
    const fetchUserStats = async () => {
      // setIsPending(true);
      try {
        console.log(
          `Fetching user stats from ${process.env.NEXT_PUBLIC_BACKEND_URL}/user`
        );
        const response = await axiosInstance.get<UserStats>(
          `${process.env.NEXT_PUBLIC_BACKEND_URL}/user`,
          {
            headers: {
              Authorization: `Bearer ${session.access_token}`,
            },
          }
        );
        setUserStats(response.data);
      } catch (error) {
        console.error("Error fetching user stats", error);
        setUserStats(undefined);
      }
    };
    fetchUserStats();
  }, [session.access_token]);

  return (
    <main className="w-full flex flex-col pt-10">
      <section className="flex flex-col justify-center items-center flex-1 gap-5 h-full">
        <div className="p-5 max-w-3xl w-full min-h-full flex-1 mb-24">
          {userStats ? (
            <>
              <UserStatistics {...userStats} />
            </>
          ) : (
            <div className="flex items-center justify-center">
              <span>获取数据中...</span>
              <Spinner />
            </div>
          )}
        </div>
      </section>
    </main>
  );
};
export default UserPage;
