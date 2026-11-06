"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useEffect } from "react";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { getQueryClient } from "@/lib/query-client";
import { useSettings } from "@/lib/settings";
import { useUI } from "@/lib/ui";

export function Providers({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    void useSettings.persist.rehydrate();
    void useUI.persist.rehydrate();
  }, []);

  return (
    <QueryClientProvider client={getQueryClient()}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
        <TooltipProvider delayDuration={300}>
          {children}
          <Toaster position="top-center" closeButton />
        </TooltipProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
