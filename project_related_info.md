# HR Employee Policy RAG - System Design & Reference
> Companion to `project_plan.md`. Goal: simple to understand, efficient to build, covers all 20 features without rework across phases.
> Last updated: 2026-09-19 | Phase: 1 - Project Planning

---

## 1. Design Principles (Keep It Simple, Make It Work)

1. **Modular monolith, not microservices:** One FastAPI backend + one Celery worker. Easy to run locally, easy to scale later via Docker.
2. **Single source of truth per data type:**
   - PostgreSQL = structured data (users, docs metadata, logs)
   - Qdrant = vectors + payload (searchable knowledge)
   - Redis = ephemeral data (cache, blacklist, queue)
3. **One collection, smart filters:** Single Qdrant collection `hr_policies` with rich payload filters (department, location, role, version). No need for per-dept collections.
4. **Pluggable interfaces:** `Embedder`, `LLMProvider`, `Reranker` as interfaces. Start with OpenAI, swap to local later without rewriting pipeline.
5. **Security as middleware:** Auth -> RBAC filter -> Injection check -> PII check run on every query in fixed order.
6. **Every answer is auditable:** Every query stores: query, filters, retrieved chunk_ids + scores, prompt, answer, citations, latency, cost.

---

## 2. High-Level Architecture

```
                    +------------------+
                    |  Next.js Frontend| (Phase 5)
                    | Chat + Admin UI  |
                    +--------+---------+
                             | HTTPS / SSE
                    +--------v---------+
                    |  Nginx (Phase 6) |
                    +--------+---------+
                             |
              +--------------v--------------+
              |      FastAPI Backend        |
              |  /auth /documents /chat     |
              |  /retrieve /admin           |
              +--+------+------+------+----+
                 |      |      |      |
        +--------v-+ +--v---+ +-v----+ +--v-----+
        | Postgres | |Qdrant| |Redis | | LLM API|
        | users    | |vectors| |cache| | GPT-4o |
        | docs     | |payload| |black| | embed  |
        | logs     | |HNSW  | |queue| | rerank |
        +----------+ +------+ +-----+ +--------+
                 ^                    |
                 |        +-----------v----------+
                 |        | Celery Worker        |
                 +--------| Ingest: parse->chunk |
                          | ->embed->upsert      |
                          +----------------------+
        Observability: LangSmith traces all LLM calls (Phase 4)
        Evaluation: RAGAS on golden_dataset.json (Phase 4)
```

**Local dev (Phase 1-4):** `docker-compose` runs postgres, qdrant, redis. Backend + worker run via `uvicorn` + `celery` directly for fast iteration.
**Prod (Phase 6):** Everything containerized, AWS ECS + RDS + ElastiCache, Terraform.

---

## 3. Core Data Flows

### 3.1 Document Upload Flow (Ingestion)
```
HR Manager -> POST /documents/upload (JWT + hr_manager role)
  -> Save file to /uploads + row in documents table (status=processing)
  -> Celery task:
    1. Parse (PyMuPDF / python-docx / openpyxl)
    2. Clean + PII mask (Presidio) [Phase 3, stub in Phase 1]
    3. Chunk (512 tokens, 64 overlap, keep page_no, heading)
    4. Embed (text-embedding-3-small)
    5. Upsert to Qdrant with payload
    6. Update documents.status=ready, invalidate Redis cache for that doc
```

### 3.2 Query Flow (Retrieval + Generation)
```
Employee -> POST /chat {query} (JWT)
  1. Auth + load user profile (dept, location, role)
  2. Injection check (regex in Phase 3, block if malicious)
  3. PII scan on query
  4. Cache lookup: hash(normalized_query + filters) -> Redis [Phase 2]
     -> HIT: return in ~50ms
  5. Build Qdrant filter: access_level <= user.role + dept/location auto-filter
  6. Retrieve:
     Phase 1: dense top-10 (cosine)
     Phase 2: dense + BM25 sparse -> RRF fusion -> rerank top-20 to top-5
  7. Threshold check: if top score <0.5 (or <0.3 after rerank) -> fallback "contact HR"
  8. Build prompt: system (answer ONLY from context) + chunks + query
  9. LLM generate (temp 0.1, streaming via SSE)
  10. Extract citations [doc_name, page, section, excerpt]
  11. PII scan on answer, save to query_logs + audit, cache answer (TTL by category)
  12. Return {answer, citations[], latency, cached:false}
```

### 3.3 Agentic Flow (Phase 4, extension of 3.2)
```
Complex query -> LangGraph ReAct (max 5 steps)
  Tools: search_policy, compare_documents, calculate_entitlement, escalate_to_hr, get_document_metadata
  Example: "India vs UK maternity?" -> 2x search_policy -> compare_documents -> synthesize
```

