"""Ingestion orchestrator: parse -> chunk -> embed -> upsert into Qdrant.

Versioning: chunks carry {document_id, version}. Re-ingesting the same file_name
soft-deletes previous versions (is_active=false) instead of hard-deleting.
"""
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from qdrant_client.http.models import FieldCondition, Filter, MatchValue, PointStruct

from backend.app.core.config import get_settings
from backend.app.services.ingestion.chunker import chunk_pages
from backend.app.services.ingestion.embedder import Embedder
from backend.app.services.ingestion.parser import parse_file

CHUNK_ID = "{document_id}_{chunk_index}_v{version}"


def _to_epoch(value) -> float | None:
    """Normalize date/datetime/ISO string to epoch seconds for numeric range filters."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    return dt.replace(tzinfo=timezone.utc).timestamp()


def build_points(
    document_id: str,
    document_name: str,
    meta: dict,
    version: int,
    vectors: list[list[float]],
    chunks_meta: list[dict],
    sparse_vecs: list[dict] | None = None,
) -> list[PointStruct]:
    from qdrant_client.http.models import SparseVector

    points: list[PointStruct] = []
    for i, (vec, cm) in enumerate(zip(vectors, chunks_meta)):
        chunk_id = CHUNK_ID.format(document_id=document_id, chunk_index=i, version=version)
        vector: list | dict = vec
        if sparse_vecs is not None:
            vector = {"dense": vec,
                      "bm25": SparseVector(indices=sparse_vecs[i]["indices"],
                                           values=sparse_vecs[i]["values"])}
        points.append(
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id)),
                vector=vector,
                payload={
                    "document_id": document_id,
                    "document_name": document_name,
                    "chunk_id": chunk_id,
                    "chunk_index": i,
                    "text": cm["text"],
                    "page_number": cm["page_number"],
                    "section_heading": cm.get("section_heading"),
                    "department": meta.get("department"),
                    "location": meta.get("location"),
                    "policy_category": meta.get("policy_category"),
                    "employment_type": meta.get("employment_type"),
                    "seniority": meta.get("seniority"),
                    "access_level": meta.get("access_level", "public"),
                    "version": version,
                    "effective_date": meta.get("effective_date"),
                    "effective_date_ts": _to_epoch(meta.get("effective_date")),
                    "is_active": True,
                },
            )
        )
    return points


def ingest_file(
    file_path: str | Path,
    document_id: str,
    document_name: str,
    meta: dict,
    version: int,
    prev_document_ids: list[str] | None = None,
    embedder: Embedder | None = None,
    qdrant_client=None,
    sparse_embedder=None,
) -> dict:
    """Run the full pipeline for one file. Returns summary dict."""
    from backend.app.core.qdrant import get_qdrant_client
    from backend.app.services.ingestion.embedder import get_embedder as _get_embedder
    from backend.app.services.ingestion.embedder import BM25Embedder

    settings = get_settings()
    client = qdrant_client or get_qdrant_client()
    embedder = embedder or _get_embedder()
    sparse_embedder = sparse_embedder or BM25Embedder()

    pages = parse_file(file_path)
    if not pages:
        raise ValueError(f"No extractable text in {document_name}")
    chunks = chunk_pages(pages)
    if not chunks:
        raise ValueError(f"No chunks produced from {document_name} (empty or too short)")
    # F13: mask PII before embedding/storing (one-way; no reversible vault).
    from backend.app.services.security.pii_masker import mask_text

    masked = [mask_text(c.text) for c in chunks]
    chunk_dicts = [{"text": m, "page_number": c.page_number, "section_heading": c.section_heading}
                   for c, (m, _) in zip(chunks, masked)]
    pii_count = sum(len(findings) for _, findings in masked)
    vectors = embedder.embed_documents([d["text"] for d in chunk_dicts])
    if len(vectors) != len(chunk_dicts):
        raise ValueError("Embedder returned wrong number of vectors")
    sparse_vecs = sparse_embedder.embed_documents([d["text"] for d in chunk_dicts])

    # Soft-delete previous versions of the same document.
    for prev_id in prev_document_ids or []:
        client.set_payload(
            collection_name=settings.QDRANT_COLLECTION,
            payload={"is_active": False},
            points=Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=prev_id))]
            ),
        )

    points = build_points(
        document_id, document_name, meta, version,
        vectors, chunk_dicts,
        sparse_vecs,
    )
    client.upsert(collection_name=settings.QDRANT_COLLECTION, points=points)
    return {"document_id": document_id, "chunks": len(points), "version": version,
            "pii_masked": pii_count}
