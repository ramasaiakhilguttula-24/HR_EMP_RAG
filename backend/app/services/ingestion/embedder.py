"""Embedder interface. Phase 1: Hugging Face Inference API (bge-large, 1024-dim).

Swap to OpenAI (text-embedding-3-small, 1536-dim) later by adding an
OpenAIEmbedder with the same two methods — callers stay unchanged.
"""


class Embedder:
    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class HFEmbedder(Embedder):
    """bge-large-en-v1.5 via Hugging Face Inference API. Needs HF_TOKEN in env."""

    def __init__(self, model: str | None = None, token: str | None = None) -> None:
        from huggingface_hub import InferenceClient

        from backend.app.core.config import get_settings

        settings = get_settings()
        self.model = model or settings.EMBED_MODEL
        api_key = token or settings.HF_TOKEN
        if not api_key:
            raise ValueError("HF_TOKEN is missing. Add it to .env.")
        self._client = InferenceClient(api_key=api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out = self._client.feature_extraction(texts, model=self.model)
        return [list(map(float, v)) for v in out]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class BM25Embedder:
    """Statistical BM25 sparse vectors via fastembed (local, no key, no GPU)."""

    def __init__(self, model: str = "Qdrant/bm25") -> None:
        from fastembed import SparseTextEmbedding

        self._model = SparseTextEmbedding(model)

    @staticmethod
    def _to_dict(vec) -> dict:
        return {"indices": [int(i) for i in vec.indices],
                "values": [float(v) for v in vec.values]}

    def embed_documents(self, texts: list[str]) -> list[dict]:
        if not texts:
            return []
        return [self._to_dict(v) for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> dict:
        return self.embed_documents([text])[0]


def get_embedder() -> Embedder:
    from backend.app.core.config import get_settings

    provider = get_settings().EMBED_PROVIDER.lower()
    if provider == "huggingface":
        return HFEmbedder()
    raise ValueError(f"Unknown EMBED_PROVIDER '{provider}' (expected 'huggingface')")
