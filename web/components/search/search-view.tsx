"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangleIcon, Loader2Icon, MessageSquarePlusIcon, SearchIcon, TextSearchIcon } from "lucide-react";
import { SourceCard } from "@/components/chat/source-card";
import { TopBar } from "@/components/shell/top-bar";
import { Switch } from "@/components/ui/switch";
import { errorMessage } from "@/lib/api/client";
import type { Category } from "@/lib/api/types";
import { useSearch } from "@/lib/queries";
import { cn } from "@/lib/utils";

const CATS: { id: Category; label: string }[] = [
  { id: "ALL", label: "All" },
  { id: "RBI", label: "RBI" },
  { id: "SEBI", label: "SEBI" },
  { id: "AA", label: "AA" },
];

const EXAMPLES = ["Key Fact Statement", "video customer identification", "cooling-off period", "consent artefact"];

export function SearchView() {
  const search = useSearch();
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<Category>("ALL");
  const [rerank, setRerank] = useState(true);

  const run = (q = query, c = category) => {
    const text = q.trim();
    if (text.length < 2) return;
    search.mutate({ query: text, category: c, top_k: 10, rerank });
  };

  const data = search.data;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar>
        <TextSearchIcon className="size-4 text-muted-foreground" />
        <h1 className="text-sm font-medium">Passage search</h1>
      </TopBar>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-3xl px-4 py-8">
          <h2 className="text-2xl font-semibold tracking-tight">Find the exact passage</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Searches the documents directly (no AI answer) with the same hybrid retrieval and reranking the assistant uses.
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              run();
            }}
            className="mt-6 flex items-center gap-2 rounded-2xl border border-border bg-card p-1.5 shadow-sm focus-within:border-primary/40 focus-within:ring-4 focus-within:ring-primary/8"
          >
            <SearchIcon className="ml-2.5 size-4 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. periodic updation of KYC for high-risk customers"
              aria-label="Search passages"
              autoFocus
              className="h-9 min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground/80"
            />
            <button
              type="submit"
              disabled={query.trim().length < 2 || search.isPending}
              className="inline-flex h-9 items-center gap-1.5 rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {search.isPending && <Loader2Icon className="size-4 animate-spin" />} Search
            </button>
          </form>

          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            {CATS.map((c) => (
              <button
                key={c.id}
                onClick={() => {
                  setCategory(c.id);
                  if (data) run(query, c.id);
                }}
                className={cn(
                  "h-7 rounded-full px-3 text-xs transition-colors",
                  category === c.id ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {c.label}
              </button>
            ))}
            <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
              <Switch checked={rerank} onCheckedChange={setRerank} size="sm" /> Rerank (more precise)
            </label>
          </div>

          <div className="mt-8">
            {search.isError ? (
              <p className="text-sm text-destructive">{errorMessage(search.error)}</p>
            ) : !data ? (
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                Try:
                {EXAMPLES.map((e) => (
                  <button
                    key={e}
                    onClick={() => {
                      setQuery(e);
                      run(e);
                    }}
                    className="rounded-full border border-border px-2.5 py-1 hover:border-primary/40 hover:text-foreground"
                  >
                    {e}
                  </button>
                ))}
              </div>
            ) : (
              <div className={cn("space-y-3", search.isPending && "opacity-60")}>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>
                    {data.results.length} passages
                    {data.timings.total_ms ? ` · ${(data.timings.total_ms / 1000).toFixed(1)}s` : ""}
                  </span>
                  {data.search_query !== data.query && (
                    <span className="truncate pl-4">Expanded to “{data.search_query}”</span>
                  )}
                </div>
                {!data.grounded && (
                  <div className="flex gap-2 rounded-lg border border-partial/30 bg-partial/8 px-3 py-2 text-[13px]">
                    <AlertTriangleIcon className="mt-0.5 size-4 shrink-0 text-partial" />
                    No passage is a strong match — these results may be only loosely related.
                  </div>
                )}
                {data.results.map((s) => (
                  <SourceCard
                    key={s.chunk_id}
                    source={s}
                    showNumber={false}
                    action={
                      <Link
                        href={`/?q=${encodeURIComponent(
                          `Explain ${s.section ? `“${s.section.split(" › ").pop()}”` : "this passage"} (${s.doc_name}, page ${s.page_number})`,
                        )}`}
                        className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                      >
                        <MessageSquarePlusIcon className="size-3.5" /> Ask
                      </Link>
                    }
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
