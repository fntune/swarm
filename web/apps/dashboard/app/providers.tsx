"use client";

import { SpawndApiError } from "@spawnd/api-client";
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";

function handleUnauthorized(error: unknown) {
  if (error instanceof SpawndApiError && error.status === 401) {
    window.location.assign("/login");
  }
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({ onError: handleUnauthorized }),
        defaultOptions: {
          queries: {
            staleTime: 3_000,
            retry: 1,
            refetchOnWindowFocus: true,
          },
          mutations: {
            onError: handleUnauthorized,
          },
        },
      }),
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
