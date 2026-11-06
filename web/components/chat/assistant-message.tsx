"use client";

import Link from "next/link";
import { useCallback, useMemo } from "react";
import { toast } from "sonner";
import {
  AlertTriangleIcon,
  ArrowRightIcon,
  BookOpenIcon,
  CheckIcon,
  CircleStopIcon,
  CopyIcon,
  GlobeIcon,
  InfoIcon,
  LibraryIcon,
  RefreshCwIcon,
  SearchXIcon,
  SparklesIcon,
} from "lucide-react";
import { useState } from "react";
import { AnswerMarkdown } from "@/components/chat/answer-markdown";
import { FeedbackBar } from "@/components/chat/feedback-bar";
import { StatusLine } from "@/components/chat/status-line";
import { ConfidenceMeter, ModeBadge, VerificationBadge } from "@/components/chat/trust-badges";
import { IconButton } from "@/components/common/icon-button";
import { LogoMark } from "@/components/common/logo";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type {
  Confidence,
  Feedback,
  Message,
  MessageStatus,
  RegenerateRequest,
  ResponseMode,
  Source,
  Verification,
} from "@/lib/api/types";
import { isFinished, type AnswerStage } from "@/lib/chat/reducer";
import type { Run } from "@/lib/chat/store";
import { answerToClipboard, shortDocName } from "@/lib/format";
import { useUI } from "@/lib/ui";
import { cn } from "@/lib/utils";

export interface AssistantView {
  key: string;
  messageId: string | null;
  content: string;
  status: "streaming" | MessageStatus;
  stage: AnswerStage | null;
  statusText: string;
  stopping: boolean;
  mode: ResponseMode | null;
  sources: Source[];
  verification: Verification | null;
  confidence: Confidence;
  revised: boolean;
  generalFallback: boolean;
  followups: string[];
  feedback: Feedback | null;
  model: string | null;
  latencyMs: number | null;
  error: string | null;
}

export function viewFromMessage(m: Message): AssistantView {
  return {
    key: m.id,
    messageId: m.id,
    content: m.content,
    status: m.status,
    stage: null,
    statusText: "",
    stopping: false,
    mode: m.mode,
    sources: m.sources,
    verification: m.verification,
    confidence: m.confidence,
    revised: m.revised,
    generalFallback: false,
    followups: m.followups ?? [],
    feedback: m.feedback,
    model: m.model,
    latencyMs: m.latency_ms,
    error: m.status === "error" ? "The answer couldn’t be completed." : null,
  };
}

export function viewFromRun(run: Run): AssistantView {
  const a = run.answer;
  const finished = isFinished(a.stage);
  return {
    key: a.messageId ?? run.id,
    messageId: a.messageId,
    content: a.text,
    status: finished ? (a.stage as MessageStatus) : "streaming",
    stage: a.stage,
    statusText: a.statusText,
    stopping: run.stopping,
    mode: a.mode,
    sources: a.mode === "regulatory" ? a.sources : [],
    verification: a.verification,
    confidence: a.confidence,
    revised: a.revised,
    generalFallback: a.generalFallback,
    followups: a.followups,
    feedback: null,
    model: a.model,
    latencyMs: a.latencyMs,
    error: a.error?.message ?? null,
  };
}

interface Props {
  view: AssistantView;
  conversationId: string | null;
  isLast: boolean;
  busy: boolean;
  onRegenerate: (body?: RegenerateRequest) => void;
  onFollowup: (question: string) => void;
}