---

## 4. Database Schemas

### 4.1 PostgreSQL (SQLAlchemy + Alembic)

```sql
-- users
users(id UUID PK, email UNIQUE, password_hash, full_name,
      role ENUM[employee,hr_manager,department_head,legal_counsel,admin],
      department VARCHAR, location VARCHAR, employment_type VARCHAR,
      is_active BOOL, created_at, updated_at)

-- documents (metadata, not content)
documents(id UUID PK, file_name, file_type, file_size, s3_path,
          department, location, policy_category, access_level,
          version INT DEFAULT 1, effective_date DATE,
          status ENUM[processing,ready,failed,archived],
          uploaded_by FK->users.id, created_at, updated_at)

-- query_logs (audit + eval)
query_logs(id UUID PK, user_id FK, query TEXT, normalized_query TEXT,
           filters JSONB, retrieved_chunk_ids TEXT[],
           retrieval_scores FLOAT[], answer TEXT, citations JSONB,
           latency_ms INT, tokens_in INT, tokens_out INT, cost_usd FLOAT,
           cache_hit BOOL, feedback SMALLINT NULL, created_at)

-- security_events
security_events(id UUID PK, user_id FK, event_type ENUM[injection_attempt,pii_detected,rbac_denied],
                details JSONB, created_at)

-- refresh_tokens (optional, if not using Redis only)
-- Can be Redis-only; kept here for reference if needed.
```

### 4.2 Qdrant Collection: `hr_policies`

```json
{
  "vector_size": 1536,
  "distance": "Cosine",
  "hnsw": {"m": 16, "ef_construct": 100},
  "sparse_vectors": {"bm25": {}},
  "payload_schema": {
    "document_id": "uuid",
    "document_name": "keyword",
    "chunk_id": "keyword",
    "chunk_index": "integer",
    "text": "text",
    "page_number": "integer",
    "section_heading": "keyword",
    "department": "keyword",
    "location": "keyword",
    "policy_category": "keyword",
    "employment_type": "keyword",
    "access_level": "keyword",
    "version": "integer",
    "effective_date": "datetime",
    "is_active": "bool"
  }
}
```

Chunk ID format: `{document_id}_{chunk_index}_v{version}`. On re-ingest: `is_active=false` for old version (soft delete), insert new version.

### 4.3 Redis Keys

```
rag:cache:{sha256(query+filters)} -> {answer, citations} TTL 86400 (24h) / 3600 (benefits)
auth:blacklist:{jti} -> 1 TTL = token remaining TTL
celery:queue -> ingestion tasks
ratelimit:login:{ip} -> count TTL 900
```

---

## 5. API Contract (FastAPI /api/v1)

```
POST /auth/register {email,password,full_name,department,location} -> 201
POST /auth/login {email,password} -> {access_token(15m), refresh_token(7d)}
POST /auth/refresh {refresh_token} -> {access_token}
POST /auth/logout -> blacklist (auth required)

POST /documents/upload (multipart, hr_manager+) -> {document_id, status}
GET  /documents?page,limit,category -> list
GET  /documents/{id} -> metadata + versions
DELETE /documents/{id} -> soft delete (admin/hr_manager)

POST /retrieve {query, top_k=10, filters?} -> {chunks[{chunk_id,text,score,document_name,page}]}
POST /chat {query, filters?, stream=false} -> {answer, citations[{document,page,section,excerpt,url}], latency_ms, cached}
POST /chat/stream -> SSE stream (Phase 1 week 3)

GET  /admin/users, PATCH /admin/users/{id}/role (admin)
GET  /admin/stats {query_volume, cache_hit_rate, avg_latency, cost_today}
POST /feedback {query_log_id, score:+1/-1}
GET  /health, GET /ready
```

Auth: `Authorization: Bearer <access_token>`. Role guard via FastAPI `Depends(require_role(...))`.

---

## 6. Security Design (Phase 3, stubs in Phase 1)

Order per request: `Authenticate -> RBAC filter -> Injection detect -> PII mask -> Retrieve -> PII scan output -> Audit log`

| Role | Can access |
|------|------------|
| employee | access_level=public (leave, benefits, conduct) |
| hr_manager | public + internal (salary bands, reviews) |
| department_head | public + own dept disciplinary |
| legal_counsel | public + compliance/legal/disputes |
| admin | all + config |

- Injection: Layer1 regex (`ignore previous instructions|forget system|DAN mode|jailbreak|act as`), Layer2 embedding classifier, Layer3 LLM judge. 3 strikes = suspend.
- PII: Presidio at ingest (tokenize) + query/output scan. Mapping table only readable by hr_manager+.
- All denials logged to `security_events` + Slack webhook.

