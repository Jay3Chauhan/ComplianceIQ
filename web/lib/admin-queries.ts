"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api/client";
import type { AdminSession, AdminStats, DocumentMetadata, DocumentSummary, IngestJob, UploadResult } from "@/lib/api/types";
import { keys } from "@/lib/queries";

export const adminKeys = {
  session: ["admin", "session"] as const,
  stats: (days: number) => ["admin", "stats", days] as const,
  jobs: ["admin", "jobs"] as const,
};

const ACTIVE = new Set<IngestJob["status"]>(["queued", "running"]);

export function isActiveJob(job: IngestJob) {
  return ACTIVE.has(job.status);
}

export function useAdminSession() {
  return useQuery({
    queryKey: adminKeys.session,
    queryFn: () => api<AdminSession>("admin-session"),
    staleTime: 60_000,
    retry: false,
  });
}

export function useAdminLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (password: string) => api<AdminSession>("admin-session", { body: { password } }),
    onSuccess: (session) => qc.setQueryData(adminKeys.session, session),
  });
}

export function useAdminLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<AdminSession>("admin-session", { method: "DELETE" }),
    onSuccess: (session) => {
      qc.setQueryData(adminKeys.session, session);
      qc.removeQueries({ queryKey: ["admin", "stats"] });
      qc.removeQueries({ queryKey: adminKeys.jobs });
    },
  });
}

export function useAdminStats(days: number) {
  return useQuery({
    queryKey: adminKeys.stats(days),
    queryFn: () => api<AdminStats>(`admin/stats?days=${days}`),
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  });
}

/** Recent ingest jobs; polls every 2s while any job is queued or running. */
export function useJobs() {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: adminKeys.jobs,
    queryFn: () => api<IngestJob[]>("admin/jobs?limit=20"),
    refetchInterval: (q) => (q.state.data?.some(isActiveJob) ? 2000 : false),
  });

  // When a job finishes, the library (chunks / indexed) and stats are out of date.
  const active = useRef<Set<string>>(new Set());
  useEffect(() => {
    const jobs = query.data ?? [];
    const finished = jobs.filter((j) => active.current.has(j.id) && !isActiveJob(j));
    for (const job of finished) {
      if (job.status === "succeeded") toast.success(`Indexed ${job.filename}`);
      else toast.error(`Indexing ${job.filename} failed`, { description: job.error ?? undefined });
    }
    if (finished.length) {
      qc.invalidateQueries({ queryKey: keys.documents });
      qc.invalidateQueries({ queryKey: ["admin", "stats"] });
    }
    active.current = new Set(jobs.filter(isActiveJob).map((j) => j.id));
  }, [query.data, qc]);

  return query;
}

function useAfterJobQueued() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: adminKeys.jobs });
    qc.invalidateQueries({ queryKey: keys.documents });
  };
}

export function useUploadDocument() {
  const after = useAfterJobQueued();
  return useMutation({
    mutationFn: ({ file, meta, replace }: { file: File; meta: DocumentMetadata; replace: boolean }) => {
      const form = new FormData();
      form.set("file", file);
      for (const [k, v] of Object.entries(meta)) form.set(k, v);
      form.set("replace", String(replace));
      return api<UploadResult>("admin/documents", { body: form });
    },
    onSuccess: after,
  });
}

export function useUpdateDocument() {
  const qc = useQueryClient();
  const after = useAfterJobQueued();
  return useMutation({
    mutationFn: ({ docId, patch }: { docId: string; patch: Partial<DocumentMetadata> }) =>
      api<{ document: DocumentSummary; job: IngestJob | null }>(`admin/documents/${encodeURIComponent(docId)}`, {
        method: "PATCH",
        body: patch,
      }),
    onSuccess: (_d, { docId }) => {
      qc.invalidateQueries({ queryKey: keys.document(docId) });
      after();
    },
  });
}

export function useReindexDocument() {
  const after = useAfterJobQueued();
  return useMutation({
    mutationFn: (docId: string) => api<IngestJob>(`admin/documents/${encodeURIComponent(docId)}/reindex`, { method: "POST" }),
    onSuccess: after,
    onError: (err) => toast.error(errorMessage(err)),
  });
}

export function useReindexAll() {
  const after = useAfterJobQueued();
  return useMutation({
    mutationFn: () => api<{ jobs: IngestJob[] }>("admin/reindex", { method: "POST" }),
    onSuccess: ({ jobs }) => {
      toast.success(`Queued ${jobs.length} re-index job${jobs.length === 1 ? "" : "s"}.`);
      after();
    },
    onError: (err) => toast.error(errorMessage(err)),
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ docId, deleteFile }: { docId: string; deleteFile: boolean }) =>
      api<{ deleted: boolean; file_deleted: boolean }>(
        `admin/documents/${encodeURIComponent(docId)}?delete_file=${deleteFile}`,
        { method: "DELETE" },
      ),
    onSuccess: (_d, { docId }) => {
      qc.removeQueries({ queryKey: keys.document(docId) });
      qc.invalidateQueries({ queryKey: keys.documents });
      qc.invalidateQueries({ queryKey: ["admin", "stats"] });
    },
  });
}

export function useClearCache() {
  return useMutation({
    mutationFn: () => api<void>("admin/cache/clear", { method: "POST" }),
    onSuccess: () => toast.success("Retrieval and answer caches cleared."),
    onError: (err) => toast.error(errorMessage(err)),
  });
}
