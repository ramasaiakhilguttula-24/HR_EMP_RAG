"""Embedder + pipeline tests with fakes (no network). Live HF check runs separately."""
from unittest.mock import MagicMock

from backend.app.services.ingestion.embedder import HFEmbedder, get_embedder
from backend.app.services.ingestion.pipeline import build_points, ingest_file


class FakeEmbedder:
    dim = 8

    def embed_documents(self, texts):
        return [[float(len(t) % 10)] * self.dim for t in texts]

    def embed_query(self, text):
        return self.embed_documents([text])[0]


class FakeSparse:
    def embed_documents(self, texts):
        return [{"indices": [1], "values": [0.5]} for _ in texts]


def test_build_points_payload_shape():
    points = build_points(
        "doc-1", "leave.pdf", {"department": "HR", "access_level": "public"},
        1, [[0.1] * 8], [{"text": "hello", "page_number": 3, "section_heading": None}],
    )
    assert len(points) == 1
    p = points[0].payload
    assert p["document_id"] == "doc-1" and p["chunk_id"] == "doc-1_0_v1"
    assert p["chunk_index"] == 0 and p["page_number"] == 3
    assert p["version"] == 1 and p["is_active"] is True and p["text"] == "hello"


def test_ingest_file_upserts_and_soft_deletes(tmp_path, monkeypatch):
    f = tmp_path / "leave.txt"
    f.write_text("Annual leave is 18 days. " * 100, encoding="utf-8")

    fake_qdrant = MagicMock()
    summary = ingest_file(
        f, "doc-1", "leave.txt", {"department": "HR"}, 2,
        prev_document_ids=["old-doc"], embedder=FakeEmbedder(), qdrant_client=fake_qdrant,
        sparse_embedder=FakeSparse(),
    )
    assert summary["chunks"] >= 1 and summary["version"] == 2
    fake_qdrant.set_payload.assert_called_once()  # old version soft-deleted
    fake_qdrant.upsert.assert_called_once()
    _, kwargs = fake_qdrant.upsert.call_args
    assert kwargs["collection_name"] == "hr_policies"
    assert len(kwargs["points"]) == summary["chunks"]


def test_ingest_file_empty_text_rejected(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("   ", encoding="utf-8")
    import pytest

    with pytest.raises(ValueError):
        ingest_file(f, "d", "empty.txt", {}, 1, embedder=FakeEmbedder(),
                    qdrant_client=MagicMock(), sparse_embedder=FakeSparse())


def test_hf_embedder_requires_token(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.get_settings",
                        lambda: type("S", (), {"EMBED_MODEL": "m", "HF_TOKEN": "", "EMBED_PROVIDER": "huggingface"})())
    import pytest

    with pytest.raises(ValueError, match="HF_TOKEN"):
        HFEmbedder()


def test_get_embedder_default_provider(monkeypatch):
    monkeypatch.setattr("backend.app.core.config.get_settings",
                        lambda: type("S", (), {"EMBED_MODEL": "m", "HF_TOKEN": "tok",
                                              "EMBED_PROVIDER": "huggingface"})())
    assert isinstance(get_embedder(), HFEmbedder)
