# Project Context — HR Employee Policy RAG (checkpoint)

> Purpose: resume checkpoint for multiple agents / IDEs. Update this file after
> every feature and phase. Source of truth for "where did we stop".
> Last updated: 2026-09-21 — after Phase 3 (F12–F14 Security), post-restart re-verified.

## 1. Goal (one line)
Production-grade HR policy RAG (ask HR questions, get cited answers) built
incrementally to **learn RAG systems**. Plan: `project_plan.md` (20 features,
6 phases). Design: `project_related_info.md`.

## 2. Status

| # | Item | State | Notes |
|---|------|-------|-------|
| F1 | Project Planning | DONE | plan + `project_related_info.md` system design stored |
| F2 | Backend Foundation | DONE | FastAPI, Postgres+SQLAlchemy+Alembic, Qdrant, Redis, `/health` `/ready`, 5 tests |
| - | Project Directory | DONE | full skeleton per plan (backend/frontend/worker/infra/.github/evaluation), stubs only |
| F3 | Authentication | DONE | JWT rotation, 4 endpoints, blacklist, rate-limit; 16 new tests; **21/21 total pass** |
| F4 | Document Ingestion | DONE (verified live) | parsers/chunker/HF embedder/pipeline/upload API; 24 new tests; **45/45 pass**; 2 sample docs ingested + searched |
| F5 | Basic Retrieval | DONE (verified live) | dense search + MMR + `POST /retrieve` + query logging; 8 new tests; **53/53 pass** |
| F6 | Basic RAG (LLM) | DONE (verified live) | Groq generate + citations + `POST /chat` + SSE `/chat/stream` + fallback; 9 new tests |
| F7 | Citations | DONE (included in F6) | numbered excerpts + citations array; marker style tuning deferred to eval |
| F8 | Metadata Filtering | DONE (verified live) | profile auto-filter + manual override + LLM extraction + date range; 9 new tests; **71/71 pass** |
| F9 | Hybrid Search | DONE (verified live) | BM25 sparse (fastembed) + RRF/weighted fusion, normalized scores; 6 new tests |
| F10 | Reranking | DONE (verified live) | Cohere `rerank-english-v3.0`, top20→top5, 0.3 threshold; 6 new tests |
| F11 | Response Caching | DONE (verified live) | L1 LRU(100) + L2 Redis, semantic ≥0.95, TTL 24h/1h, invalidate on ingest; 10 new tests; **94/94 pass** |
| F12 | Prompt Injection | DONE (verified live) | regex + embedding-sim + Groq judge, 3-strikes 1h lock, security_events log; webhook stubbed |
| F13 | PII Masking | DONE (verified live) | pattern engine + Presidio anonymizer, ingest+query+output scan, audit; one-way (no vault) |
| F14 | RBAC | DONE (verified live) | ROLE_ACCESS matrix enforced in Qdrant filter, deny-audit, admin role APIs; PG RLS deferred; **130/130 pass** |
| F15 | Agentic RAG | DONE (verified live) | LangGraph ReAct (5-step cap), 5 tools, search-first enforced, escalation tickets; 11 new tests; **141/141 pass** |
| F18 | Frontend | DONE (build green, API-verified) | Prism HR theme, chat+agent+admin, custom JWT auth; CORS fixed+verified; live stream proof ok; pool_pre_ping fix from user testing |
| F16 | Monitoring | DONE (verified live) | @traceable on 6 fns, user metadata, feedback API, runbook; nested runs in `hr-rag-dev`; 5 new tests; **146/146 pass** |
| F17 | Evaluation | CODE DONE, full run pending | 14-pair golden set, 5 in-house metrics (ragas pkg broken upstream), gates + CI job + LangSmith upload; 13 tests; **159/159 pass**; full eval paused at 4/14 (Groq 429s) — `evaluation/results.json` checkpointed, resume with `--resume` |
| F17 | Evaluation | NEXT | RAGAS suite + golden dataset (after F16 live check) |

Phases: Phase 1 (F1–F7) DONE. Phase 2 (F8–F11) DONE. Phase 3 (F12–F14) DONE. Phase 4 in progress. F16–F20 not started.

## 3. What exists (key files)
- `backend/app/main.py` — app factory, routers: health (no prefix) + auth (`/api/v1`)
- `backend/app/api/v1/auth.py` — register/login/refresh/logout
- `backend/app/core/` — `config.py`, `database.py` (asyncpg), `qdrant.py`, `redis_client.py`,
  `security.py` (bcrypt + JWT), `token_blacklist.py` (Redis + memory fallback), `dependencies.py`
  (`get_current_user`, `require_role`)
