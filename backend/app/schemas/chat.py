"""Chat (RAG answer) request/response schemas."""
from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)
    filters: dict | None = None
    use_profile_filters: bool = True
    extract_filters: bool = False
    search_mode: str = Field(default="hybrid", pattern="^(dense|hybrid)$")
    rerank: bool = True


class CitationOut(BaseModel):
    index: int
    document: str
    page: int | None = None
    section: str | None = None
    excerpt: str


class ChatOut(BaseModel):
    answer: str
    citations: list[CitationOut]
    fallback: bool
    latency_ms: int
    cached: bool = False
