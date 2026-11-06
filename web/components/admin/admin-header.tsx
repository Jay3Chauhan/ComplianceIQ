"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { LogOutIcon, ShieldCheckIcon } from "lucide-react";
import { TopBar } from "@/components/shell/top-bar";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useAdminLogout } from "@/lib/admin-queries";
import { cn } from "@/lib/utils";

const TABS = [
  { id: "overview", href: "/admin", label: "Overview" },
  { id: "documents", href: "/admin/documents", label: "Documents" },
] as const;

export function AdminHeader({ active }: { active: (typeof TABS)[number]["id"] }) {
  const router = useRouter();
  const logout = useAdminLogout();
  return (
    <TopBar
      actions={
        <Button
          variant="ghost"
          size="sm"
          className="gap-1.5 text-muted-foreground"
          disabled={logout.isPending}
          onClick={() => logout.mutate(undefined, { onSuccess: () => router.push("/") })}
        >
          <LogOutIcon /> <span className="hidden sm:inline">Sign out</span>
        </Button>
      }
    >
      <ShieldCheckIcon className="size-4 text-primary" />
      <h1 className="text-sm font-medium">Admin</h1>
      <nav className="ml-2 flex gap-1" aria-label="Admin sections">
        {TABS.map((t) => (
          <Link
            key={t.id}
            href={t.href}
            aria-current={active === t.id ? "page" : undefined}
            className={cn(
              "h-7 rounded-full px-3 text-[13px] leading-7 transition-colors",
              active === t.id ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {t.label}
          </Link>
        ))}
      </nav>
    </TopBar>
  );
}

/** Sends the admin back to sign-in when the session expires mid-use. */
export function useAdminAuthRedirect(error: unknown) {
  const router = useRouter();
  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) {
      router.replace(`/admin/login?next=${encodeURIComponent(window.location.pathname)}`);
    }
  }, [error, router]);
}

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div
      className={cn("h-1.5 overflow-hidden rounded-full bg-muted", className)}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value * 100)}
    >
      <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${Math.max(2, value * 100)}%` }} />
    </div>
  );
}

export function Panel({
  title,
  description,
  action,
  children,
  className,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-xl border border-border bg-card p-5", className)}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
