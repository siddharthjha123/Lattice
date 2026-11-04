"use client";

import React, { useState, useEffect } from "react";
import { MotionConfig } from "framer-motion";
import { useAuthStore } from "@/stores/authStore";
import { useTelemetryStore } from "@/stores/telemetryStore";
import { clearPoolCodes } from "@/lib/api/poolsAdapter";
import { ApiError } from "@/lib/api/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 2000,
            retry: (count, error) =>
              !(
                error instanceof ApiError &&
                [401, 403, 404].includes(error.status)
              ) && count < 1,
            refetchOnWindowFocus: true,
          },
        },
      }),
  );

  const token = useAuthStore((s) => s.token);
  useEffect(() => {
    queryClient.clear();
    clearPoolCodes();
    useTelemetryStore.getState().clearHistory();
  }, [token, queryClient]);
  useEffect(() => {
    const rejected = () => {
      useAuthStore.getState().logout();
      queryClient.clear();
    };
    window.addEventListener("lattice:unauthorized", rejected);
    return () => window.removeEventListener("lattice:unauthorized", rejected);
  }, [queryClient]);
  return (
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">{children}</MotionConfig>
    </QueryClientProvider>
  );
}
