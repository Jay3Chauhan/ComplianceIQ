from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── LLM (Groq) ───────────────────────────────────────────────────────────
    groq_api_key: str
    groq_model: str = "openai/gpt-oss-120b"
    # Small, fast model for query rewriting and claim verification
    groq_fast_model: str = "qwen/qwen3.8-27b"
    # Tried in order when a model is rate limited or unavailable (comma separated).
    # Free-tier limits are per model, so each fallback has its own token budget.
    groq_fallback_models: str = "openai/gpt-oss-20b,qwen/qwen3.8-27b"
    # Visible answer budget. Reasoning models get llm_reasoning_allowance on top,
    # because their hidden reasoning counts against max_completion_tokens.
    llm_max_tokens: int = 1400
    llm_temperature: float = 0.0
    llm_reasoning_effort: str = "low"  # gpt-oss: low | medium | high
    llm_reasoning_allowance: int = 1000

    # ── Vector store (Qdrant) ────────────────────────────────────────────────
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str = "regulations_v2"
    dense_vector_name: str = "dense"
    sparse_vector_name: str = "bm25"

    # ── Embeddings / rerank ──────────────────────────────────────────────────
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    # Official BGE v1.5 instruction for short-query → passage retrieval
    query_instruction: str = "Represent this sentence for searching relevant passages: "
    sparse_model: str = "Qdrant/bm25"
    enable_rerank: bool = True
    # Same retrieval quality as bge-reranker-base on our eval set, ~3x faster on CPU
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # ── Retrieval ────────────────────────────────────────────────────────────
    retrieval_strategy: str = "hybrid"  # hybrid | dense | sparse
    max_retrieval_chunks: int = 6
    prefetch_limit: int = 30
    rerank_candidates: int = 20
    max_chunks_per_page: int = 2
    # Gate: minimum reranker probability for the best chunk to count as grounded.
    # Calibrated with MiniLM on evaluation/test_questions.json: in-scope ≥ 0.54,
    # out-of-scope ≤ 0.08. Re-calibrate if you change the reranker model.
    rerank_min_score: float = 0.2
    # Gate when reranking is disabled: minimum dense cosine similarity
    dense_min_score: float = 0.58
    # Drop individual chunks far below the best one
    relative_score_floor: float = 0.05
    max_context_chars: int = 7000
    retrieval_cache_ttl: int = 600
    enable_query_rewrite: bool = True
    enable_glossary_expansion: bool = True

    # ── Chunking ─────────────────────────────────────────────────────────────
    chunk_size: int = 900
    chunk_overlap: int = 120

    # ── Anti-hallucination ───────────────────────────────────────────────────
    enable_verification: bool = True
    enable_llm_verifier: bool = True
    enable_answer_repair: bool = True
    verification_pass_score: float = 0.8

    # ── Persistence ──────────────────────────────────────────────────────────
    database_url: str = "sqlite:///./data/complianceiq.db"

    # ── Security / limits ────────────────────────────────────────────────────
    # Comma-separated keys accepted in X-API-Key (server-to-server, e.g. Next.js)
    api_keys: str = ""
    admin_api_key: str = ""
    cors_origins: str = "*"
    rate_limit_per_minute: int = 30
    max_upload_mb: int = 50

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        if not self.cors_origins or self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def fallback_model_list(self) -> list[str]:
        return [m.strip() for m in self.groq_fallback_models.split(",") if m.strip()]

    @property
    def api_key_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
