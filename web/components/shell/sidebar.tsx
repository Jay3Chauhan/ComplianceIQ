"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import {
  ArchiveIcon,
  ArrowLeftIcon,
  LibraryIcon,
  MessageSquarePlusIcon,
  PanelLeftCloseIcon,
  SearchIcon,
  Settings2Icon,
  TextSearchIcon,
  XIcon,
} from "lucide-react";
import { IconButton } from "@/components/common/icon-button";
import { Logo } from "@/components/common/logo";
import { ConversationRow } from "@/components/shell/conversation-row";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { groupConversations } from "@/lib/format";
import { useConversations } from "@/lib/queries";
import { useUI } from "@/lib/ui";
import { cn } from "@/lib/utils";

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

const NAV = [
  { href: "/documents", label: "Library", icon: LibraryIcon },
  { href: "/search", label: "Passage search", icon: TextSearchIcon },
];

/** Renders with the pathname once known; dynamic routes only know it at request time. */
function WithPathname({ children }: { children: (pathname: string | null) => React.ReactNode }) {
  return (
    <Suspense fallback={children(null)}>
      <PathnameReader>{children}</PathnameReader>
    </Suspense>
  );
}

function PathnameReader({ children }: { children: (pathname: string) => React.ReactNode }) {
  return children(usePathname());
}

export function Sidebar({ variant }: { variant: "desktop" | "mobile" }) {
  const { setSidebarCollapsed, setMobileNavOpen, setSettingsOpen } = useUI();
  const [query, setQuery] = useState("");
  const [archived, setArchived] = useState(false);
  const q = useDebounced(query.trim(), 250);
  const list = useConversations(q, archived);
  const sentinel = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const groups = groupConversations(items);
  const close = () => variant === "mobile" && setMobileNavOpen(false);

  useEffect(() => {
    const el = sentinel.current;
    if (!el) return;
    const io = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && list.hasNextPage && !list.isFetchingNextPage) list.fetchNextPage();
    });
    io.observe(el);
    return () => io.disconnect();
  }, [list]);

  useEffect(() => {
    if (variant !== "desktop") return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSidebarCollapsed(false);
        requestAnimationFrame(() => searchRef.current?.focus());
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [variant, setSidebarCollapsed]);

  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex h-14 shrink-0 items-center justify-between px-3">
        <Link href="/" onClick={close} className="rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
          <Logo />
        </Link>
        {variant === "desktop" && (
          <IconButton label="Close sidebar" side="right" onClick={() => setSidebarCollapsed(true)}>
            <PanelLeftCloseIcon />
          </IconButton>
        )}
      </div>

      <div className="space-y-1 px-3 pb-2">
        <Button asChild variant="outline" className="h-9 w-full justify-start gap-2 bg-background shadow-xs">
          <Link href="/" onClick={close}>
            <MessageSquarePlusIcon className="text-primary" />
            New chat
            <kbd className="ml-auto hidden font-mono text-[10px] text-muted-foreground lg:inline">Ctrl ⇧ O</kbd>
          </Link>
        </Button>
        <WithPathname>
          {(pathname) =>
            NAV.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                onClick={close}
                className={cn(
                  "flex h-8 items-center gap-2 rounded-lg px-2.5 text-sm transition-colors",
                  pathname?.startsWith(href)
                    ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/75 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            ))
          }
        </WithPathname>
      </div>

      <div className="px-3 pb-2">
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            ref={searchRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={archived ? "Search archived…" : "Search chats…"}
            aria-label="Search conversations"
            className="h-8 w-full rounded-lg border border-transparent bg-sidebar-accent/60 pr-7 pl-8 text-sm outline-none placeholder:text-muted-foreground focus:border-ring/50 focus:bg-background"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              aria-label="Clear search"
              className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-0.5 text-muted-foreground hover:text-foreground"
            >
              <XIcon className="size-3.5" />
            </button>
          )}
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <nav className="px-2 pb-4" aria-label="Conversations">
          {archived && (
            <button
              onClick={() => setArchived(false)}
              className="mb-1 flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-muted-foreground hover:text-foreground"
            >
              <ArrowLeftIcon className="size-3.5" /> Back to chats
            </button>
          )}
          {list.isPending ? (
            <div className="space-y-2 px-2 pt-2">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-6" style={{ width: `${90 - i * 8}%` }} />
              ))}
            </div>
          ) : list.isError ? (
            <p className="px-3 py-4 text-sm text-muted-foreground">Couldn’t load conversations.</p>
          ) : items.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              {q ? "No conversations match." : archived ? "No archived conversations." : "Your conversations will appear here."}
            </p>
          ) : (
            <WithPathname>
              {(pathname) => {
                const activeId = pathname?.startsWith("/c/") ? pathname.split("/")[2] : null;
                return groups.map((group) => (
                  <div key={group.label} className="mb-3">
                    <h3 className="px-2.5 pt-2 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                      {group.label}
                    </h3>
                    <div className="space-y-px">
                      {group.items.map((c) => (
                        <ConversationRow key={c.id} conversation={c} active={c.id === activeId} />
                      ))}
                    </div>
                  </div>
                ));
              }}
            </WithPathname>
          )}
          <div ref={sentinel} className="h-px" />
          {list.isFetchingNextPage && <Skeleton className="mx-2 h-6" />}
        </nav>
      </ScrollArea>

      <div className="flex shrink-0 items-center gap-1 border-t border-sidebar-border px-2 py-2">
        <Button variant="ghost" size="sm" className="flex-1 justify-start gap-2" onClick={() => setSettingsOpen(true)}>
          <Settings2Icon /> Settings
        </Button>
        {!archived && (
          <IconButton label="Archived chats" onClick={() => setArchived(true)}>
            <ArchiveIcon />
          </IconButton>
        )}
        <ThemeToggle />
      </div>
    </div>
  );
}
