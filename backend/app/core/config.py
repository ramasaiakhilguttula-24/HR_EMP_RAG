"""Typed app configuration. Single source of truth for env vars."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "hr-policy-rag"
    ENV: str = "dev"
    API_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:3000"

    # Databases
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/hr_rag"
    POSTGRES_SSL: bool = False
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION: str = "hr_policies"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth (Feature 3)
    JWT_SECRET: str = "change-me-in-prod"
    JWT_ALG: str = "HS256"
    ACCESS_TTL_MIN: int = 15
    REFRESH_TTL_DAYS: int = 7

    # Models
    EMBED_PROVIDER: str = "huggingface"  # huggingface | openai (pluggable, see services/ingestion/embedder.py)
    EMBED_MODEL: str = "BAAI/bge-large-en-v1.5"
    EMBED_DIM: int = 1024
    HF_TOKEN: str = ""
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""  # LLM generation (Feature 6)
    COHERE_API_KEY: str = ""  # reranking (Feature 10)
    RERANK_MODEL: str = "rerank-english-v3.0"
    RERANK_THRESHOLD: float = 0.3
    RERANK_TOP_N: int = 5

    # Cache (Feature 11)
    CACHE_TTL_STANDARD: int = 86400
    CACHE_TTL_BENEFITS: int = 3600
    CACHE_SIM_THRESHOLD: float = 0.95

    # Observability (Feature 16)
    LANGSMITH_TRACING: bool = True
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "hr-rag-dev"
    LLM_PROVIDER: str = "groq"
    LLM_MODEL: str = "openai/gpt-oss-120b"
    LLM_TEMP: float = 0.1

    # RAG tuning
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64
    TOP_K_RETRIEVE: int = 10
    TOP_K_RERANK: int = 5
    SCORE_THRESHOLD: float = 0.5


@lru_cache
def get_settings() -> Settings:
    return Settings()
