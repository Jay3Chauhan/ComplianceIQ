"use client";

import { ArrowUpRightIcon, BadgeCheckIcon, FileSearchIcon, SearchXIcon } from "lucide-react";
import { LogoMark } from "@/components/common/logo";
import { Skeleton } from "@/components/ui/skeleton";
import type { Category } from "@/lib/api/types";
import { useSuggestions } from "@/lib/queries";
import { cn } from "@/lib/utils";

const REGULATORS: { id: Category; label: string; dot: string }[] = [
  { id: "ALL", label: "All", dot: "bg-primary" },
  { id: "RBI", label: "RBI", dot: "bg-rbi" },
  { id: "SEBI", label: "SEBI", dot: "bg-sebi" },
  { id: "AA", label: "Account Aggregator", dot: "bg-aa" },
];

const PILLARS = [
  { icon: FileSearchIcon, title: "Cited to the page", text: "Every claim links to the circular, section and page." },
  { icon: BadgeCheckIcon, title: "Fact-checked", text: "Claims are verified against the sources before you see them." },
  { icon: SearchXIcon, title: "Says when it doesn’t know", text: "No guessing when the documents don’t cover it." },
];

export function EmptyState({
  category,
  onCategory,
  onPick,
}: {
  category: Category;
  onCategory: (c: Category) => void;
  onPick: (q: string) => void;
}) {
  const suggestions = useSuggestions(category);

  return (
    <div className="mx-auto w-full max-w-3xl animate-fade-up px-4">
      <div className="flex flex-col items-center text-center">
        <LogoMark className="size-12 rounded-2xl shadow-lg shadow-primary/20 [&_svg]:size-6" />
        <h1 className="mt-5 text-2xl font-semibold tracking-tight text-balance sm:text-3xl">
          What do you need to check today?
        </h1>
        <p className="mt-2 max-w-lg text-[15px] text-balance text-muted-foreground">
          Ask about RBI master directions, SEBI master circulars or the Account Aggregator framework. Get answers cited to
          the exact page.
        </p>
      </div>

      <div className="mt-7 flex flex-wrap justify-center gap-1.5" role="radiogroup" aria-label="Regulator">
        {REGULATORS.map((r) => (
          <button
            key={r.id}
            role="radio"
            aria-checked={category === r.id}
            onClick={() => onCategory(r.id)}
            className={cn(
              "inline-flex h-8 items-center gap-2 rounded-full border px-3.5 text-[13px] transition-all",
              category === r.id
                ? "border-primary/40 bg-primary/8 font-medium text-foreground shadow-xs"
                : "border-border bg-card text-muted-foreground hover:border-foreground/20 hover:text-foreground",
            )}
          >
            <span className={cn("size-2 rounded-full", r.dot)} />
            {r.label}
          </button>
        ))}
      </div>

      <div className="mt-5 grid gap-2.5 sm:grid-cols-2">
        {suggestions.isPending
          ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[68px] rounded-xl" />)
          : (suggestions.data ?? []).map((q, i) => (
              <button
                key={q}
                onClick={() => onPick(q)}
                style={{ animationDelay: `${i * 50}ms` }}
                className="group/s flex animate-fade-up items-start gap-3 rounded-xl border border-border bg-card p-3.5 text-left text-[13.5px] leading-snug transition-all hover:-translate-y-px hover:border-primary/35 hover:shadow-md hover:shadow-primary/5"
              >
                <span className="flex-1 text-foreground/90">{q}</span>
                <ArrowUpRightIcon className="size-4 shrink-0 text-muted-foreground transition-colors group-hover/s:text-primary" />
              </button>
            ))}
      </div>

      <div className="mt-8 hidden gap-3 sm:grid sm:grid-cols-3">
        {PILLARS.map(({ icon: Icon, title, text }) => (
          <div key={title} className="rounded-xl p-3">
            <Icon className="size-4 text-primary" />
            <p className="mt-2 text-[13px] font-medium">{title}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
