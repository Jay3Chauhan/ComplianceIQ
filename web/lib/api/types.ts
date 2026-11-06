export type Category = "ALL" | "RBI" | "SEBI" | "AA";
export type AnswerMode = "auto" | "regulatory" | "general";
export type ResponseMode = "regulatory" | "general" | "not_found";
export type Confidence = "high" | "medium" | "low" | null;
export type VerificationStatus = "verified" | "partially_verified" | "unverified" | "not_applicable";
export type MessageStatus = "complete" | "stopped" | "error";
export type RevisionReason = "format" | "repair" | "not_found" | "general_fallback";
export type Stage = "understanding" | "searching" | "thinking" | "writing" | "verifying" | "revising";

export interface Source {
  id: number;
  chunk_id: string;
  doc_id: string;
  doc_name: string;
  circular_id: string;
  category: string;
  section: string;
  page_number: number;
  date: string;
  source_url: string;
  filename: string;
  snippet: string;
  text: string;
  relevance_score: number;
  citation: string;
}

export interface Verification {
  status: VerificationStatus;
  score: number;
  method: string;
  claims_checked: number;
  supported: number;
  unsupported_claims: { claim: string; reason: string }[];
  uncited_claims: string[];
  invalid_citations: number[];
  unsupported_numbers: string[];
  citation_issues: string[];
}

export interface ChatRequest {
  question: string;
  conversation_id?: string | null;
  category?: Category;
  answer_mode?: AnswerMode;
  top_k?: number;
  verify?: boolean;
  save?: boolean;
  followups?: boolean;
}

export interface RegenerateRequest {
  category?: Category;
  answer_mode?: AnswerMode;
  top_k?: number;
  verify?: boolean;
  followups?: boolean;
}

export interface EditRequest extends RegenerateRequest {
  question: string;
}

export interface Conversation {
  id: string;
  title: string;
  category: Category;
  answer_mode: AnswerMode;
  pinned: boolean;
  archived: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface Feedback {
  rating: 1 | -1;
  reasons: string[];
  comment: string | null;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  mode: ResponseMode | null;
  followups: string[];
  sources: Source[];
  verification: Verification | null;
  confidence: Confidence;
  revised: boolean;
  standalone_question: string | null;
  model: string | null;
  latency_ms: number | null;
  created_at: string;
  feedback: Feedback | null;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
  streaming: boolean;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface StopResponse {
  conversation_id: string;
  stopped: boolean;
}

export type StreamEvent =
  | { type: "conversation"; conversation_id: string; user_message_id: string | null }
  | { type: "status"; stage: Stage; message: string }
  | {
      type: "retrieval";
      mode: ResponseMode;
      grounded: boolean;
      gate_score: number;
      standalone_question: string;
      sources: Source[];
      timings: Record<string, number>;
    }
  | { type: "token"; content: string }
  | ({ type: "verification"; final: boolean } & Verification)
  | { type: "revision"; answer: string; mode: ResponseMode; reason: RevisionReason; sources?: Source[] }
  | { type: "followups"; followups: string[] }
  | { type: "title"; conversation_id: string; title: string }
  | { type: "error"; code: string; message: string }
  | {
      type: "done";
      status: MessageStatus;
      message_id: string | null;
      conversation_id: string | null;
      mode: ResponseMode | null;
      answer: string;
      confidence: Confidence;
      model: string | null;
      latency_ms: number;
    };

export interface MetaOption {
  id: string;
  label: string;
  description: string;
}

export interface Meta {
  version: string;
  categories: MetaOption[];
  answer_modes: MetaOption[];
  limits: {
    question_max_chars: number;
    top_k_max: number;
    rate_limit_per_minute: number;
    max_upload_mb: number;
    sse_heartbeat_seconds: number;
  };
  features: Record<string, unknown>;
  models: Record<string, unknown>;
}

export interface DocumentSummary {
  doc_id: string;
  name: string;
  circular_id: string;
  category: string;
  subcategory: string;
  date: string;
  issuer: string;
  source_url: string;
  filename: string;
  has_file: boolean;
  chunks: number;
  indexed: boolean;
}

export interface Passage {
  chunk_id: string;
  seq: number;
  section: string;
  text: string;
}

export interface DocumentPage {
  doc_id: string;
  name: string;
  page_number: number;
  total_pages: number | null;
  passages: Passage[];
}

export interface DocumentOutline {
  doc_id: string;
  name: string;
  sections: { section: string; page_number: number; passages: number }[];
}

export interface SearchResponse {
  query: string;
  search_query: string;
  grounded: boolean;
  gate_score: number;
  results: Source[];
  timings: Record<string, number>;
}

// ── Health ───────────────────────────────────────────────────────────────────

export interface ReadinessCheck {
  ok: boolean;
  detail?: string | null;
  latency_ms?: number | null;
}

export interface Readiness {
  status: "ready" | "degraded";
  checks: Record<string, ReadinessCheck>;
}

// ── Admin ────────────────────────────────────────────────────────────────────

export type DocumentCategory = "RBI" | "SEBI" | "AA" | "GENERAL";

export interface AdminSession {
  enabled: boolean;
  authenticated: boolean;
}

export interface IngestJob {
  id: string;
  doc_id: string;
  filename: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: string | null;
  progress: number;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DocumentMetadata {
  name: string;
  circular_id: string;
  category: DocumentCategory;
  subcategory: string;
  date: string;
  issuer: string;
  url: string;
}

export interface UploadResult {
  document: DocumentSummary & { size_bytes: number };
  job: IngestJob;
}

export interface AdminStats {
  usage: {
    window_days: number;
    total_queries: number;
    by_mode: Record<string, number>;
    grounded_rate: number | null;
    verification: Record<string, number>;
    revised_answers: number;
    errors: number;
    latency_ms: { p50: number | null; p95: number | null };
    feedback: { positive: number; negative: number };
    recent_unanswered: string[];
  };
  index: { collection?: string; points?: number; status?: string; indexed_vectors?: number; error?: string };
  documents: { total: number; indexed: number; by_category: Record<string, number> };
}

export const FEEDBACK_REASONS: { id: string; label: string }[] = [
  { id: "incorrect", label: "Incorrect" },
  { id: "not_grounded", label: "Not supported by sources" },
  { id: "missing_info", label: "Missing information" },
  { id: "wrong_citation", label: "Wrong citation" },
  { id: "outdated", label: "Outdated" },
  { id: "unclear", label: "Unclear" },
  { id: "too_long", label: "Too long" },
  { id: "other", label: "Other" },
];
