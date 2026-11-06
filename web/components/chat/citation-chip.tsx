"use client";

import { ExternalLinkIcon, FileTextIcon } from "lucide-react";
import Link from "next/link";
import { RegulatorBadge } from "@/components/common/regulator-badge";
import { HoverCard, HoverCardContent, HoverCardTrigger } from "@/components/ui/hover-card";
import type { Source } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export function documentHref(s: Source) {
  return `/documents/${encodeURIComponent(s.doc_id)}?page=${s.page_number}&chunk=${encodeURIComponent(s.chunk_id)}`;
}

export function CitationChip({ n, source, onCite }: { n: number; source?: Source; onCite: (n: number) => void }) {
  const chip = (
    <button
      type="button"
      data-cite
      onClick={() => source && onCite(n)}
      aria-label={source ? `Source ${n}: ${source.doc_name}, page ${source.page_number}` : `Source ${n} (unavailable)`}
      className={cn(
        "mx-[1px] inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded-[5px] px-1 align-middle font-mono text-[10.5px] font-semibold leading-none transition-colors",
        source
          ? "bg-primary/10 text-primary ring-1 ring-primary/20 ring-inset hover:bg-primary hover:text-primary-foreground"
          : "cursor-default bg-muted text-muted-foreground line-through",
      )}
    >
      {n}
    </button>
  );
  if (!source) return chip;

  return (
    <HoverCard openDelay={150} closeDelay={80}>
      <HoverCardTrigger asChild>{chip}</HoverCardTrigger>
      <HoverCardContent side="top" className="w-[22rem] p-0">
        <div className="space-y-2 p-3.5">
          <div className="flex items-start gap-2">
            <RegulatorBadge category={source.category} />
            <div className="min-w-0">
              <p className="line-clamp-2 text-[13px] leading-snug font-medium">{source.doc_name}</p>
              {source.circular_id && (
                <p className="mt-0.5 truncate font-mono text-[10.5px] text-muted-foreground">{source.circular_id}</p>
              )}
            </div>
          </div>
          {source.section && (
            <p className="line-clamp-2 text-xs text-muted-foreground">
              {source.section} · <span className="text-foreground/80">p. {source.page_number}</span>
            </p>
          )}
          <p className="line-clamp-5 border-l-2 border-primary/30 pl-2.5 text-xs leading-relaxed text-foreground/85">
            {source.snippet}
          </p>
        </div>
        <div className="flex items-center gap-1 border-t border-border bg-muted/40 px-2 py-1.5">
          <Link
            href={documentHref(source)}
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-primary/10"
          >
            <FileTextIcon className="size-3.5" /> Open page {source.page_number}
          </Link>
          {source.source_url && (
            <a
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              Official source <ExternalLinkIcon className="size-3" />
            </a>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
