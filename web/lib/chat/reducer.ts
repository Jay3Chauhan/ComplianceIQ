import type {
  Confidence,
  MessageStatus,
  ResponseMode,
  Source,
  Stage,
  StreamEvent,
  Verification,
} from "@/lib/api/types";

export type AnswerStage = "starting" | Stage | MessageStatus;

export interface ActiveAnswer {
  stage: AnswerStage;
  statusText: string;
  text: string;
  sources: Source[];
  mode: ResponseMode | null;
  verification: Verification | null;
  revised: boolean;
  generalFallback: boolean;
  confidence: Confidence;
  messageId: string | null;
  followups: string[];
  model: string | null;
  latencyMs: number | null;
  error: { code: string; message: string } | null;
}

export const initialAnswer: ActiveAnswer = {
  stage: "starting",
  statusText: "Starting…",
  text: "",
  sources: [],
  mode: null,
  verification: null,
  revised: false,
  generalFallback: false,
  confidence: null,
  messageId: null,
  followups: [],
  model: null,
  latencyMs: null,
  error: null,
};

export function isFinished(stage: AnswerStage): boolean {
  return stage === "complete" || stage === "stopped" || stage === "error";
}

export function reduce(s: ActiveAnswer, e: StreamEvent): ActiveAnswer {
  switch (e.type) {
    case "status":
      return { ...s, stage: e.stage, statusText: e.message };
    case "retrieval":
      return { ...s, sources: e.sources, mode: e.mode };
    case "token":
      return { ...s, text: s.text + e.content };
    case "revision":
      return {
        ...s,
        text: e.answer,
        mode: e.mode,
        sources: e.sources ?? s.sources,
        revised: s.revised || e.reason === "repair",
        generalFallback: s.generalFallback || e.reason === "general_fallback",
      };
    case "verification":
      return e.final ? { ...s, verification: e } : s;
    case "followups":
      return { ...s, followups: e.followups };
    case "error":
      return { ...s, error: { code: e.code, message: e.message } };
    case "done":
      return {
        ...s,
        stage: e.status,
        text: e.answer,
        mode: e.mode ?? s.mode,
        confidence: e.confidence,
        messageId: e.message_id,
        model: e.model,
        latencyMs: e.latency_ms,
        followups: e.status === "complete" ? s.followups : [],
      };
    default:
      return s;
  }
}
