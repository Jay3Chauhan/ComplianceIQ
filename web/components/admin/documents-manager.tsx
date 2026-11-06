"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  BookOpenIcon,
  CircleAlertIcon,
  CircleCheckIcon,
  CircleDashedIcon,
  FileXIcon,
  Loader2Icon,
  MoreHorizontalIcon,
  PencilIcon,
  PlusIcon,
  RefreshCwIcon,
  SearchIcon,
  Trash2Icon,
} from "lucide-react";
import { AdminHeader, Panel, Progress, useAdminAuthRedirect } from "@/components/admin/admin-header";
import { DeleteDocumentDialog, EditDocumentDialog, UploadDialog } from "@/components/admin/document-dialogs";
import { RegulatorBadge } from "@/components/common/regulator-badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import type { DocumentSummary, IngestJob } from "@/lib/api/types";
import { isActiveJob, useJobs, useReindexDocument } from "@/lib/admin-queries";
import { formatDate, relativeTime } from "@/lib/format";
import { useDocuments } from "@/lib/queries";
import { cn } from "@/lib/utils";

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  parsing: "Parsing PDF",
  chunking: "Chunking",
  embedding: "Embedding",
  storing: "Writing vectors",
  done: "Done",
};

function stageLabel(job: IngestJob) {
  if (job.status === "queued") return "Queued";
  return (job.stage && STAGE_LABELS[job.stage]) || job.stage || job.status;
}

function DocStatus({ doc, job }: { doc: DocumentSummary; job?: IngestJob }) {
  if (job && isActiveJob(job)) {
    return (
      <div className="w-32 space-y-1">
        <span className="flex items-center gap-1.5 text-xs text-primary">
          <Loader2Icon className="size-3.5 animate-spin" /> {stageLabel(job)}
        </span>
        <Progress value={job.progress} />
      </div>
    );
  }
  if (job?.status === "failed") {
    return (
      <span className="flex items-center gap-1.5 text-xs text-unverified" title={job.error ?? ""}>
        <CircleAlertIcon className="size-3.5" /> Failed
      </span>
    );
  }
  if (!doc.has_file && !doc.indexed) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <FileXIcon className="size-3.5" /> No PDF
      </span>
    );
  }
  return doc.indexed ? (
    <span className="flex items-center gap-1.5 text-xs text-verified">
      <CircleCheckIcon className="size-3.5" /> Indexed
    </span>
  ) : (
    <span className="flex items-center gap-1.5 text-xs text-partial">
      <CircleDashedIcon className="size-3.5" /> Not indexed
    </span>
  );
}

