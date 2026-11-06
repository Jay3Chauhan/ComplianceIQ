"use client";

import { create } from "zustand";
import { toast } from "sonner";
import { ApiError, api, errorMessage } from "@/lib/api/client";
import type { ChatRequest, ConversationDetail, RegenerateRequest, StreamEvent } from "@/lib/api/types";
import { initialAnswer, reduce, type ActiveAnswer } from "@/lib/chat/reducer";
import { streamSSE } from "@/lib/chat/sse";
import { keys, patchConversationLists } from "@/lib/queries";
import { getQueryClient } from "@/lib/query-client";

/** An answer being generated (or just finished, until the saved message replaces it). */
export interface Run {
  id: string;
  conversationId: string | null;
  question: string;
  userMessageId: string | null;
  answer: ActiveAnswer;
  stopping: boolean;
}

export type StartArgs =
  | { kind: "send"; request: ChatRequest }
  | { kind: "regenerate"; conversationId: string; messageId: string; userMessageId: string; question: string; body?: RegenerateRequest }
  | { kind: "edit"; conversationId: string; messageId: string; question: string; body?: RegenerateRequest };

interface ChatState {
  runs: Record<string, Run>;
  /** Starts a stream. `accepted` resolves false if the request was rejected (409, 429, …). */
  start: (args: StartArgs) => { runId: string; accepted: Promise<boolean> };
  stop: (runId: string) => void;
}

const STALL_MS = 30_000; // > 2 × the backend's 10s heartbeat
const FLUSH_MS = 40;
const controllers = new Map<string, AbortController>();

