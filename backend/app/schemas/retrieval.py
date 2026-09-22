"""Retrieval request/response schemas."""
from pydantic import BaseModel, Field


class RetrieveIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=10, ge=1, le=50)
    use_mmr: bool = True
    filters: dict | None = None
    use_profile_filters: bool = True
    extract_filters: bool = False
    search_mode: str = Field(default="hybrid", pattern="^(dense|hybrid)$")
    rerank: bool = True


class ChunkOut(BaseModel):
    chunk_id: str
    text: str
    score: float
    document_name: str
    page_number: int | None = None
    section_heading: str | None = None


class RetrieveOut(BaseModel):
    query: str
    chunks: list[ChunkOut]
    latency_ms: int
