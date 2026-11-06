"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeftIcon, Loader2Icon, LockKeyholeIcon } from "lucide-react";
import { LogoMark } from "@/components/common/logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { errorMessage } from "@/lib/api/client";
import { useAdminLogin, useAdminSession } from "@/lib/admin-queries";

function safeNext(): string {
  const next = new URLSearchParams(window.location.search).get("next");
  return next && next.startsWith("/admin") && !next.startsWith("//") ? next : "/admin";
}

export function AdminLogin() {
  const router = useRouter();
  const session = useAdminSession();
  const login = useAdminLogin();
  const [password, setPassword] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    login.mutate(password, { onSuccess: () => router.replace(safeNext()) });
  };

  return (
    <div className="flex min-h-0 flex-1 items-center justify-center overflow-y-auto px-4 py-10">
      <div className="w-full max-w-sm animate-fade-up">
        <div className="flex flex-col items-center text-center">
          <LogoMark className="size-11 rounded-xl" />
          <h1 className="mt-4 text-xl font-semibold tracking-tight">Admin console</h1>
          <p className="mt-1 text-sm text-muted-foreground">Manage documents, indexing and usage analytics.</p>
        </div>

        {session.data && !session.data.enabled ? (
          <div className="mt-8 rounded-xl border border-border bg-card p-5 text-sm">
            <p className="font-medium">The admin console is turned off</p>
            <p className="mt-1.5 text-muted-foreground">
              Set <code className="rounded bg-muted px-1 font-mono text-xs">ADMIN_PASSWORD</code> and{" "}
              <code className="rounded bg-muted px-1 font-mono text-xs">COMPLIANCEIQ_ADMIN_KEY</code> (the backend’s{" "}
              <code className="rounded bg-muted px-1 font-mono text-xs">ADMIN_API_KEY</code>) in{" "}
              <code className="rounded bg-muted px-1 font-mono text-xs">web/.env.local</code>, then restart the web server.
            </p>
          </div>
        ) : (
          <form onSubmit={submit} className="mt-8 space-y-3 rounded-xl border border-border bg-card p-5 shadow-sm">
            <label htmlFor="admin-password" className="text-sm font-medium">
              Password
            </label>
            <div className="relative">
              <LockKeyholeIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="admin-password"
                type="password"
                autoComplete="current-password"
                autoFocus
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="h-10 pl-9"
                aria-invalid={login.isError || undefined}
              />
            </div>
            {login.isError && <p className="text-xs text-destructive">{errorMessage(login.error)}</p>}
            <Button type="submit" className="h-10 w-full" disabled={!password || login.isPending || session.isPending}>
              {login.isPending && <Loader2Icon className="animate-spin" />}
              Sign in
            </Button>
          </form>
        )}

        <Link href="/" className="mt-6 flex items-center justify-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeftIcon className="size-3.5" /> Back to chat
        </Link>
      </div>
    </div>
  );
}