function JobsPanel({ jobs }: { jobs: IngestJob[] }) {
  if (!jobs.length) return null;
  return (
    <Panel title="Jobs" description="Ingestion runs one document at a time in the background." className="mt-6">
      <ul className="divide-y divide-border">
        {jobs.slice(0, 8).map((job) => (
          <li key={job.id} className="flex items-center gap-3 py-2.5 text-sm">
            {isActiveJob(job) ? (
              <Loader2Icon className="size-4 shrink-0 animate-spin text-primary" />
            ) : job.status === "succeeded" ? (
              <CircleCheckIcon className="size-4 shrink-0 text-verified" />
            ) : (
              <CircleAlertIcon className="size-4 shrink-0 text-unverified" />
            )}
            <div className="min-w-0 flex-1">
              <p className="truncate font-mono text-xs">{job.filename}</p>
              {job.error ? (
                <p className="truncate text-xs text-unverified" title={job.error}>
                  {job.error}
                </p>
              ) : job.status === "succeeded" && job.result ? (
                <p className="text-xs text-muted-foreground">
                  {String(job.result.pages ?? "?")} pages · {String(job.result.chunks ?? "?")} passages
                </p>
              ) : null}
            </div>
            {isActiveJob(job) ? (
              <div className="w-32 space-y-1 sm:w-48">
                <p className="text-right text-xs text-muted-foreground">
                  {stageLabel(job)} · {Math.round(job.progress * 100)}%
                </p>
                <Progress value={job.progress} />
              </div>
            ) : (
              <span className="shrink-0 text-xs text-muted-foreground">{relativeTime(job.finished_at ?? job.created_at)}</span>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function DocumentsManager() {
  const docs = useDocuments();
  const jobs = useJobs();
  const reindex = useReindexDocument();
  useAdminAuthRedirect(jobs.error);
  const [text, setText] = useState("");
  const [uploading, setUploading] = useState(false);
  const [editing, setEditing] = useState<DocumentSummary | null>(null);
  const [deleting, setDeleting] = useState<DocumentSummary | null>(null);

  const latestJob = useMemo(() => {
    const map = new Map<string, IngestJob>();
    for (const job of jobs.data ?? []) if (!map.has(job.doc_id)) map.set(job.doc_id, job);
    return map;
  }, [jobs.data]);

  const items = useMemo(() => {
    const q = text.trim().toLowerCase();
    return (docs.data ?? []).filter(
      (d) => !q || `${d.name} ${d.circular_id} ${d.subcategory} ${d.filename} ${d.category}`.toLowerCase().includes(q),
    );
  }, [docs.data, text]);

  const indexed = (docs.data ?? []).filter((d) => d.indexed).length;
  const passages = (docs.data ?? []).reduce((n, d) => n + d.chunks, 0);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <AdminHeader active="documents" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl px-4 py-8">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight">Documents</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {docs.data
                  ? `${docs.data.length} registered · ${indexed} indexed · ${passages.toLocaleString()} passages`
                  : "Upload, edit and re-index the regulatory corpus."}
              </p>
            </div>
            <div className="flex w-full gap-2 sm:w-auto">
              <div className="relative flex-1 sm:w-64">
                <SearchIcon className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Filter…"
                  aria-label="Filter documents"
                  className="h-9 w-full rounded-lg border border-border bg-card pr-3 pl-9 text-sm outline-none focus:border-primary/40 focus:ring-3 focus:ring-primary/10"
                />
              </div>
              <Button className="h-9" onClick={() => setUploading(true)}>
                <PlusIcon /> Add PDF
              </Button>
            </div>
          </div>

          <JobsPanel jobs={jobs.data ?? []} />

          <div className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">Document</th>
                    <th className="hidden px-4 py-2.5 font-medium md:table-cell">Issued</th>
                    <th className="px-4 py-2.5 text-right font-medium">Passages</th>
                    <th className="px-4 py-2.5 font-medium">Status</th>
                    <th className="w-12 px-2 py-2.5">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {docs.isPending
                    ? Array.from({ length: 5 }, (_, i) => (
                        <tr key={i}>
                          <td colSpan={5} className="px-4 py-3">
                            <Skeleton className="h-9" />
                          </td>
                        </tr>
                      ))
                    : items.map((d) => {
                        const job = latestJob.get(d.doc_id);
                        const busy = !!job && isActiveJob(job);
                        return (
                          <tr key={d.doc_id} className="transition-colors hover:bg-muted/30">
                            <td className="w-full max-w-0 px-4 py-3">
                              <div className="flex items-start gap-2">
                                <RegulatorBadge category={d.category} className="mt-px" />
                                <span className="line-clamp-2 leading-snug font-medium" title={d.name}>
                                  {d.name}
                                </span>
                              </div>
                              <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground" title={d.filename}>
                                {d.circular_id || d.filename}
                              </p>
                            </td>
                            <td className="hidden px-4 py-3 whitespace-nowrap text-muted-foreground md:table-cell">
                              {formatDate(d.date) || "—"}
                            </td>
                            <td className="px-4 py-3 text-right tabular-nums">{d.chunks.toLocaleString()}</td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <DocStatus doc={d} job={job} />
                            </td>
                            <td className="px-2 py-3">
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${d.name}`}>
                                    <MoreHorizontalIcon />
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-44">
                                  <DropdownMenuItem asChild disabled={!d.indexed}>
                                    <Link href={`/documents/${encodeURIComponent(d.doc_id)}`}>
                                      <BookOpenIcon /> Open in library
                                    </Link>
                                  </DropdownMenuItem>
                                  <DropdownMenuItem onSelect={() => setEditing(d)}>
                                    <PencilIcon /> Edit metadata
                                  </DropdownMenuItem>
                                  <DropdownMenuItem disabled={!d.has_file || busy} onSelect={() => reindex.mutate(d.doc_id)}>
                                    <RefreshCwIcon /> Re-index
                                  </DropdownMenuItem>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem variant="destructive" disabled={busy} onSelect={() => setDeleting(d)}>
                                    <Trash2Icon /> Remove
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </td>
                          </tr>
                        );
                      })}
                </tbody>
              </table>
            </div>
            {docs.data && items.length === 0 && (
              <p className={cn("py-12 text-center text-sm text-muted-foreground")}>
                {text ? "No documents match." : "No documents yet. Add a PDF to get started."}
              </p>
            )}
            {docs.isError && <p className="py-12 text-center text-sm text-muted-foreground">Couldn’t load documents. Is the API running?</p>}
          </div>
        </div>
      </div>

      <UploadDialog open={uploading} onOpenChange={setUploading} />
      <EditDocumentDialog doc={editing} onClose={() => setEditing(null)} />
      <DeleteDocumentDialog doc={deleting} onClose={() => setDeleting(null)} />
    </div>
  );
}
