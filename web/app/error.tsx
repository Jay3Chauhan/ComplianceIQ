"use client";

import { Button } from "@/components/ui/button";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">
      <h1 className="text-xl font-semibold">Something went wrong</h1>
      <p className="max-w-md text-sm text-muted-foreground">{error.message || "An unexpected error occurred."}</p>
      <Button onClick={reset} className="mt-2">
        Try again
      </Button>
    </div>
  );
}
