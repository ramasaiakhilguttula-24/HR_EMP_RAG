"""HR escalation tickets for human-in-the-loop (Feature 15)."""
import uuid

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, UUIDMixin


class Escalation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "escalations"

    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    query: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(20), default="open")
