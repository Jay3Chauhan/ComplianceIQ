"use client";

import { MenuIcon, PanelLeftOpenIcon } from "lucide-react";
import { IconButton } from "@/components/common/icon-button";
import { useUI } from "@/lib/ui";
import { cn } from "@/lib/utils";

/** Page header: sidebar toggles on the left, page title, and page actions on the right. */
export function TopBar({ children, actions, className }: { children?: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  const { sidebarCollapsed, setSidebarCollapsed, setMobileNavOpen } = useUI();
  return (
    <header
      className={cn(
        "flex h-14 shrink-0 items-center gap-2 border-b border-transparent bg-background/80 px-3 backdrop-blur-md supports-backdrop-filter:bg-background/60",
        className,
      )}
    >
      <IconButton label="Open menu" className="md:hidden" side="right" onClick={() => setMobileNavOpen(true)}>
        <MenuIcon />
      </IconButton>
      {sidebarCollapsed && (
        <IconButton label="Open sidebar" className="hidden md:inline-flex" side="right" onClick={() => setSidebarCollapsed(false)}>
          <PanelLeftOpenIcon />
        </IconButton>
      )}
      <div className="flex min-w-0 flex-1 items-center gap-2">{children}</div>
      {actions && <div className="flex shrink-0 items-center gap-1">{actions}</div>}
    </header>
  );
}
