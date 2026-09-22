# HR Employee Policy RAG System

Production-grade RAG assistant for HR policies. See `project_plan.md` (20 features, 6 phases)
and `project_related_info.md` (system design reference).

## Quickstart (Phase 1)
```bash
docker compose up -d
copy .env.example .env
pip install -r backend/requirements.txt
alembic upgrade head
uvicorn backend.main:app --reload
```

## Layout
- `backend/` FastAPI + SQLAlchemy + Alembic + services (ingestion/retrieval/generation/security/cache)
- `frontend/` Next.js 14 placeholder (Phase 5)
- `worker/` Celery ingestion tasks
- `infrastructure/` Terraform + Nginx (Phase 6)
- `evaluation/` golden dataset + RAGAS runner (Phase 4)
- `.github/workflows/` CI/CD (Phase 6)
