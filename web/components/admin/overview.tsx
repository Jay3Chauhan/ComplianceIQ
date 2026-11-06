"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  ActivityIcon,
  CircleAlertIcon,
  CircleCheckIcon,
  DatabaseIcon,
  GaugeIcon,
  MessageCircleQuestionIcon,
  RefreshCwIcon,
  ShieldCheckIcon,
  ThumbsUpIcon,
  Trash2Icon,
} from "lucide-react";
import { AdminHeader, Panel, Progress, useAdminAuthRedirect } from "@/components/admin/admin-header";
import { RegulatorBadge } from "@/components/common/regulator-badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import type { AdminStats } from "@/lib/api/types";
import { useAdminStats, useClearCache, useReindexAll } from "@/lib/admin-queries";
import { useMeta, useReady } from "@/lib/queries";
import { cn } from "@/lib/utils";

const WINDOWS = [1, 7, 30, 90];

const MODE_LABELS: Record<string, { label: string; color: string }> = {
  regulatory: { label: "Cited from documents", color: "var(--verified)" },
  general: { label: "General knowledge", color: "var(--general)" },
  not_found: { label: "Not found / refused", color: "var(--partial)" },
  error: { label: "Errors", color: "var(--unverified)" },
};

const VERIFICATION_LABELS: Record<string, { label: string; color: string }> = {
  verified: { label: "Verified", color: "var(--verified)" },
  partially_verified: { label: "Partially verified", color: "var(--partial)" },
  unverified: { label: "Unverified", color: "var(--unverified)" },
  not_applicable: { label: "Not applicable", color: "var(--muted-foreground)" },
};

function pct(n: number | null | undefined) {
  return n == null ? "—" : `${Math.round(n * 100)}%`;
}

function ms(n: number | null | undefined) {
  return n == null ? "—" : n >= 1000 ? `${(n / 1000).toFixed(1)} s` : `${n} ms`;
}

