"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { CircleAlertIcon, FileTextIcon, LibraryIcon, SearchIcon } from "lucide-react";
import { RegulatorBadge, regulatorColor } from "@/components/common/regulator-badge";
import { TopBar } from "@/components/shell/top-bar";
import { Skeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/format";
import { useDocuments } from "@/lib/queries";
import { cn } from "@/lib/utils";

const FILTERS = ["ALL", "RBI", "SEBI", "AA"] as const;

export function Library() {
  const docs = useDocuments();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("ALL");
  const [text, setText] = useState("");

  const items = useMemo(() => {
    const q = text.trim().toLowerCase();
    return (docs.data ?? []).filter(
      (d) =>
        (filter === "ALL" || d.category === filter) &&
        (!q || `${d.name} ${d.circular_id} ${d.subcategory} ${d.issuer}`.toLowerCase().includes(q)),
    );
  }, [docs.data, filter, text]);

  const totalChunks = (docs.data ?? []).reduce((n, d) => n + d.chunks, 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar>
        <LibraryIcon className="size-4 text-muted-foreground" />
        <h1 className="text-sm font-medium">Library</h1>
      </TopBar>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-5xl px-4 py-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">Regulatory library</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {docs.data
                  ? `${docs.data.length} documents · ${totalChunks.toLocaleString()} indexed passages. Every answer is grounded in these.`
                  : "The documents ComplianceIQ answers from."}
              </p>
            </div>
            <div className="relative w-full sm:w-64">
              <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Filter documents…"
                aria-label="Filter documents"
                className="h-9 w-full rounded-lg border border-border bg-card pr-3 pl-9 text-sm outline-none focus:border-primary/40 focus:ring-3 focus:ring-primary/10"
              />
            </div>
          </div>

          <div className="mt-5 flex gap-1.5" role="tablist">
            {FILTERS.map((f) => (
              <button
                key={f}
                role="tab"
                aria-selected={filter === f}
                onClick={() => setFilter(f)}
                className={cn(
                  "h-8 rounded-full px-3.5 text-[13px] transition-colors",
                  filter === f ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {f === "ALL" ? "All" : f === "AA" ? "Account Aggregator" : f}
              </button>
            ))}
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {docs.isPending
              ? Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-44 rounded-xl" />)
              : items.map((d, i) => (
                  <Link
                    key={d.doc_id}
                    href={`/documents/${encodeURIComponent(d.doc_id)}`}
                    style={{ animationDelay: `${i * 30}ms` }}
                    className="group relative flex animate-fade-up flex-col overflow-hidden rounded-xl border border-border bg-card p-4 transition-all hover:-translate-y-0.5 hover:border-foreground/15 hover:shadow-lg hover:shadow-black/5"
                  >
                    <span className="absolute inset-x-0 top-0 h-[3px]" style={{ background: regulatorColor(d.category) }} />
                    <div className="flex items-center gap-2">
                      <RegulatorBadge category={d.category} />
                      {d.subcategory && <span className="truncate text-xs text-muted-foreground">{d.subcategory}</span>}
                    </div>
                    <p className="mt-3 line-clamp-2 text-[15px] leading-snug font-medium group-hover:text-primary">{d.name}</p>
                    {d.circular_id && (
                      <p className="mt-1.5 truncate font-mono text-[11px] text-muted-foreground" title={d.circular_id}>
                        {d.circular_id}
                      </p>
                    )}
                    <div className="mt-auto flex items-center gap-3 pt-4 text-xs text-muted-foreground">
                      <span>{formatDate(d.date) || "Undated"}</span>
                      <span className="inline-flex items-center gap-1">
                        <FileTextIcon className="size-3.5" /> {d.chunks} passages
                      </span>
                      {!d.indexed && (
                        <span className="ml-auto inline-flex items-center gap-1 text-partial">
                          <CircleAlertIcon className="size-3.5" /> Not indexed
                        </span>
                      )}
                    </div>
                  </Link>
                ))}
          </div>
          {docs.data && items.length === 0 && (
            <p className="py-16 text-center text-sm text-muted-foreground">No documents match.</p>
          )}
          {docs.isError && (
            <p className="py-16 text-center text-sm text-muted-foreground">Couldn’t load documents. Is the API running?</p>
          )}
        </div>
      </div>
    </div>
  );
}
