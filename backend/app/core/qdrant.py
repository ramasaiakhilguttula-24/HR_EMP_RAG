"""Qdrant client helper. Dense (default) + BM25 sparse (Phase 2 hybrid)."""
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, SparseVectorParams, VectorParams

from backend.app.core.config import get_settings


def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.QDRANT_URL, timeout=10)


def ensure_collection(client: QdrantClient | None = None) -> str:
    """Create `hr_policies` collection if missing. Returns collection name."""
    from backend.app.core.config import get_settings as _gs

    settings = _gs()
    client = client or get_qdrant_client()
    if not client.collection_exists(settings.QDRANT_COLLECTION):
        client.create_collection(
            collection_name=settings.QDRANT_COLLECTION,
            vectors_config={"dense": VectorParams(size=settings.EMBED_DIM, distance=Distance.COSINE)},
            sparse_vectors_config={"bm25": SparseVectorParams()},
        )
    return settings.QDRANT_COLLECTION
