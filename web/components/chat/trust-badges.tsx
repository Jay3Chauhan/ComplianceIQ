"use client";

import {
  FileCheck2Icon,
  SearchXIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  ShieldXIcon,
  SparklesIcon,
  Wand2Icon,
} from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Confidence, ResponseMode, Verification } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const pill = "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium ring-1 ring-inset";

export function ModeBadge({ mode }: { mode: ResponseMode | null }) {
  if (mode === "regulatory")
    return (
      <span className={cn(pill, "bg-primary/8 text-primary ring-primary/20")}>
        <FileCheck2Icon className="size-3.5" /> Cited from documents
      </span>
    );
  if (mode === "general")
    return (
      <span className={cn(pill, "bg-general/10 text-general ring-general/25")}>
        <SparklesIcon className="size-3.5" /> General knowledge
      </span>
    );
  if (mode === "not_found")
    return (
      <span className={cn(pill, "bg-muted text-muted-foreground ring-border")}>
        <SearchXIcon className="size-3.5" /> Not in documents
      </span>
    );
  return null;
}

const VERIFICATION = {
  verified: { label: "Verified", icon: ShieldCheckIcon, cls: "bg-verified/10 text-verified ring-verified/25" },
  partially_verified: { label: "Partially verified", icon: ShieldAlertIcon, cls: "bg-partial/12 text-partial ring-partial/30" },
  unverified: { label: "Unverified", icon: ShieldXIcon, cls: "bg-unverified/10 text-unverified ring-unverified/25" },
} as const;

export function VerificationBadge({ verification, revised }: { verification: Verification | null; revised: boolean }) {
  if (!verification || verification.status === "not_applicable") return null;
  const v = VERIFICATION[verification.status];
  const Icon = v.icon;
  const issues = [
    ...verification.unsupported_claims.map((c) => ({ title: c.claim, detail: c.reason || "Not supported by the sources" })),
    ...verification.unsupported_numbers.map((n) => ({ title: n, detail: "Figure not found in the sources" })),
    ...verification.invalid_citations.map((n) => ({ title: `[${n}]`, detail: "Cites a source that doesn’t exist" })),
    ...verification.uncited_claims.map((c) => ({ title: c, detail: "Factual sentence without a citation" })),
  ];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button className={cn(pill, v.cls, "transition-opacity hover:opacity-80")} aria-label={`${v.label}: show details`}>
          <Icon className="size-3.5" /> {v.label}
          {revised && <Wand2Icon className="size-3" aria-label="Refined after fact-check" />}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-0">
        <div className="space-y-3 p-4">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">Fact-check</p>
            <span className="font-mono text-xs text-muted-foreground">{Math.round(verification.score * 100)}%</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                "h-full rounded-full",
                verification.status === "verified" ? "bg-verified" : verification.status === "partially_verified" ? "bg-partial" : "bg-unverified",
              )}
              style={{ width: `${Math.max(4, verification.score * 100)}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            {verification.claims_checked > 0
              ? `${verification.supported} of ${verification.claims_checked} claims supported by the cited passages.`
              : "Citations and figures checked against the sources."}{" "}
            Method: {verification.method === "rules+llm" ? "rules + AI claim check" : "rule checks"}.
          </p>
          {revised && (
            <p className="flex gap-2 rounded-md bg-partial/10 p-2 text-xs text-foreground/90">
              <Wand2Icon className="mt-0.5 size-3.5 shrink-0 text-partial" />
              The first draft had unsupported statements and was corrected automatically.
            </p>
          )}
        </div>
        {issues.length > 0 && (
          <div className="max-h-56 space-y-2 overflow-y-auto border-t border-border bg-muted/30 p-4">
            <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Flagged</p>
            {issues.slice(0, 8).map((i, idx) => (
              <div key={idx} className="text-xs">
                <p className="line-clamp-2 text-foreground/90">“{i.title}”</p>
                <p className="text-muted-foreground">{i.detail}</p>
              </div>
            ))}
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

export function ConfidenceMeter({ confidence }: { confidence: Confidence }) {
  if (!confidence) return null;
  const level = { high: 3, medium: 2, low: 1 }[confidence];
  const color = { high: "bg-verified", medium: "bg-partial", low: "bg-unverified" }[confidence];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex h-6 items-center gap-1.5 px-1 text-xs text-muted-foreground" tabIndex={0}>
          <span className="flex items-end gap-[2px]" aria-hidden>
            {[1, 2, 3].map((i) => (
              <span
                key={i}
                className={cn("w-[3px] rounded-full", i <= level ? color : "bg-border")}
                style={{ height: 4 + i * 3 }}
              />
            ))}
          </span>
          <span className="capitalize">{confidence}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {confidence === "high"
          ? "Strong source match and every claim verified"
          : confidence === "medium"
            ? "Mostly supported — check the flagged details"
            : "Weak support — verify with the regulator"}
      </TooltipContent>
    </Tooltip>
  );
}
