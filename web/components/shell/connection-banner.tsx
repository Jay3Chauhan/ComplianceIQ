"use client";

import { RefreshCwIcon, WifiOffIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useMeta } from "@/lib/queries";

/** Shown when the web server can't reach the API (or isn't configured for it). */
export function ConnectionBanner() {
  const meta = useMeta();
  if (!meta.isError) return null;
  const err = meta.error;
  const message =
    err instanceof ApiError && err.code === "not_configured"
      ? "The web server isn’t configured with an API URL (COMPLIANCEIQ_API_URL)."
      : err instanceof ApiError && err.status === 401
        ? "The web server’s API key was rejected. Check COMPLIANCEIQ_API_KEY."
        : "Can’t reach the ComplianceIQ API. Answers and history are unavailable until it’s back.";
  return (
    <div role="alert" className="flex items-center gap-3 border-b border-partial/30 bg-partial/10 px-4 py-2 text-sm">
      <WifiOffIcon className="size-4 shrink-0 text-partial" />
      <p className="min-w-0 flex-1">{message}</p>
      <Button variant="outline" size="sm" className="h-7 shrink-0 bg-background" disabled={meta.isFetching} onClick={() => meta.refetch()}>
        <RefreshCwIcon className={meta.isFetching ? "animate-spin" : undefined} /> Retry
      </Button>
    </div>
  );
}