function Kpi({
  icon: Icon,
  label,
  value,
  hint,
  className,
}: {
  icon: React.ElementType;
  label: string;
  value: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={cn("rounded-xl border border-border bg-card p-4", className)}>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="size-3.5" /> {label}
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 truncate text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Breakdown({ data, labels }: { data: Record<string, number>; labels: Record<string, { label: string; color: string }> }) {
  const total = Object.values(data).reduce((a, b) => a + b, 0);
  if (!total) return <p className="py-6 text-center text-sm text-muted-foreground">No data in this window.</p>;
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  return (
    <div className="space-y-3">
      <div className="flex h-2.5 overflow-hidden rounded-full bg-muted">
        {rows.map(([k, n]) => (
          <div key={k} style={{ width: `${(n / total) * 100}%`, background: labels[k]?.color ?? "var(--muted-foreground)" }} />
        ))}
      </div>
      <ul className="space-y-1.5">
        {rows.map(([k, n]) => (
          <li key={k} className="flex items-center gap-2 text-sm">
            <span className="size-2 rounded-full" style={{ background: labels[k]?.color ?? "var(--muted-foreground)" }} />
            <span className="flex-1 text-muted-foreground">{labels[k]?.label ?? k}</span>
            <span className="tabular-nums">{n.toLocaleString()}</span>
            <span className="w-10 text-right text-xs text-muted-foreground tabular-nums">{Math.round((n / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function HealthChecks() {
  const ready = useReady();
  const checks = Object.entries(ready.data?.checks ?? {});
  return (
    <Panel
      title="Service health"
      description="Live dependency checks from /ready."
      action={
        ready.data && (
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[11px] font-medium",
              ready.data.status === "ready" ? "bg-verified/12 text-verified" : "bg-unverified/12 text-unverified",
            )}
          >
            {ready.data.status === "ready" ? "All systems ready" : "Degraded"}
          </span>
        )
      }
    >
      {ready.isPending ? (
        <Skeleton className="h-28" />
      ) : ready.isError ? (
        <p className="text-sm text-unverified">The API is not reachable.</p>
      ) : (
        <ul className="divide-y divide-border">
          {checks.map(([name, c]) => (
            <li key={name} className="flex items-center gap-3 py-2 text-sm">
              {c.ok ? <CircleCheckIcon className="size-4 text-verified" /> : <CircleAlertIcon className="size-4 text-unverified" />}
              <span className="w-20 font-medium capitalize">{name}</span>
              <span className="min-w-0 flex-1 truncate text-muted-foreground" title={c.detail ?? ""}>
                {c.detail}
              </span>
              {c.latency_ms != null && <span className="text-xs text-muted-foreground tabular-nums">{c.latency_ms} ms</span>}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function IndexPanel({ stats }: { stats: AdminStats }) {
  const { index, documents } = stats;
  return (
    <Panel
      title="Index"
      description={index.collection ? `Qdrant collection “${index.collection}”` : "Qdrant collection"}
      action={
        <Link href="/admin/documents" className="text-xs font-medium text-primary hover:underline">
          Manage documents
        </Link>
      }
    >
      {index.error ? (
        <p className="text-sm text-unverified">{index.error}</p>
      ) : (
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">Vectors</dt>
            <dd className="font-medium tabular-nums">{(index.points ?? 0).toLocaleString()}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Status</dt>
            <dd className="font-medium capitalize">{index.status ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Documents indexed</dt>
            <dd className="font-medium tabular-nums">
              {documents.indexed} / {documents.total}
            </dd>
          </div>
        </dl>
      )}
      {documents.total > 0 && <Progress value={documents.indexed / documents.total} className="mt-4" />}
      <div className="mt-4 flex flex-wrap gap-2">
        {Object.entries(documents.by_category).map(([cat, n]) => (
          <span key={cat} className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2 py-1 text-xs">
            <RegulatorBadge category={cat} /> {n}
          </span>
        ))}
      </div>
    </Panel>
  );
}

function Maintenance() {
  const clear = useClearCache();
  const reindex = useReindexAll();
  const [confirm, setConfirm] = useState(false);
  return (
    <Panel title="Maintenance" description="Use after changing documents, models or prompts.">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-medium">Clear caches</p>
            <p className="text-xs text-muted-foreground">Drops cached retrievals and answers (10-minute TTL).</p>
          </div>
          <Button variant="outline" size="sm" disabled={clear.isPending} onClick={() => clear.mutate()}>
            <Trash2Icon /> Clear
          </Button>
        </div>
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm font-medium">Re-index everything</p>
            <p className="text-xs text-muted-foreground">Re-parses and re-embeds every PDF. Takes minutes.</p>
          </div>
          <Button variant="outline" size="sm" disabled={reindex.isPending} onClick={() => setConfirm(true)}>
            <RefreshCwIcon /> Re-index
          </Button>
        </div>
      </div>
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Re-index every document?</AlertDialogTitle>
            <AlertDialogDescription>
              Each PDF is queued as a background job and processed one at a time. Answers keep working meanwhile, but a
              document’s passages are briefly missing while it’s replaced.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => reindex.mutate()}>Queue jobs</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Panel>
  );
}

export function AdminOverview() {
  const [days, setDays] = useState(7);
  const stats = useAdminStats(days);
  const meta = useMeta();
  useAdminAuthRedirect(stats.error);
  const u = stats.data?.usage;
  const feedbackTotal = (u?.feedback.positive ?? 0) + (u?.feedback.negative ?? 0);
  const verifiedTotal = Object.values(u?.verification ?? {}).reduce((a, b) => a + b, 0);
  const unanswered = useMemo(() => {
    const counts = new Map<string, number>();
    for (const q of u?.recent_unanswered ?? []) counts.set(q.trim(), (counts.get(q.trim()) ?? 0) + 1);
    return [...counts.entries()];
  }, [u?.recent_unanswered]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <AdminHeader active="overview" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl px-4 py-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">Overview</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Usage, answer quality and index health
                {meta.data ? ` · API v${meta.data.version}` : ""}
              </p>
            </div>
            <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
              <SelectTrigger className="w-36" aria-label="Time window">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WINDOWS.map((d) => (
                  <SelectItem key={d} value={String(d)}>
                    {d === 1 ? "Last 24 hours" : `Last ${d} days`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {stats.isError && !(stats.error as { status?: number })?.status && (
            <p className="mt-6 rounded-lg border border-unverified/30 bg-unverified/5 p-3 text-sm text-unverified">
              Couldn’t load stats. Is the API running?
            </p>
          )}

          <div className={cn("mt-6 grid grid-cols-2 gap-3 lg:grid-cols-5", stats.isFetching && "opacity-80")}>
            {!u ? (
              Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-[104px] rounded-xl" />)
            ) : (
              <>
                <Kpi icon={MessageCircleQuestionIcon} label="Questions" value={u.total_queries.toLocaleString()} hint={`${u.errors} errors`} />
                <Kpi icon={DatabaseIcon} label="Grounded" value={pct(u.grounded_rate)} hint="answered from documents" />
                <Kpi
                  icon={ShieldCheckIcon}
                  label="Verified"
                  value={verifiedTotal ? pct((u.verification.verified ?? 0) / verifiedTotal) : "—"}
                  hint={`${u.revised_answers} answers revised`}
                />
                <Kpi icon={GaugeIcon} label="Latency p50" value={ms(u.latency_ms.p50)} hint={`p95 ${ms(u.latency_ms.p95)}`} />
                <Kpi
                  icon={ThumbsUpIcon}
                  label="Helpful"
                  value={feedbackTotal ? pct(u.feedback.positive / feedbackTotal) : "—"}
                  hint={`${u.feedback.positive} up · ${u.feedback.negative} down`}
                  className="col-span-2 lg:col-span-1"
                />
              </>
            )}
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <Panel title="How questions were answered">
              {u ? <Breakdown data={u.by_mode} labels={MODE_LABELS} /> : <Skeleton className="h-32" />}
            </Panel>
            <Panel title="Answer verification" description="Claim-level check of cited answers.">
              {u ? <Breakdown data={u.verification} labels={VERIFICATION_LABELS} /> : <Skeleton className="h-32" />}
            </Panel>
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            <Panel
              title="Recently unanswered"
              description="Questions with no supporting passage: candidates for new documents or eval cases."
              className="lg:col-span-2"
            >
              {!u ? (
                <Skeleton className="h-32" />
              ) : unanswered.length === 0 ? (
                <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                  <ActivityIcon className="size-4" /> Every question in this window found supporting documents.
                </p>
              ) : (
                <ul className="divide-y divide-border">
                  {unanswered.map(([q, count]) => (
                    <li key={q} className="flex items-center gap-3 py-2 text-sm">
                      <span className="min-w-0 flex-1 truncate" title={q}>
                        {q}
                      </span>
                      {count > 1 && (
                        <span className="shrink-0 rounded-full bg-muted px-1.5 text-[11px] text-muted-foreground tabular-nums">×{count}</span>
                      )}
                      <Link href={`/?q=${encodeURIComponent(q)}`} className="shrink-0 text-xs font-medium text-primary hover:underline">
                        Try it
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            {stats.data ? <IndexPanel stats={stats.data} /> : <Skeleton className="h-64 rounded-xl" />}
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-2">
            <HealthChecks />
            <Maintenance />
          </div>
        </div>
      </div>
    </div>
  );
}
