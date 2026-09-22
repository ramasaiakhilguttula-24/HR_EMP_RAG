"""Audit tables: every Q&A + security event is stored for compliance/eval."""
import enum
import uuid

from sqlalchemy import Boolean, Enum, Float, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, UUIDMixin


class SecurityEventType(str, enum.Enum):
    injection_attempt = "injection_attempt"
    pii_detected = "pii_detected"
    rbac_denied = "rbac_denied"


class QueryLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "query_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    query: Mapped[str] = mapped_column(Text)
    normalized_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    retrieved_chunk_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    retrieval_scores: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class SecurityEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "security_events"

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[SecurityEventType] = mapped_column(Enum(SecurityEventType))
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
