"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeftIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  DownloadIcon,
  ExternalLinkIcon,
  ListTreeIcon,
  MessageSquarePlusIcon,
} from "lucide-react";
import { RegulatorBadge } from "@/components/common/regulator-badge";
import { TopBar } from "@/components/shell/top-bar";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDate } from "@/lib/format";
import { useDocument, useDocumentPage, useOutline } from "@/lib/queries";
import { cn } from "@/lib/utils";

export function DocumentReader({ docId }: { docId: string }) {
  const router = useRouter();
  const params = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const chunk = params.get("chunk");
  const doc = useDocument(docId);
  const outline = useOutline(docId);
  const pageQuery = useDocumentPage(docId, page);
  const totalPages = pageQuery.data?.total_pages ?? null;
  const [pageInput, setPageInput] = useState(String(page));
  const [tab, setTab] = useState("passages");
  const [outlineOpen, setOutlineOpen] = useState(false);
  const highlightRef = useRef<HTMLDivElement>(null);

  const [shownPage, setShownPage] = useState(page);
  if (shownPage !== page) {
    setShownPage(page);
    setPageInput(String(page));
  }
  const docName = doc.data?.name;
  useEffect(() => {
    if (docName) document.title = `${docName} · ComplianceIQ`;
  }, [docName]);

  useEffect(() => {
    if (chunk && pageQuery.data) {
      requestAnimationFrame(() => highlightRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }));
    }
  }, [chunk, pageQuery.data]);

  const go = (n: number, keepChunk = false) => {
    const target = Math.max(1, totalPages ? Math.min(totalPages, n) : n);
    const q = new URLSearchParams({ page: String(target) });
    if (keepChunk && chunk) q.set("chunk", chunk);
    router.replace(`/documents/${encodeURIComponent(docId)}?${q}`, { scroll: false });
    setOutlineOpen(false);
  };

  const currentSection = useMemo(() => {
    const sections = outline.data?.sections ?? [];
    return [...sections].reverse().find((s) => s.page_number <= page)?.section ?? null;
  }, [outline.data, page]);

  const outlineList = (
    <nav aria-label="Document outline" className="space-y-px p-2">
      {outline.isPending
        ? Array.from({ length: 10 }, (_, i) => <Skeleton key={i} className="m-1 h-5" />)
        : (outline.data?.sections ?? []).map((s, i) => (
            <button
              key={`${s.section}-${i}`}
              onClick={() => go(s.page_number)}
              className={cn(
                "flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-[12.5px] leading-snug transition-colors",
                s.section === currentSection
                  ? "bg-primary/8 font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <span className="line-clamp-2 flex-1">{s.section.split(" › ").pop()}</span>
              <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground/80">{s.page_number}</span>
            </button>
          ))}
    </nav>
  );

  const d = doc.data;
  const askHref = d ? `/?q=${encodeURIComponent(`Summarise the key obligations in ${d.name}`)}` : "/";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <TopBar
        actions={
          <>
            <Button variant="ghost" size="sm" className="lg:hidden" onClick={() => setOutlineOpen(true)}>
              <ListTreeIcon /> Outline
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link href={askHref}>
                <MessageSquarePlusIcon /> <span className="hidden sm:inline">Ask about this</span>
              </Link>
            </Button>
          </>
        }
      >
        <Link href="/documents" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeftIcon className="size-4" /> Library
        </Link>
      </TopBar>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-72 shrink-0 border-r border-border lg:block">
          <ScrollArea className="h-full">
            <p className="px-4 pt-4 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">Outline</p>
            {outlineList}
          </ScrollArea>
        </aside>
        <Sheet open={outlineOpen} onOpenChange={setOutlineOpen}>
          <SheetContent side="left" className="w-[85vw] max-w-xs gap-0 p-0">
            <SheetTitle className="px-4 pt-4 text-sm">Outline</SheetTitle>
            <ScrollArea className="min-h-0 flex-1">{outlineList}</ScrollArea>
          </SheetContent>
        </Sheet>

        <div className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-3xl px-4 py-6">
            {d ? (
              <div className="animate-fade-up">
                <div className="flex items-center gap-2">
                  <RegulatorBadge category={d.category} />
                  <span className="text-xs text-muted-foreground">
                    {[d.issuer, formatDate(d.date)].filter(Boolean).join(" · ")}
                  </span>
                </div>
                <h1 className="mt-2 text-xl font-semibold tracking-tight text-balance">{d.name}</h1>
                {d.circular_id && <p className="mt-1 font-mono text-xs text-muted-foreground">{d.circular_id}</p>}
                <div className="mt-4 flex flex-wrap gap-2">
                  {d.has_file && (
                    <Button variant="outline" size="sm" asChild>
                      <a href={`/api/documents/${encodeURIComponent(docId)}/file`} target="_blank" rel="noopener noreferrer">
                        <DownloadIcon /> PDF
                      </a>
                    </Button>
                  )}
                  {d.source_url && (
                    <Button variant="ghost" size="sm" asChild>
                      <a href={d.source_url} target="_blank" rel="noopener noreferrer">
                        Official source <ExternalLinkIcon />
                      </a>
                    </Button>
                  )}
                </div>
              </div>
            ) : doc.isError ? (
              <p className="py-10 text-sm text-muted-foreground">Document not found.</p>
            ) : (
              <div className="space-y-2">
                <Skeleton className="h-5 w-24" />
                <Skeleton className="h-7 w-3/4" />
              </div>
            )}

            <Tabs value={tab} onValueChange={setTab} className="mt-6">
              <div className="sticky top-0 z-10 -mx-4 flex flex-wrap items-center gap-3 bg-background/90 px-4 py-2 backdrop-blur">
                <TabsList>
                  <TabsTrigger value="passages">Passages</TabsTrigger>
                  {d?.has_file && <TabsTrigger value="pdf">PDF</TabsTrigger>}
                </TabsList>
                <div className="ml-auto flex items-center gap-1">
                  <Button variant="ghost" size="icon-sm" aria-label="Previous page" disabled={page <= 1} onClick={() => go(page - 1)}>
                    <ChevronLeftIcon />
                  </Button>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      go(Number(pageInput) || 1);
                    }}
                    className="flex items-center gap-1.5 text-sm text-muted-foreground"
                  >
                    Page
                    <input
                      value={pageInput}
                      onChange={(e) => setPageInput(e.target.value.replace(/\D/g, ""))}
                      aria-label="Page number"
                      className="h-7 w-12 rounded-md border border-border bg-card text-center text-sm text-foreground outline-none focus:border-primary/40"
                    />
                    {totalPages && <span>of {totalPages}</span>}
                  </form>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Next page"
                    disabled={!!totalPages && page >= totalPages}
                    onClick={() => go(page + 1)}
                  >
                    <ChevronRightIcon />
                  </Button>
                </div>
              </div>

              <TabsContent value="passages" className="mt-4">
                {pageQuery.isPending ? (
                  <div className="space-y-3">
                    {Array.from({ length: 3 }, (_, i) => (
                      <Skeleton key={i} className="h-28 rounded-xl" />
                    ))}
                  </div>
                ) : (pageQuery.data?.passages.length ?? 0) === 0 ? (
                  <p className="rounded-xl border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
                    No indexed text on this page (it may be a cover, table of contents or image).
                  </p>
                ) : (
                  <div className={cn("space-y-3 transition-opacity", pageQuery.isPlaceholderData && "opacity-50")}>
                    {pageQuery.data!.passages.map((p, i, arr) => {
                      const hl = p.chunk_id === chunk;
                      const showSection = p.section && p.section !== arr[i - 1]?.section;
                      return (
                        <div key={p.chunk_id}>
                          {showSection && (
                            <p className="mb-2 text-xs font-medium text-muted-foreground">{p.section}</p>
                          )}
                          <div
                            ref={hl ? highlightRef : undefined}
                            className={cn(
                              "rounded-xl border p-4 text-[14px] leading-7 whitespace-pre-line",
                              hl
                                ? "animate-flash border-primary/50 bg-primary/5 ring-3 ring-primary/10"
                                : "border-border bg-card",
                            )}
                          >
                            {hl && (
                              <span className="mb-2 inline-flex rounded-md bg-primary px-1.5 py-0.5 text-[10.5px] font-semibold text-primary-foreground">
                                Cited passage
                              </span>
                            )}
                            <p>{p.text}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </TabsContent>
              {d?.has_file && (
                <TabsContent value="pdf" className="mt-4">
                  <iframe
                    key={page}
                    title={`${d.name}, page ${page}`}
                    src={`/api/documents/${encodeURIComponent(docId)}/file#page=${page}`}
                    className="h-[75vh] w-full rounded-xl border border-border bg-muted"
                  />
                </TabsContent>
              )}
            </Tabs>
          </div>
        </div>
      </div>
    </div>
  );
}
