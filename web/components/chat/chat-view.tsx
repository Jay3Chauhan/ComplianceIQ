"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowDownIcon, BookOpenCheckIcon, DownloadIcon, Loader2Icon, MessageSquareDashedIcon, SquareIcon } from "lucide-react";
import { AssistantMessage, viewFromMessage, viewFromRun } from "@/components/chat/assistant-message";
import { Composer, type ComposerHandle } from "@/components/chat/composer";
import { EmptyState } from "@/components/chat/empty-state";
import { SourcesPanel } from "@/components/chat/sources-panel";
import { UserMessage } from "@/components/chat/user-message";
import { IconButton } from "@/components/common/icon-button";
import { LogoMark } from "@/components/common/logo";
import { TopBar } from "@/components/shell/top-bar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api } from "@/lib/api/client";
import type { AnswerMode, Category, Message, RegenerateRequest } from "@/lib/api/types";
import { runForConversation, useChatStore } from "@/lib/chat/store";
import { downloadConversation } from "@/lib/export";
import { categoryLabel } from "@/lib/format";
import { useConversation } from "@/lib/queries";
import { useSettings } from "@/lib/settings";
import { useUI } from "@/lib/ui";
import { cn } from "@/lib/utils";

const STICK_PX = 96;

export function ChatView({ conversationId }: { conversationId: string | null }) {
  const router = useRouter();
  const settings = useSettings();
  const start = useChatStore((s) => s.start);
  const stopRun = useChatStore((s) => s.stop);
  const [draftRunId, setDraftRunId] = useState<string | null>(null);
  const run = useChatStore(
    useCallback(
      (s: Parameters<ReturnType<typeof runForConversation>>[0]) =>
        conversationId ? runForConversation(conversationId)(s) : draftRunId ? (s.runs[draftRunId] ?? null) : null,
      [conversationId, draftRunId],
    ),
  );
  const conv = useConversation(conversationId, { poll: !run });
  const detail = conv.data;
  const { showSources, syncSources, sourcesOpen, setSourcesOpen } = useUI();

  // Composer settings: what the user picked here, else the conversation's saved ones, else the defaults.
  const [picked, setPicked] = useState<{ category?: Category; answerMode?: AnswerMode }>({});
  const category = picked.category ?? detail?.category ?? settings.category;
  const answerMode = picked.answerMode ?? detail?.answer_mode ?? settings.answerMode;
  const setCategory = (c: Category) => setPicked((p) => ({ ...p, category: c }));
  const setAnswerMode = (m: AnswerMode) => setPicked((p) => ({ ...p, answerMode: m }));
  const [editingId, setEditingId] = useState<string | null>(null);
  const composer = useRef<ComposerHandle>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const [atBottom, setAtBottom] = useState(true);

  // A new chat gets its URL as soon as the server creates the conversation.
  useEffect(() => {
    if (!conversationId && run?.conversationId) router.replace(`/c/${run.conversationId}`, { scroll: false });
  }, [conversationId, run?.conversationId, router]);

  // Visited routes stay mounted but hidden; the new-chat page must be blank when shown again.
  useLayoutEffect(() => {
    if (conversationId) return;
    return () => {
      setDraftRunId(null);
      setPicked({});
      setEditingId(null);
    };
  }, [conversationId]);

  useEffect(() => {
    document.title = detail?.title ? `${detail.title} · ComplianceIQ` : "ComplianceIQ";
  }, [detail?.title]);

  // "/?q=…" (from the library or search) pre-fills the composer for a new chat.
  useEffect(() => {
    if (conversationId) return;
    const q = new URLSearchParams(window.location.search).get("q");
    if (!q) return;
    window.history.replaceState(null, "", "/");
    requestAnimationFrame(() => composer.current?.setValue(q.slice(0, 2000)));
  }, [conversationId]);

  // ── Message list ─────────────────────────────────────────────────────────
  const messages = detail?.messages ?? [];
  const hidden = new Set([run?.userMessageId, run?.answer.messageId].filter(Boolean) as string[]);
  const visible = messages.filter((m) => !hidden.has(m.id));
  const pending = !run && !!detail?.streaming;
  const busy = !!run || pending;
  const isEmpty = !conversationId && !run;

  // Auto-open the evidence panel the first time an answer brings sources (wide screens).
  const autoOpened = useRef<Set<string>>(new Set());
  const runSources = run?.answer.mode === "regulatory" ? run.answer.sources : null;
  useEffect(() => {
    if (!run || !runSources?.length) return;
    if (sourcesOpen || autoOpened.current.has(run.id)) {
      if (sourcesOpen) syncSources(run.id, runSources);
      return;
    }
    autoOpened.current.add(run.id);
    if (settings.showSources && window.matchMedia("(min-width: 1280px)").matches) showSources(run.id, runSources);
  }, [run, runSources, sourcesOpen, settings.showSources, showSources, syncSources]);

  // When switching conversations, point an open panel at that conversation's latest sources.
  useEffect(() => {
    if (!detail || run) return;
    const last = [...detail.messages].reverse().find((m) => m.role === "assistant" && m.sources.length);
    const selection = useUI.getState().selection;
    if (last && selection?.owner !== last.id && !detail.messages.some((m) => m.id === selection?.owner)) {
      syncSources(last.id, last.sources);
    }
  }, [detail, run, syncSources]);

  // ── Scrolling ────────────────────────────────────────────────────────────
  const scrollToBottom = useCallback((smooth = false) => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }, []);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const bottom = el.scrollHeight - el.scrollTop - el.clientHeight < STICK_PX;
    stick.current = bottom;
    setAtBottom(bottom);
  };

  useLayoutEffect(() => {
    if (stick.current) scrollToBottom();
  }, [run?.answer.text, run?.answer.stage, run?.answer.followups, visible.length, pending, scrollToBottom]);

  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!detail || loadedFor.current === detail.id) return;
    loadedFor.current = detail.id;
    const hash = window.location.hash;
    const target = hash.startsWith("#m-") ? document.getElementById(hash.slice(1)) : null;
    requestAnimationFrame(() => {
      if (target) {
        stick.current = false;
        target.scrollIntoView({ block: "start" });
      } else {
        stick.current = true;
        scrollToBottom();
      }
    });
  }, [detail, scrollToBottom]);

  // ── Actions ──────────────────────────────────────────────────────────────
  const send = async (question: string): Promise<boolean> => {
    if (busy) return false;
    stick.current = true;
    const { runId, accepted } = start({
      kind: "send",
      request: {
        question,
        conversation_id: conversationId,
        category,
        answer_mode: answerMode,
        followups: settings.followups,
      },
    });
    if (!conversationId) setDraftRunId(runId);
    requestAnimationFrame(() => scrollToBottom(true));
    return accepted;
  };

  const regenerate = (assistant: Message, body?: RegenerateRequest) => {
    if (busy || !conversationId) return;
    const idx = messages.findIndex((m) => m.id === assistant.id);
    const user = [...messages.slice(0, idx)].reverse().find((m) => m.role === "user");
    if (!user) return;
    if (body?.category) setCategory(body.category);
    if (body?.answer_mode) setAnswerMode(body.answer_mode);
    stick.current = true;
    start({
      kind: "regenerate",
      conversationId,
      messageId: assistant.id,
      userMessageId: user.id,
      question: user.content,
      body: { followups: settings.followups, ...body },
    });
  };

  const edit = (message: Message, question: string) => {
    if (busy || !conversationId) return;
    setEditingId(null);
    stick.current = true;
    start({
      kind: "edit",
      conversationId,
      messageId: message.id,
      question,
      body: { category, answer_mode: answerMode, followups: settings.followups },
    });
  };

  const stop = useCallback(() => {
    if (run) stopRun(run.id);
    else if (pending && conversationId)
      void api(`conversations/${conversationId}/stop`, { method: "POST" }).then(() => conv.refetch());
  }, [run, stopRun, pending, conversationId, conv]);

  const editLast = () => {
    if (busy) return;
    const last = [...visible].reverse().find((m) => m.role === "user");
    if (last) setEditingId(last.id);
  };

  // ── Render ───────────────────────────────────────────────────────────────
  const items: React.ReactNode[] = [];
  let previousUserId: string | null = null;
  const lastAssistantIndex = run ? -1 : visible.map((m) => m.role).lastIndexOf("assistant");

  visible.forEach((m, i) => {
    if (m.role === "user") {
      previousUserId = m.id;
      items.push(
        <UserMessage
          key={`u-${m.id}`}
          content={m.content}
          editable={!busy && !!conversationId}
          editing={editingId === m.id}
          laterMessages={visible.length - i - 1}
          onEditStart={() => setEditingId(m.id)}
          onEditCancel={() => setEditingId(null)}
          onEditSubmit={(q) => edit(m, q)}
        />,
      );
    } else {
      items.push(
        <AssistantMessage
          key={`a-${previousUserId ?? m.id}`}
          view={viewFromMessage(m)}
          conversationId={conversationId}
          isLast={i === lastAssistantIndex}
          busy={busy}
          onRegenerate={(body) => regenerate(m, body)}
          onFollowup={(q) => void send(q)}
        />,
      );
    }
  });

  if (run) {
    const uid = run.userMessageId;
    items.push(
      <UserMessage
        key={uid ? `u-${uid}` : `u-run-${run.id}`}
        content={run.question}
        editable={false}
        editing={false}
        laterMessages={0}
        onEditStart={() => {}}
        onEditCancel={() => {}}
        onEditSubmit={() => {}}
      />,
    );
    const view = viewFromRun(run);
    items.push(
      <AssistantMessage
        key={uid ? `a-${uid}` : `a-run-${run.id}`}
        view={view}
        conversationId={run.conversationId}
        isLast
        busy
        onRegenerate={() => {}}
        onFollowup={(q) => void send(q)}
      />,
    );
  } else if (pending) {
    items.push(
      <div key="pending" className="flex animate-fade-up gap-3.5">
        <LogoMark className="mt-0.5 size-7 rounded-lg" />
        <div className="flex flex-1 items-center gap-3 rounded-xl border border-dashed border-border px-4 py-3 text-[13px] text-muted-foreground">
          <Loader2Icon className="size-4 animate-spin text-primary" />
          <span className="flex-1">An answer is being generated (started in another tab or before a reload)…</span>
          <Button size="xs" variant="outline" onClick={stop}>
            <SquareIcon className="fill-current" /> Stop
          </Button>
        </div>
      </div>,
    );
  }

  const notFound = conv.error instanceof ApiError && conv.error.status === 404;
  const title = detail?.title ?? (run ? run.question : "New chat");

  const topBar = (
    <TopBar
      actions={
        <>
          {conversationId && detail && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <span>
                  <IconButton label="Export conversation" side="bottom">
                    <DownloadIcon />
                  </IconButton>
                </span>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => downloadConversation(conversationId, "markdown")}>
                  Export as Markdown
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => downloadConversation(conversationId, "json")}>
                  Export as JSON
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          {!isEmpty && (
            <IconButton
              label={sourcesOpen ? "Hide sources" : "Show sources"}
              side="bottom"
              onClick={() => setSourcesOpen(!sourcesOpen)}
              className={cn(sourcesOpen && "bg-muted text-foreground")}
            >
              <BookOpenCheckIcon />
            </IconButton>
          )}
        </>
      }
    >
      {!isEmpty && (
        <div className="flex min-w-0 items-center gap-2">
          <h1 className="truncate text-sm font-medium">{title}</h1>
          {detail && detail.category !== "ALL" && (
            <span className="hidden shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground sm:inline">
              {categoryLabel(detail.category)}
            </span>
          )}
        </div>
      )}
    </TopBar>
  );

  const composerEl = (
    <Composer
      ref={composer}
      busy={busy}
      stopping={!!run?.stopping}
      category={category}
      answerMode={answerMode}
      onCategory={setCategory}
      onAnswerMode={setAnswerMode}
      onSend={send}
      onStop={stop}
      onEditLast={conversationId ? editLast : undefined}
      autoFocus
    />
  );

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        {topBar}
        {notFound ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">
            <MessageSquareDashedIcon className="size-10 text-muted-foreground/50" />
            <p className="text-base font-medium">Conversation not found</p>
            <p className="text-sm text-muted-foreground">It may have been deleted, or it belongs to another browser.</p>
            <Button asChild className="mt-2">
              <Link href="/">Start a new chat</Link>
            </Button>
          </div>
        ) : isEmpty ? (
          <div className="relative flex min-h-0 flex-1 flex-col overflow-y-auto">
            <div className="bg-grid pointer-events-none absolute inset-x-0 top-0 h-80" />
            <div className="relative my-auto py-10">
              <EmptyState
                category={category}
                onCategory={setCategory}
                onPick={(q) => void send(q)}
              />
              <div className="mx-auto mt-7 w-full max-w-3xl px-4">{composerEl}</div>
            </div>
          </div>
        ) : (
          <>
            <div ref={scrollRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
              <div className="mx-auto w-full max-w-3xl space-y-8 px-4 pt-6 pb-10" aria-live="off">
                {conv.isPending && conversationId && !run ? <ConversationSkeleton /> : items}
              </div>
            </div>
            <div className="relative shrink-0 px-4 pb-3">
              {!atBottom && (
                <button
                  onClick={() => {
                    stick.current = true;
                    scrollToBottom(true);
                  }}
                  aria-label="Scroll to latest"
                  className="absolute -top-12 left-1/2 flex size-9 -translate-x-1/2 animate-fade-up items-center justify-center rounded-full border border-border bg-background shadow-md transition-colors hover:bg-muted"
                >
                  <ArrowDownIcon className="size-4" />
                </button>
              )}
              <div className="mx-auto w-full max-w-3xl">{composerEl}</div>
            </div>
          </>
        )}
      </div>
      <SourcesPanel />
    </div>
  );
}

export function ConversationSkeleton() {
  return (
    <div className="space-y-8">
      <Skeleton className="ml-auto h-11 w-2/3 rounded-2xl" />
      <div className="flex gap-3.5">
        <Skeleton className="size-7 rounded-lg" />
        <div className="flex-1 space-y-2.5">
          <Skeleton className="h-5 w-40 rounded-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
        </div>
      </div>
    </div>
  );
}
