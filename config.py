from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Groq
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"

    # Qdrant
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str = "regulations"

    # Embeddings / rerank
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    enable_rerank: bool = True
    reranker_model: str = "BAAI/bge-reranker-base"
    retrieval_candidate_multiplier: int = 4

    # RAG settings
    max_retrieval_chunks: int = 6
    chunk_size: int = 900
    chunk_overlap: int = 120
    score_threshold: float = 0.42
    score_fallback_threshold: float = 0.30
    grounded_min_score: float = 0.58

    # Security / deploy
    admin_api_key: str = ""
    cors_origins: str = "*"
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


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