export function AssistantMessage({ view, conversationId, isLast, busy, onRegenerate, onFollowup }: Props) {
  const showSources = useUI((s) => s.showSources);
  const [copied, setCopied] = useState(false);
  const streaming = view.status === "streaming";
  const owner = view.messageId ?? view.key;
  const sources = useMemo(() => (view.mode === "regulatory" ? view.sources : []), [view.mode, view.sources]);
  const onCite = useCallback((n: number) => showSources(owner, sources, n), [showSources, owner, sources]);
  const canAct = !streaming && !!view.messageId && !!conversationId;
  const writing = streaming && view.content.length > 0 && view.mode !== "not_found";
  const waiting = streaming && (view.content.length === 0 || view.stage === "verifying" || view.stage === "revising");

  const copy = async () => {
    await navigator.clipboard.writeText(answerToClipboard(view.content, sources));
    setCopied(true);
    toast.success("Answer copied with sources");
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <article id={view.messageId ? `m-${view.messageId}` : undefined} className="group/msg flex animate-fade-up gap-3.5">
      <LogoMark className="mt-0.5 size-7 rounded-lg" />
      <div className="min-w-0 flex-1">
        {/* header badges */}
        {(view.mode || !streaming) && view.content && (
          <div className="mb-2.5 flex flex-wrap items-center gap-1.5">
            <ModeBadge mode={view.mode} />
            {!streaming && <VerificationBadge verification={view.verification} revised={view.revised} />}
            {!streaming && <ConfidenceMeter confidence={view.confidence} />}
          </div>
        )}

        {view.mode === "general" && view.content && (
          <div className="mb-3 flex gap-2.5 rounded-xl border border-general/25 bg-general/6 px-3.5 py-2.5 text-[13px] text-foreground/85">
            <SparklesIcon className="mt-0.5 size-4 shrink-0 text-general" />
            <p>
              {view.generalFallback
                ? "The loaded documents don’t cover this, so this answer is from general knowledge."
                : "This answer is from general knowledge, not the loaded regulatory documents."}{" "}
              Verify on the regulator’s website before relying on it.
            </p>
          </div>
        )}

        {view.mode === "not_found" ? (
          <NotFoundCard
            text={view.content}
            canAct={canAct && !busy}
            onAllRegulators={() => onRegenerate({ category: "ALL", answer_mode: "regulatory" })}
            onGeneral={() => onRegenerate({ answer_mode: "general" })}
          />
        ) : view.content ? (
          <AnswerMarkdown text={view.content} sources={sources} onCite={onCite} streaming={writing && !waiting} />
        ) : null}

        {waiting && (
          <div className={cn(view.content && "mt-3")}>
            <StatusLine stage={view.stage ?? "starting"} text={view.statusText} stopping={view.stopping} />
          </div>
        )}

        {view.status === "stopped" && (
          <StatusRow
            icon={<CircleStopIcon className="size-4" />}
            text={view.content ? "Stopped before the answer was finished." : "Stopped."}
            action={canAct && !busy ? () => onRegenerate() : undefined}
            actionLabel="Regenerate"
          />
        )}
        {view.status === "error" && (
          <StatusRow
            tone="error"
            icon={<AlertTriangleIcon className="size-4" />}
            text={view.error ?? "The answer couldn’t be completed."}
            action={canAct && !busy ? () => onRegenerate() : undefined}
            actionLabel="Try again"
          />
        )}

        {/* compact source row */}
        {!streaming && sources.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-1.5">
            {sources.slice(0, 6).map((s) => (
              <button
                key={s.chunk_id}
                onClick={() => onCite(s.id)}
                className="inline-flex h-7 max-w-[15rem] items-center gap-1.5 rounded-lg border border-border bg-card px-2 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
              >
                <span className="font-mono font-semibold text-primary">{s.id}</span>
                <span className="truncate">{shortDocName(s.doc_name)}</span>
                <span className="shrink-0 text-muted-foreground/80">p.{s.page_number}</span>
              </button>
            ))}
            {sources.length > 6 && (
              <button
                onClick={() => showSources(owner, sources)}
                className="h-7 rounded-lg px-2 text-xs text-muted-foreground hover:text-foreground"
              >
                +{sources.length - 6} more
              </button>
            )}
          </div>
        )}

        {/* actions */}
        {canAct && view.status === "complete" && (
          <div
            className={cn(
              "mt-2 -ml-1.5 flex items-center gap-0.5 transition-opacity",
              !isLast && "opacity-0 group-hover/msg:opacity-100 focus-within:opacity-100",
            )}
          >
            <IconButton label={copied ? "Copied" : "Copy answer"} onClick={copy}>
              {copied ? <CheckIcon /> : <CopyIcon />}
            </IconButton>
            {isLast && (
              <IconButton label="Regenerate" onClick={() => onRegenerate()} disabled={busy}>
                <RefreshCwIcon />
              </IconButton>
            )}
            {sources.length > 0 && (
              <IconButton label="Show sources" onClick={() => showSources(owner, sources)}>
                <BookOpenIcon />
              </IconButton>
            )}
            <FeedbackBar conversationId={conversationId!} messageId={view.messageId!} feedback={view.feedback} />
            {(view.model || view.latencyMs) && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span className="ml-1 inline-flex size-7 items-center justify-center text-muted-foreground/60" tabIndex={0}>
                    <InfoIcon className="size-3.5" />
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  {[view.model, view.latencyMs ? `${(view.latencyMs / 1000).toFixed(1)}s` : null].filter(Boolean).join(" · ")}
                </TooltipContent>
              </Tooltip>
            )}
          </div>
        )}

        {/* follow-ups */}
        {isLast && view.status === "complete" && view.followups.length > 0 && (
          <div className="mt-5 space-y-1.5" role="list" aria-label="Suggested follow-up questions">
            <p className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              {view.mode === "not_found" ? "Try one of these" : "Follow up"}
            </p>
            {view.followups.map((q, i) => (
              <button
                key={q}
                role="listitem"
                disabled={busy}
                onClick={() => onFollowup(q)}
                style={{ animationDelay: `${i * 60}ms` }}
                className="group/f flex w-full animate-fade-up items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-left text-[13px] transition-colors hover:border-primary/40 hover:bg-primary/5 disabled:opacity-50"
              >
                <span className="flex-1">{q}</span>
                <ArrowRightIcon className="size-3.5 text-muted-foreground transition-transform group-hover/f:translate-x-0.5 group-hover/f:text-primary" />
              </button>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function StatusRow({
  icon,
  text,
  action,
  actionLabel,
  tone = "muted",
}: {
  icon: React.ReactNode;
  text: string;
  action?: () => void;
  actionLabel: string;
  tone?: "muted" | "error";
}) {
  return (
    <div
      className={cn(
        "mt-3 flex items-center gap-2.5 rounded-lg border px-3 py-2 text-[13px]",
        tone === "error"
          ? "border-destructive/30 bg-destructive/5 text-destructive"
          : "border-border bg-muted/50 text-muted-foreground",
      )}
    >
      {icon}
      <span className="flex-1">{text}</span>
      {action && (
        <Button size="xs" variant={tone === "error" ? "outline" : "secondary"} onClick={action}>
          <RefreshCwIcon /> {actionLabel}
        </Button>
      )}
    </div>
  );
}

function NotFoundCard({
  text,
  canAct,
  onAllRegulators,
  onGeneral,
}: {
  text: string;
  canAct: boolean;
  onAllRegulators: () => void;
  onGeneral: () => void;
}) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-muted/30 p-4">
      <div className="flex gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-background ring-1 ring-border">
          <SearchXIcon className="size-4 text-muted-foreground" />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-medium">Not covered by the loaded documents</p>
          <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">{text}</p>
        </div>
      </div>
      <div className="mt-3.5 flex flex-wrap gap-2 pl-12">
        {canAct && (
          <>
            <Button size="sm" variant="outline" onClick={onAllRegulators}>
              <GlobeIcon /> Search all regulators
            </Button>
            <Button size="sm" variant="outline" onClick={onGeneral}>
              <SparklesIcon /> Answer from general knowledge
            </Button>
          </>
        )}
        <Button size="sm" variant="ghost" asChild>
          <Link href="/documents">
            <LibraryIcon /> Browse documents
          </Link>
        </Button>
      </div>
    </div>
  );
}