- `backend/app/models/` — `user.py` (5 roles), `document.py`, `query_log.py` (`query_logs`, `security_events`)
- `backend/app/schemas/auth.py` — auth DTOs
- `backend/app/services/*` — stubs only (ingestion/retrieval/generation/security/cache)
- Tests: `test_foundation.py`, `test_models.py`, `test_auth_security.py`,
  `test_auth_api.py`, `test_parser.py`, `test_chunker.py`, `test_ingestion.py`,
  `test_documents_api.py`. Run: `python -m pytest backend/tests -q` → 45 passed (2026-09-21).
- Ingestion (F4): `services/ingestion/{parser,chunker,embedder,pipeline}.py`,
  `api/v1/documents.py` (upload/list/get), `sample_docs/`, `scripts/init_db.py`.
  Deviations from plan: pypdf not PyMuPDF (native DLL blocked on this machine),
  no OCR/`unstructured` (deferred), FastAPI BackgroundTasks not Celery (worker file
  calls same pipeline; Celery in Phase 6), HF bge-large 1024-dim (not OpenAI 1536).
- Retrieval (F5): `services/retrieval/vector_search.py` (dense + MMR, is_active filter;
  access_level filter deferred to Phase 3 RBAC), `schemas/retrieval.py`,
  `POST /api/v1/retrieve` in `api/v1/chat.py` with `query_logs` feedback loop.
  Live: "paternity leave?" → leave_policy.md first (0.758).
- Filtering (F8): `services/retrieval/filters.py` (profile auto-filter, manual-wins merge,
  hr_manager/admin bypass, LLM JSON extraction via Groq, `effective_date_ts` epoch for
  numeric date ranges); `seniority` added to users/documents (+live ALTER TABLE);
  `filters/use_profile_filters/extract_filters` on `/retrieve` + `/chat`.
  Live: India user → 2 hits, US user → 0; LLM extracted {location UK, category leave}.
