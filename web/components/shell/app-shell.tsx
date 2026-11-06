"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { SettingsDialog } from "@/components/shell/settings-dialog";
import { Sidebar } from "@/components/shell/sidebar";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useUI } from "@/lib/ui";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { sidebarCollapsed, mobileNavOpen, setMobileNavOpen } = useUI();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "o") {
        e.preventDefault();
        router.push("/");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  return (
    <div className="flex h-dvh w-full overflow-hidden">
      <aside
        className={cn(
          "hidden shrink-0 overflow-hidden border-r border-sidebar-border transition-[width] duration-200 ease-out md:block",
          sidebarCollapsed ? "w-0 border-r-0" : "w-[272px]",
        )}
        aria-label="Sidebar"
      >
        <div className="h-full w-[272px]">
          <Sidebar variant="desktop" />
        </div>
      </aside>

      <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <SheetContent side="left" className="w-[85vw] max-w-[300px] gap-0 p-0" showCloseButton={false}>
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Sidebar variant="mobile" />
        </SheetContent>
      </Sheet>

      <main className="flex min-w-0 flex-1 flex-col">{children}</main>
      <SettingsDialog />
    </div>
  );
}
