"""Document metadata (file content lives in object storage / uploads/, vectors in Qdrant)."""
import datetime
import enum
import uuid

from sqlalchemy import Date, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.core.database import Base
from backend.app.models.base import TimestampMixin, UUIDMixin


class DocumentStatus(str, enum.Enum):
    processing = "processing"
    ready = "ready"
    failed = "failed"
    archived = "archived"


class Document(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "documents"

    file_name: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(20))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    policy_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(100), nullable=True)
    access_level: Mapped[str] = mapped_column(String(50), default="public")

    version: Mapped[int] = mapped_column(Integer, default=1)
    effective_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus), default=DocumentStatus.processing)

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
