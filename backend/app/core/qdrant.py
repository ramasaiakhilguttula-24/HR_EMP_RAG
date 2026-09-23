"""Qdrant client helper. Dense (default) + BM25 sparse (Phase 2 hybrid)."""
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PayloadSchemaType, SparseVectorParams, VectorParams

from backend.app.core.config import get_settings

# Qdrant Cloud rejects filtered search without these; self-hosted auto-indexes.
PAYLOAD_INDEXES = {
    "is_active": PayloadSchemaType.BOOL,
    "document_id": PayloadSchemaType.KEYWORD,
    "department": PayloadSchemaType.KEYWORD,
    "location": PayloadSchemaType.KEYWORD,
    "policy_category": PayloadSchemaType.KEYWORD,
    "employment_type": PayloadSchemaType.KEYWORD,
    "seniority": PayloadSchemaType.KEYWORD,
    "access_level": PayloadSchemaType.KEYWORD,
    "effective_date_ts": PayloadSchemaType.FLOAT,
    "version": PayloadSchemaType.INTEGER,
}


def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.QDRANT_URL,
                        api_key=settings.QDRANT_API_KEY or None, timeout=10)


def ensure_collection(client: QdrantClient | None = None) -> str:
    """Create `hr_policies` if missing; always ensure payload indexes. Returns name."""
    from backend.app.core.config import get_settings as _gs

    settings = _gs()
    client = client or get_qdrant_client()
    if not client.collection_exists(settings.QDRANT_COLLECTION):
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config={"dense": VectorParams(size=settings.EMBED_DIM, distance=Distance.COSINE)},
            sparse_vectors_config={"bm25": SparseVectorParams()},
        )
    try:
        existing = set((client.get_collection(settings.QDRANT_COLLECTION).payload_schema or {}).keys())
    except Exception:
        existing = set()
    for field, schema in PAYLOAD_INDEXES.items():
        if field in existing:
            continue
        try:
            client.create_payload_index(settings.QDRANT_COLLECTION, field, schema)
        except Exception:
            pass  # already exists (race) or server-managed
    return settings.QDRANT_COLLECTION
