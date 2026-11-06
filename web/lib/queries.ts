"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorMessage } from "@/lib/api/client";
import type {
  Conversation,
  ConversationDetail,
  DocumentOutline,
  DocumentPage,
  DocumentSummary,
  Feedback,
  Meta,
  Paginated,
  SearchResponse,
} from "@/lib/api/types";

export const keys = {
  meta: ["meta"] as const,
  suggestions: (category: string) => ["suggestions", category] as const,
  conversations: (q: string, archived: boolean) => ["conversations", q, archived] as const,
  conversationsAll: ["conversations"] as const,
  conversation: (id: string) => ["conversation", id] as const,
  documents: ["documents"] as const,
  document: (id: string) => ["document", id] as const,
  outline: (id: string) => ["outline", id] as const,
  page: (id: string, n: number) => ["page", id, n] as const,
};

export function useMeta() {
  return useQuery({ queryKey: keys.meta, queryFn: () => api<Meta>("meta"), staleTime: 3_600_000 });
}

export function useSuggestions(category: string) {
  return useQuery({
    queryKey: keys.suggestions(category),
    queryFn: () => api<{ suggestions: string[] }>(`suggestions?category=${category}&limit=4`),
    staleTime: 3_600_000,
    select: (d) => d.suggestions,
  });
}

const PAGE = 30;

export function useConversations(q: string, archived = false) {
  return useInfiniteQuery({
    queryKey: keys.conversations(q, archived),
    queryFn: ({ pageParam }) =>
      api<Paginated<Conversation>>(
        `conversations?limit=${PAGE}&offset=${pageParam}&archived=${archived}${q ? `&q=${encodeURIComponent(q)}` : ""}`,
      ),
    initialPageParam: 0,
    getNextPageParam: (last) => (last.offset + last.items.length < last.total ? last.offset + PAGE : undefined),
  });
}

export function useConversation(id: string | null, opts: { poll?: boolean } = {}) {
  return useQuery({
    queryKey: keys.conversation(id ?? "none"),
    queryFn: () => api<ConversationDetail>(`conversations/${id}`),
    enabled: !!id,
    staleTime: 0,
    refetchInterval: (query) => (opts.poll && query.state.data?.streaming ? 2000 : false),
  });
}

export function useDocuments() {
  return useQuery({ queryKey: keys.documents, queryFn: () => api<DocumentSummary[]>("documents"), staleTime: 300_000 });
}

export function useDocument(id: string) {
  return useQuery({
    queryKey: keys.document(id),
    queryFn: () => api<DocumentSummary>(`documents/${encodeURIComponent(id)}`),
    staleTime: 600_000,
  });
}

export function useOutline(id: string) {
  return useQuery({
    queryKey: keys.outline(id),
    queryFn: () => api<DocumentOutline>(`documents/${encodeURIComponent(id)}/outline`),
    staleTime: 600_000,
  });
}

export function useDocumentPage(id: string, page: number) {
  return useQuery({
    queryKey: keys.page(id, page),
    queryFn: () => api<DocumentPage>(`documents/${encodeURIComponent(id)}/pages/${page}`),
    staleTime: 600_000,
    placeholderData: (prev) => prev,
  });
}

export function useSearch() {
  return useMutation({
    mutationFn: (body: { query: string; category: string; top_k?: number; rerank?: boolean }) =>
      api<SearchResponse>("search", { body }),
  });
}

/** Rename / pin / archive / change settings, with an optimistic sidebar update. */
export function useUpdateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Conversation> }) =>
      api<Conversation>(`conversations/${id}`, { method: "PATCH", body: patch }),
    onMutate: async ({ id, patch }) => {
      qc.setQueryData<ConversationDetail>(keys.conversation(id), (old) => (old ? { ...old, ...patch } : old));
      patchConversationLists(qc, id, patch);
    },
    onError: (err) => toast.error(errorMessage(err)),
    onSettled: (_d, _e, { id }) => {
      qc.invalidateQueries({ queryKey: keys.conversationsAll });
      qc.invalidateQueries({ queryKey: keys.conversation(id) });
    },
  });
}

export function useDeleteConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`conversations/${id}`, { method: "DELETE" }),
    onSuccess: (_d, id) => {
      qc.removeQueries({ queryKey: keys.conversation(id) });
      qc.invalidateQueries({ queryKey: keys.conversationsAll });
    },
    onError: (err) => toast.error(errorMessage(err)),
  });
}

export function useFeedback(conversationId: string, messageId: string) {
  const qc = useQueryClient();
  const setLocal = (feedback: Feedback | null) =>
    qc.setQueryData<ConversationDetail>(keys.conversation(conversationId), (old) =>
      old ? { ...old, messages: old.messages.map((m) => (m.id === messageId ? { ...m, feedback } : m)) } : old,
    );
  return useMutation({
    mutationFn: async (feedback: Feedback | null) => {
      if (feedback) await api(`messages/${messageId}/feedback`, { method: "PUT", body: feedback });
      else await api(`messages/${messageId}/feedback`, { method: "DELETE" });
    },
    onMutate: (feedback) => setLocal(feedback),
    onError: (err) => {
      toast.error(errorMessage(err));
      qc.invalidateQueries({ queryKey: keys.conversation(conversationId) });
    },
  });
}

type InfiniteConversations = { pages: Paginated<Conversation>[]; pageParams: number[] };

export function patchConversationLists(
  qc: ReturnType<typeof useQueryClient>,
  id: string,
  patch: Partial<Conversation>,
) {
  qc.setQueriesData<InfiniteConversations>({ queryKey: keys.conversationsAll }, (old) =>
    old
      ? {
          ...old,
          pages: old.pages.map((p) => ({ ...p, items: p.items.map((c) => (c.id === id ? { ...c, ...patch } : c)) })),
        }
      : old,
  );
}
