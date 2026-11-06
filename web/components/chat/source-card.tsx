"use client";

import { ChevronDownIcon, ExternalLinkIcon, FileTextIcon } from "lucide-react";
import Link from "next/link";
import { forwardRef, useState } from "react";
import { documentHref } from "@/components/chat/citation-chip";
import { RegulatorBadge, regulatorColor } from "@/components/common/regulator-badge";
import type { Source } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export const SourceCard = forwardRef<
  HTMLDivElement,
  { source: Source; highlighted?: boolean; flashKey?: number; showNumber?: boolean; action?: React.ReactNode }
>(function SourceCard({ source, highlighted, flashKey, showNumber = true, action }, ref) {
  const [expanded, setExpanded] = useState(false);
  const relevance = Math.round(Math.min(1, Math.max(0, source.relevance_score)) * 100);

  return (
    <div
      ref={ref}
      key={flashKey}
      className={cn(
        "group/card relative overflow-hidden rounded-xl border bg-card p-3.5 text-sm transition-colors",
        highlighted ? "animate-flash border-primary/50" : "border-border hover:border-foreground/15",
      )}
    >
      <span className="absolute inset-y-0 left-0 w-[3px]" style={{ background: regulatorColor(source.category) }} />
      <div className="flex items-start gap-2.5">
        {showNumber && (
          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-primary/10 font-mono text-xs font-semibold text-primary">
            {source.id}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <RegulatorBadge category={source.category} />
            <p className="line-clamp-1 text-[13px] font-medium" title={source.doc_name}>
              {source.doc_name}
            </p>
          </div>
          {source.circular_id && (
            <p className="mt-1 truncate font-mono text-[10.5px] text-muted-foreground" title={source.circular_id}>
              {source.circular_id}
            </p>
          )}
          <p className="mt-1 line-clamp-1 text-xs text-muted-foreground" title={source.section}>
            {source.section ? `${source.section} · ` : ""}
            <span className="font-medium text-foreground/80">Page {source.page_number}</span>
            {source.date ? ` · ${formatDate(source.date)}` : ""}
          </p>
        </div>
      </div>

      <p className={cn("mt-2.5 text-[13px] leading-relaxed text-foreground/85", !expanded && "line-clamp-4")}>
        {expanded ? source.text : source.snippet}
      </p>

      <div className="mt-3 flex items-center gap-2">
        <div className="flex items-center gap-1.5" title={`Relevance ${relevance}%`}>
          <div className="h-1 w-14 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary/70" style={{ width: `${Math.max(6, relevance)}%` }} />
          </div>
          <span className="font-mono text-[10px] text-muted-foreground">{relevance}%</span>
        </div>
        <div className="ml-auto flex items-center gap-0.5">
          {action}
          {source.snippet.endsWith("…") && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="inline-flex items-center gap-0.5 rounded-md px-1.5 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              {expanded ? "Less" : "More"}
              <ChevronDownIcon className={cn("size-3 transition-transform", expanded && "rotate-180")} />
            </button>
          )}
          <Link
            href={documentHref(source)}
            className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs font-medium text-primary hover:bg-primary/10"
          >
            <FileTextIcon className="size-3.5" /> Open
          </Link>
          {source.source_url && (
            <a
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Official source"
              className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              <ExternalLinkIcon className="size-3.5" />
            </a>
          )}
        </div>
      </div>
    </div>
  );
});