export const useChatStore = create<ChatState>()((set, get) => {
  const patchRun = (id: string, fn: (r: Run) => Partial<Run>) =>
    set((s) => (s.runs[id] ? { runs: { ...s.runs, [id]: { ...s.runs[id], ...fn(s.runs[id]) } } } : s));
  const removeRun = (id: string) =>
    set((s) => {
      const runs = { ...s.runs };
      delete runs[id];
      return { runs };
    });

  return {
    runs: {},

    start(args) {
      const qc = getQueryClient();
      const runId = crypto.randomUUID();
      const controller = new AbortController();
      controllers.set(runId, controller);

      let path: string;
      let body: unknown;
      let conversationId: string | null;
      let userMessageId: string | null = null;
      if (args.kind === "send") {
        path = "chat/stream";
        body = args.request;
        conversationId = args.request.conversation_id ?? null;
      } else if (args.kind === "regenerate") {
        path = `messages/${args.messageId}/regenerate`;
        body = args.body ?? {};
        conversationId = args.conversationId;
        userMessageId = args.userMessageId;
      } else {
        path = `messages/${args.messageId}/edit`;
        body = { ...args.body, question: args.question };
        conversationId = args.conversationId;
        userMessageId = args.messageId;
      }
      const question = args.kind === "send" ? args.request.question : args.question;

      // Regenerate/edit remove later messages on the server; mirror that now so the UI doesn't jump.
      const snapshot = conversationId
        ? qc.getQueryData<ConversationDetail>(keys.conversation(conversationId))
        : undefined;
      if (snapshot && args.kind !== "send") {
        const idx = snapshot.messages.findIndex((m) => m.id === args.messageId);
        if (idx >= 0) {
          const keep = args.kind === "regenerate" ? idx : idx + 1;
          qc.setQueryData<ConversationDetail>(keys.conversation(snapshot.id), {
            ...snapshot,
            messages: snapshot.messages.slice(0, keep),
          });
        }
      }

      set((s) => ({
        runs: {
          ...s.runs,
          [runId]: { id: runId, conversationId, question, userMessageId, answer: initialAnswer, stopping: false },
        },
      }));

      let resolveAccepted!: (ok: boolean) => void;
      const accepted = new Promise<boolean>((r) => (resolveAccepted = r));

      // Batch stream events: one store update per FLUSH_MS instead of one per token.
      let queue: StreamEvent[] = [];
      let timer: ReturnType<typeof setTimeout> | null = null;
      const flush = () => {
        if (timer) clearTimeout(timer);
        timer = null;
        if (!queue.length) return;
        const events = queue;
        queue = [];
        patchRun(runId, (r) => {
          let answer = r.answer;
          const extra: Partial<Run> = {};
          for (const e of events) {
            answer = reduce(answer, e);
            if (e.type === "conversation") {
              extra.conversationId = e.conversation_id;
              extra.userMessageId = e.user_message_id;
            }
          }
          return { ...extra, answer };
        });
      };

      let stall: ReturnType<typeof setTimeout> | undefined;
      const alive = () => {
        clearTimeout(stall);
        stall = setTimeout(() => controller.abort("stalled"), STALL_MS);
      };

      const run = async () => {
        let done = false;
        let first = true;
        try {
          alive();
          for await (const e of streamSSE(path, body, controller.signal, alive)) {
            if (first) {
              first = false;
              resolveAccepted(true);
            }
            queue.push(e);
            if (e.type === "conversation") {
              flush();
              qc.invalidateQueries({ queryKey: keys.conversationsAll });
            } else if (e.type === "title") {
              qc.setQueryData<ConversationDetail>(keys.conversation(e.conversation_id), (old) =>
                old ? { ...old, title: e.title } : old,
              );
              patchConversationLists(qc, e.conversation_id, { title: e.title });
            } else if (e.type === "done") {
              done = true;
              flush();
            } else if (!timer) {
              timer = setTimeout(flush, FLUSH_MS);
            }
          }
          flush();
        } catch (err) {
          flush();
          if (err instanceof ApiError) {
            if (snapshot) qc.setQueryData(keys.conversation(snapshot.id), snapshot);
            removeRun(runId);
            controllers.delete(runId);
            clearTimeout(stall);
            resolveAccepted(false);
            notifyRejected(err, conversationId);
            return;
          }
          // Aborted (Stop / stall) or the network dropped: the server keeps what it generated.
        } finally {
          clearTimeout(stall);
        }
        resolveAccepted(true);

        const reason = controller.signal.reason;
        if (!done) {
          patchRun(runId, (r) => ({
            answer: {
              ...r.answer,
              stage: reason === "stop" || r.stopping ? "stopped" : "error",
              error:
                reason === "stop" || r.stopping
                  ? null
                  : { code: "connection_lost", message: "The connection was interrupted." },
            },
          }));
        }
        controllers.delete(runId);

        const cid = get().runs[runId]?.conversationId;
        if (cid) {
          if (!done) await waitUntilIdle(cid);
          await qc.invalidateQueries({ queryKey: keys.conversation(cid) });
          qc.invalidateQueries({ queryKey: keys.conversationsAll });
          removeRun(runId);
        } else if (!done) {
          removeRun(runId);
        }
      };
      void run();
      return { runId, accepted };
    },

    stop(runId) {
      const run = get().runs[runId];
      const controller = controllers.get(runId);
      if (!run || !controller) return;
      patchRun(runId, () => ({ stopping: true }));
      if (run.conversationId) {
        // The stream ends with done{status:"stopped"}; abort only if that doesn't arrive.
        api(`conversations/${run.conversationId}/stop`, { method: "POST" }).catch(() => controller.abort("stop"));
        setTimeout(() => controllers.get(runId)?.abort("stop"), 8000);
      } else {
        controller.abort("stop");
      }
    },
  };
});

async function waitUntilIdle(conversationId: string, timeoutMs = 10_000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try {
      const conv = await api<ConversationDetail>(`conversations/${conversationId}`);
      if (!conv.streaming) return;
    } catch {
      return;
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

function notifyRejected(err: ApiError, conversationId: string | null) {
  if (err.code === "conversation_busy" && conversationId) {
    toast("An answer is still being generated in this conversation.", {
      description: "Stop it, or wait for it to finish.",
      action: {
        label: "Stop it",
        onClick: () => void api(`conversations/${conversationId}/stop`, { method: "POST" }).catch(() => {}),
      },
    });
  } else {
    toast.error(errorMessage(err));
  }
}

/** Selectors */
export const runForConversation = (conversationId: string) => (s: ChatState) =>
  Object.values(s.runs).find((r) => r.conversationId === conversationId) ?? null;

export const anyRunActive = (s: ChatState) => Object.keys(s.runs).length > 0;