---

## 7. Performance & Quality Targets

| Metric | Target | How |
|--------|--------|-----|
| Chat p95 latency (cache miss) | <3s | HNSW, top-10, async, streaming |
| Chat latency (cache hit) | <200ms | Redis semantic cache, hit rate >60% |
| Rerank overhead | +100-300ms | only on miss, top-20->top-5 |
| Faithfulness (RAGAS) | >0.85 | strict prompt, temp 0.1, threshold |
| Answer Relevancy | >0.80 | rerank + MMR |
| Context Precision | >0.75 | hybrid + filters |

Cache TTL: standard 24h, benefits 1h, invalidate on doc re-ingest.

---

## 8. Config (.env) Design

```env
# App
APP_NAME=hr-policy-rag
ENV=dev
API_PREFIX=/api/v1

# DBs
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/hr_rag
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=hr_policies
REDIS_URL=redis://localhost:6379/0

# Auth
JWT_SECRET=change-me
JWT_ALG=HS256
ACCESS_TTL_MIN=15
REFRESH_TTL_DAYS=7

# Models
EMBED_MODEL=text-embedding-3-small
EMBED_DIM=1536
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
LLM_TEMP=0.1
RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
COHERE_API_KEY=

# RAG tuning
CHUNK_SIZE=512
CHUNK_OVERLAP=64
TOP_K_RETRIEVE=10
TOP_K_RERANK=5
SCORE_THRESHOLD=0.5

# Observability
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=hr-rag-dev
```

All accessed via `pydantic-settings BaseSettings`. No secrets in code.

---

## 9. Simplified Repo Layout (for learning, maps to plan structure)

```
hr-policy-rag/
  backend/
    app/
      api/v1/ (auth.py, documents.py, chat.py, admin.py)
      core/ (config.py, security.py, dependencies.py)
      models/ (user.py, document.py, query_log.py)
      services/
        ingestion/ (parser.py, chunker.py, embedder.py)
        retrieval/ (vector_search.py, hybrid_search.py, reranker.py)
        generation/ (rag_pipeline.py, agent.py)
        security/ (injection_detector.py, pii_masker.py)
        cache/ (semantic_cache.py)
    tests/ (unit/, integration/, evaluation/)
    main.py
  frontend/ (Phase 5)
  worker/tasks/ingestion_tasks.py
  infrastructure/terraform/ + nginx/
  evaluation/golden_dataset.json + run_evaluation.py
  docker-compose.yml
  .env.example
```

Start Phase 1 with only: `core, models, ingestion/{parser,chunker,embedder}, retrieval/vector_search, generation/rag_pipeline, api/{auth,documents,chat}`. Add other folders as stubs.

---

## 10. Phase Mapping (no rework)

- P1: Build flows 3.1 + 3.2 dense-only, no cache/rerank (leave hooks: `get_filters()`, `rerank()` as pass-through).
- P2: Fill in `hybrid_search.py`, `reranker.py`, `semantic_cache.py` + metadata extraction.
- P3: Fill in `injection_detector.py`, `pii_masker.py`, enforce `access_level` filter + role guards.
- P4: Add `agent.py` reusing `search_policy` tool (= existing retrieval), add LangSmith `@traceable`, add `evaluation/`.
- P5: Frontend consumes existing `/chat`, `/documents`, `/admin` APIs unchanged.
- P6: Dockerize same code, Terraform + CI/CD.

---

## 11. Key Decisions Log

| Decision | Choice | Why |
|----------|--------|-----|
| Backend | FastAPI async | Docs, DI, SSE streaming |
| Vector DB | Qdrant | Filters + sparse + HNSW in one |
| Chunking | 512 / 64 recursive | Good balance for policy paras; tune via eval later |
| Embeddings | text-embedding-3-small | Cheap, 1536-dim, easy; bge-large later for local |
| LLM | GPT-4o, temp 0.1 | Factual, cited; interface allows swap |
| Cache | Redis semantic | HR queries repeat heavily |
| Queue | Celery+Redis | Non-blocking uploads, already have Redis |

---

## 12. Next Steps (Phase 1 Week 1)

- [ ] Init repo, `.env.example`, `docker-compose.yml` (postgres, qdrant, redis)
- [ ] FastAPI skeleton + `/health`, `/ready` + Pydantic settings
- [ ] SQLAlchemy models (users, documents, query_logs) + Alembic
- [ ] Qdrant collection creation script
- [ ] Unit tests for config + health

*Reference: see `project_plan.md` Phase 1 Milestone Tasks for full checklist.*
