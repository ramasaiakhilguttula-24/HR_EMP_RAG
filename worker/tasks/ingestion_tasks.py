"""Celery ingestion tasks. Phase 6 wires a real worker; until then the API uses
FastAPI BackgroundTasks calling the same `ingest_file` pipeline function.
"""
try:
    from celery import shared_task

    from backend.app.services.ingestion.pipeline import ingest_file

    @shared_task(name="ingest_document")
    def ingest_document(file_path: str, document_id: str, document_name: str,
                        meta: dict, version: int, prev_ids: list[str] | None = None) -> dict:
        return ingest_file(file_path, document_id, document_name, meta, version, prev_ids)
except ImportError:  # celery installed only in worker image (Phase 6)
    pass
