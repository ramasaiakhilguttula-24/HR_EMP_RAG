"""Document upload/list routes (Phase 1). Upload runs ingestion as a background task."""
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal, get_db
from backend.app.core.dependencies import require_role
from backend.app.models.document import Document, DocumentStatus
from backend.app.models.user import User

router = APIRouter(prefix="/documents", tags=["documents"])

UPLOAD_DIR = Path("uploads")
ALLOWED_EXT = {".pdf", ".docx", ".xlsx", ".txt", ".md", ".html", ".htm"}


async def _run_ingestion(document_id: str, file_path: str, meta: dict, version: int, prev_ids: list[str]):
    """Background task with its own DB session (request session is closed by then)."""
    from backend.app.models.query_log import SecurityEvent, SecurityEventType
    from backend.app.services.ingestion.pipeline import ingest_file

    async with AsyncSessionLocal() as db:
        try:
            summary = ingest_file(
                file_path, document_id, Path(file_path).name, meta, version, prev_ids
            )
            doc = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
            if doc:
                doc.status = DocumentStatus.ready
                await db.commit()
            if summary.get("pii_masked"):
                db.add(SecurityEvent(user_id=doc.uploaded_by if doc else None,
                                     event_type=SecurityEventType.pii_detected,
                                     details={"stage": "ingest", "count": summary["pii_masked"],
                                              "document_id": document_id}))
                await db.commit()
            try:  # force cache invalidation on re-ingest (Feature 11)
                from backend.app.services.cache.semantic_cache import get_cache

                await get_cache().invalidate()
            except Exception:
                pass
            return summary
        except Exception:
            doc = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
            if doc:
                doc.status = DocumentStatus.failed
                await db.commit()
            raise


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload(
    file: UploadFile,
    background: BackgroundTasks,
    department: str | None = None,
    location: str | None = None,
    policy_category: str | None = None,
    access_level: str = "public",
    seniority: str | None = None,
    user: User = Depends(require_role("hr_manager", "admin")),
    db: AsyncSession = Depends(get_db),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Allowed types: {sorted(ALLOWED_EXT)}")

    UPLOAD_DIR.mkdir(exist_ok=True)
    document_id = str(uuid.uuid4())
    saved = UPLOAD_DIR / f"{document_id}_{Path(file.filename).name}"
    saved.write_bytes(await file.read())

    prev = (
        (await db.execute(select(Document).where(Document.file_name == file.filename)))
        .scalars()
        .all()
    )
    version = max([d.version for d in prev], default=0) + 1

    doc = Document(
        id=document_id,
        file_name=file.filename,
        file_type=ext.lstrip("."),
        file_size=saved.stat().st_size,
        file_path=str(saved),
        department=department,
        location=location,
        policy_category=policy_category,
        seniority=seniority,
        access_level=access_level,
        version=version,
        status=DocumentStatus.processing,
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.commit()

    meta = {"department": department, "location": location, "policy_category": policy_category,
            "seniority": seniority, "access_level": access_level, "effective_date": None}
    background.add_task(_run_ingestion, document_id, str(saved), meta, version, [str(d.id) for d in prev])
    return {"document_id": document_id, "status": "processing", "version": version}


@router.get("")
async def list_documents(
    user: User = Depends(require_role("hr_manager", "admin", "employee")),
    db: AsyncSession = Depends(get_db),
):
    docs = (await db.execute(select(Document).order_by(Document.created_at.desc()))).scalars().all()
    return [
        {"id": str(d.id), "file_name": d.file_name, "version": d.version,
         "status": d.status.value, "policy_category": d.policy_category}
        for d in docs
    ]


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    user: User = Depends(require_role("hr_manager", "admin", "employee")),
    db: AsyncSession = Depends(get_db),
):
    try:
        uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid document id")
    doc = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return {"id": str(doc.id), "file_name": doc.file_name, "version": doc.version,
            "status": doc.status.value, "department": doc.department,
            "location": doc.location, "policy_category": doc.policy_category,
            "access_level": doc.access_level}
