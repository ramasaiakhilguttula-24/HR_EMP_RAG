# Observability runbook (Feature 16)

Traces live in LangSmith project `hr-rag-dev` (see `.env`: `LANGSMITH_API_KEY`,
`LANGSMITH_PROJECT`). Toggle with `LANGSMITH_TRACING=false` (code runs unchanged).

## What is traced per request
- `rag-answer` / `hr-agent` (chain): input query + `user_id`, `role`, `endpoint`
  metadata; output answer + citations; latency; token counts; exceptions
- `dense-search` / `hybrid-search` (retriever): query, top_k, filters, chunk ids + scores
- `groq-generate` (llm): full system+user prompt, raw response, `usage` tokens
- `cohere-rerank` (retriever): query, texts, relevance scores

## Dashboards (build in LangSmith UI → Dashboards)
- Latency: filter run name `rag-answer`, metric `p95 latency`, group by `endpoint`
- Cost/tokens: sum `prompt_tokens` + `completion_tokens` per day (Groq free tier → $0)
- Topics: group `rag-answer` by first 40 chars of input, or export `query_logs`
- Errors: filter runs with `status = error`

## Alerts (LangSmith UI → Automations, Slack webhook required)
- latency p95 > 5s on `rag-answer` → Slack
- error rate > 1% on `hr-agent` → Slack
- `injection_attempt` rows in Postgres → separate DB-backed alert (not LangSmith)

## Feedback loop
`POST /api/v1/feedback {query_log_id, score: +1|-1, run_id?}` writes
`query_logs.feedback` and attaches thumbs to the LangSmith run when `run_id`
is supplied. Frontend thumbs buttons call this endpoint (Phase 5).