- Security (F12–F14): `injection_detector.py` (regex→embedding-sim→Groq judge, strikes in
  `token_blacklist.py`, 403 guard on all 3 query endpoints); `pii_masker.py` (Presidio
  AnonymizerEngine + built-in pattern detectors — AnalyzerEngine/spaCy blocked by this
  machine's policy; PERSON = indicator-scoped heuristic); `ROLE_ACCESS` matrix in
  `filters.py` enforced server-side; `admin.py` user/role APIs; deny-audit best-effort.
  Deviations: no reversible PII vault (one-way by design), PG RLS deferred (single app DB
  role — app-layer enforcement is the right layer), Slack webhook stubbed.
  Live: attack→regex block; PII masked at ingest (v4 pii_masked clean); employee/hr blind
  to restricted posh, legal/admin see it; versioning v1–v3 deactivated via soft-delete.
- Guard fix (from user testing): endpoint called detect() without embedder, so EVERY query
  went to the LLM judge (which false-positived "Article 12.3"); detect() now always embeds,
  judge sees borderline only; judge prompt sharpened toward clear attacks.
- Search intelligence (F9–F11): collection uses NAMED vectors (`dense` 1024 + `bm25` sparse;
  all queries pass `using=`); `hybrid_search.py` (RRF default + `weighted` alpha blend,
  scores min-max normalized); `reranker.py` (Cohere, drop <0.3); `semantic_cache.py`
  (L1 LRU + L2 Redis, exact→semantic, invalidate on ingest wired in upload task);
  `/retrieve` + `/chat` gained `search_mode`/`rerank`, `/chat` gained `cached` flag + cache.
  Live: sparse-only puts posh first (1.0 vs 0.014); rerank picks posh (0.9566) dropping rest;
  cache exact+paraphrase hits, invalidate verified. Note: RRF can tie symmetric ranks.
- Generation (F6): `services/generation/rag_pipeline.py` (direct Groq httpx client, no
  LangChain — transparent prompts; temp 0.1; 6000-char context budget; score<0.5 fallback),
  `schemas/chat.py`, `POST /api/v1/chat` + SSE `POST /api/v1/chat/stream` (citations event
  first, then tokens, then [DONE]). Live: annual-leave Q → correct "18 days" + 2 citations
  (381 in / 62 out tokens). Note: model used 【1】-style markers once — style tuning in eval.
- Agents (F15): `services/generation/agent.py` (LangGraph StateGraph think→act→finalize,
  5-step cap, search-first enforcement after live caught a direct-answer hallucination);
  5 tools (search/compare/calculate/escalate/metadata); `escalations` table;
  `POST /api/v1/agent/chat` with step trace. Live: 3.5y tenure → search → correct 60 days.
- Observability (F16): `core/tracing.py` (call-time bypass wrapper — zero network/pollution
  when disabled; suite-wide conftest forces OFF); traced: rag-answer, hr-agent, dense/hybrid
  search, groq-generate, cohere-rerank with user metadata; `POST /feedback` (Postgres +
  LangSmith thumbs attach); `docs/observability.md` (dashboard/alert recipes — UI objects
  themselves live in LangSmith, not code). Live fix found: SDK is env-driven, so
  `tracing._ensure_env()` exports key/project from Settings. Deviations: dashboards/alerts
  are recipes, not API-created; cost logged as tokens (Groq free tier → $0).
- Infra: `.env.example`, `docker-compose.yml`, `docker-compose.prod.yml`, `backend/alembic/*`,
  `scripts/create_qdrant_collection.py`, `frontend/*` (placeholder), `worker/*` (stub),
  `infrastructure/*`, `.github/workflows/*`, `evaluation/golden_dataset.json`.

## 4. Environment / infra state (Docker setup DONE 2026-09-21)
- OS Python 3.12.10. Docker Desktop 4.83.0 (engine 29.6.2) + Compose v5.3.1.
- `.env` created from `.env.example`. Non-standard host ports (conflicts documented below).
- Containers UP: `hr-rag-postgres` (host 5433->5432), `hr-rag-qdrant` (6333/6334),
  `hr-rag-redis` (host 6380->6379). `/ready` = `ready`, all checks `up`.
- Port conflicts (other local projects — DO NOT stop them, we remapped instead):
  - host 5432 held by native Windows Postgres (PID 9136) → ours on **5433**
  - host 6379 held by `text2sql-redis` container → ours on **6380**
  - `.env`: `DATABASE_URL=...@localhost:5433/hr_rag`, `REDIS_URL=redis://localhost:6380/0`
- Tables created via `scripts/init_db.py`: users, documents, query_logs, security_events.
- Qdrant collection `hr_policies` created (client 1.19.0 vs server 1.9.0 warning is harmless).
- 2026-09-21: Qdrant upgraded v1.9.0→v1.19.1 (client 1.19 dropped old `search`; server 1.9
  lacked `query_points`). Old volume wiped (format incompatible, only 2 sample points lost).
  Live verified: HF bge-large embed (1024-dim) → ingest 2 sample docs → query
  "How many days of annual leave?" returns leave_policy.md first (0.735).
- `requirements.txt` includes: fastapi, uvicorn, sqlalchemy, asyncpg, alembic,
  pydantic-settings, qdrant-client, redis, httpx, python-jose, passlib[bcrypt], email-validator.

## 5. Key decisions (do not re-litigate without reason)
- Modular monolith; single Qdrant collection `hr_policies` (1536-dim, cosine).
- Chunking 512/64 (F4). Auth: access 15m + refresh 7d with rotation; blacklist in Redis.
- Login rate-limit: 5 fails → 15 min lockout. Email verification STUBBED, SSO SKIPPED.
- Tests must pass without Docker (mock DB session, memory fallback for Redis).

## 6. Agreement with user
Ping user BEFORE starting any feature/phase that needs user-side input
(env keys, Docker, accounts, installs). F3 needed nothing — built directly.

## 7. How to resume
```bash
cd C:\Users\Akhil\Desktop\HR_EMP_RAG
copy .env.example .env   # then set JWT_SECRET + later OPENAI_API_KEY
docker compose up -d postgres redis qdrant
alembic upgrade head
python scripts/create_qdrant_collection.py
uvicorn backend.main:app --reload   # docs: http://localhost:8000/docs
python -m pytest backend/tests -q
```

## 8. Next (F17 full-eval resume → F19/F20 deploy)
Eval resume: `python evaluation/run_evaluation.py --samples 0 --pause 15 --resume`
(checkpoint holds 4/14). Pre-deploy audit 2026-09-22 DONE (see above). Deploy track
decision still needed: Railway (fast) vs AWS (full plan).

## 9. Update log
- 2026-09-22: pre-deploy audit: secrets clean (real HF token scrubbed from `.env.example`;
  keys only in gitignored `.env`), `.gitignore` created, config parity 36/36, 17 routes
  all covered by UI, backend 160/160, `pool_pre_ping` fix from user testing. F19 punchlist:
  multi-stage Dockerfiles, worker build-context fix, frontend API-URL build-arg, nginx
  service, compose healthchecks, DB init at deploy (alembic empty — `init_db.py` is real path).
- 2026-09-19: created; F1–F3 marked DONE; 21/21 tests recorded.
- 2026-09-21: Docker setup DONE (3 containers up, ports 5433/6380 remapped, tables +
  Qdrant collection created, /ready = ready). Added `scripts/init_db.py`.
- 2026-09-21: F4 DONE, 45/45 pass. Groq key verified (LLM-only, no embeddings).
  Embeddings = HF bge-large (1024-dim, collection recreated). HF_TOKEN not yet in
  `.env` — live check pending. Auth-test isolation fixed for live Redis.
