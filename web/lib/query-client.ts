import { QueryClient, isServer } from "@tanstack/react-query";
import { ApiError } from "@/lib/api/client";

function make() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
      },
    },
  });
}

let browserClient: QueryClient | undefined;

/** One client per browser session; the chat store uses it to update caches from stream events. */
export function getQueryClient(): QueryClient {
  if (isServer) return make();
  browserClient ??= make();
  return browserClient;
}
