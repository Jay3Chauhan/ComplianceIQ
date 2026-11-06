"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { ConnectionBanner } from "@/components/shell/connection-banner";
import { SettingsDialog } from "@/components/shell/settings-dialog";
import { ShortcutsDialog } from "@/components/shell/shortcuts-dialog";
import { Sidebar } from "@/components/shell/sidebar";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useUI } from "@/lib/ui";
import { cn } from "@/lib/utils";

function isTyping(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { sidebarCollapsed, mobileNavOpen, setMobileNavOpen, setShortcutsOpen } = useUI();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "o") {
        e.preventDefault();
        router.push("/");
      } else if (e.key === "?" && !e.metaKey && !e.ctrlKey && !isTyping(e.target)) {
        e.preventDefault();
        setShortcutsOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router, setShortcutsOpen]);

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
        <SheetContent
          side="left"
          className="w-[85vw] max-w-[300px] gap-0 p-0"
          showCloseButton={false}
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Sidebar variant="mobile" />
        </SheetContent>
      </Sheet>

      <main className="flex min-w-0 flex-1 flex-col">
        <ConnectionBanner />
        {children}
      </main>
      <SettingsDialog />
      <ShortcutsDialog />
    </div>
  );
}
