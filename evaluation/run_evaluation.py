"""Eval runner: golden Q&A -> live pipeline -> 5 metrics -> quality gates.

Usage:
  python evaluation/run_evaluation.py [--samples 6] [--mode hybrid] [--no-rerank]
                                      [--upload] [--gate/--no-gate]
- --samples N limits pairs (default 6 for quick runs; 0 = all 14).
- --mode/--no-rerank enable A/B comparisons of retrieval configs.
- --upload pushes the golden set to LangSmith datasets.
- Exit code 1 when any gate fails (CI regression gate).
"""
import argparse
import json
import sys
import time
from pathlib import Path

from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.services.evaluation.metrics import (  # noqa: E402
    METRICS,
    answer_correctness,
    answer_relevancy,
    check_gates,
    context_precision,
    context_recall,
    faithfulness,
)
from backend.app.services.generation.rag_pipeline import answer_query  # noqa: E402
from backend.app.services.retrieval.hybrid_search import hybrid_search  # noqa: E402


def load_dataset(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_results(path: Path) -> list[dict]:
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except ValueError:
            return []
    return []


def save_results(path: Path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, indent=1), encoding="utf-8")


def pending_items(items: list[dict], rows: list[dict]) -> list[dict]:
    done = {r.get("id") for r in rows}
    return [it for it in items if it["id"] not in done]


def _is_429(exc: Exception) -> bool:
    from httpx import HTTPStatusError

    return isinstance(exc, HTTPStatusError) and exc.response.status_code == 429


@retry(stop=stop_after_attempt(6), wait=wait_exponential(multiplier=10, min=10, max=180),
       retry=retry_if_exception(_is_429), reraise=True)
def _judge_generate(messages):
    from backend.app.services.generation.rag_pipeline import generate

    return generate(messages)


def run_one(item: dict, mode: str, rerank: bool, _generate, _embed) -> dict:
    from types import SimpleNamespace

    # Evaluate against the full corpus: retrieval honors RBAC, so run as admin.
    admin = SimpleNamespace(role=SimpleNamespace(value="admin"), department=None,
                            location=None, employment_type=None, seniority=None)
    res = answer_query(item["question"], top_k=5, search_mode=mode, rerank=rerank,
                       user=admin, _generate=_generate)
    if mode == "hybrid":
        chunks = hybrid_search(item["question"], top_k=5, user=admin)
    else:
        from backend.app.services.retrieval.vector_search import dense_search

        chunks = dense_search(item["question"], top_k=5, user=admin)
    contexts = [c.text for c in chunks]
    answer = res.answer if not res.fallback else "I don't know."
    row = {
        "id": item["id"],
        "faithfulness": faithfulness(answer, contexts, _generate),
        "answer_relevancy": answer_relevancy(item["question"], answer, _generate, _embed),
        "answer_correctness": answer_correctness(answer, item["ground_truth"], _generate),
    }
    if item.get("unanswerable") and res.fallback:
        # Correct refusal: retrieval metrics are not meaningful — exclude from averages.
        row["context_precision"] = None
        row["context_recall"] = None
    else:
        row["context_precision"] = context_precision(item["question"], contexts, _generate)
        row["context_recall"] = context_recall(item["ground_truth"], contexts, _generate)
    return row


def summarize(rows: list[dict]) -> dict[str, float]:
    out = {}
    for name in METRICS:
        vals = [r[name] for r in rows if r.get(name) is not None]
        out[name] = sum(vals) / len(vals) if vals else 0.0
    return out


def upload_dataset(items: list[dict]) -> None:
    from langsmith import Client

    settings = get_settings()
    client = Client(api_key=settings.LANGSMITH_API_KEY)
    names = [d.name for d in client.list_datasets()]
    if "hr-golden" not in names:
        ds = client.create_dataset("hr-golden", description="HR policy golden Q&A")
    else:
        ds = next(d for d in client.list_datasets() if d.name == "hr-golden")
    for item in items:
        client.create_example(inputs={"question": item["question"]},
                              outputs={"answer": item["ground_truth"]},
                              dataset_id=ds.id, metadata={"category": item["category"]})
    print(f"uploaded {len(items)} examples to hr-golden")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=6)
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "dense"])
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--no-gate", action="store_true")
    parser.add_argument("--pause", type=float, default=10.0,
                        help="Seconds to wait between samples (free-tier rate limits).")
    parser.add_argument("--resume", action="store_true",
                        help="Skip sample ids already in the results file.")
    parser.add_argument("--results", default="evaluation/results.json",
                        help="Checkpoint file for per-sample rows.")
    args = parser.parse_args()

    items = load_dataset(Path(__file__).with_name("golden_dataset.json"))
    if args.samples:
        items = items[: args.samples]
    results_path = Path(args.results)
    rows: list[dict] = load_results(results_path) if args.resume else []
    if args.resume and rows:
        print(f"resuming: {len(rows)} samples already done, skipping them")
    items = pending_items(items, rows)
    if args.upload:
        upload_dataset(load_dataset(Path(__file__).with_name("golden_dataset.json")))

    from backend.app.services.ingestion.embedder import get_embedder

    embedder = get_embedder()
    started = time.perf_counter()
    errors = 0
    total = len(items)
    for i, item in enumerate(items, 1):
        print(f"[{i}/{total}] {item['id']} ...", flush=True)
        try:
            row = run_one(item, args.mode, not args.no_rerank, _judge_generate,
                          embedder.embed_documents)
            rows.append(row)
            save_results(results_path, rows)
            print("   " + " ".join(f"{k}={row[k]:.2f}" if row[k] is not None else f"{k}=n/a"
                                   for k in METRICS), flush=True)
        except Exception as e:  # noqa: BLE001 - one bad sample must not kill the run
            errors += 1
            print(f"  ERROR {item['id']}: {type(e).__name__}: {str(e)[:150]}")
        if i < len(items):
            time.sleep(args.pause)
    scores = summarize(rows)
    print(f"\nconfig: mode={args.mode} rerank={not args.no_rerank} n={len(rows)} "
          f"({time.perf_counter() - started:.0f}s)")
    for name, (label, target) in METRICS.items():
        mark = "PASS" if scores.get(name, 0) >= target else "FAIL"
        print(f"  {label:20s} {scores.get(name, 0):.3f}  (target > {target})  {mark}")
    if args.no_gate:
        return 0
    if errors:
        print(f"INCOMPLETE: {errors}/{len(items)} samples errored — gate not meaningful.")
        return 2
    passed, failures = check_gates(scores)
    for f in failures:
        print("GATE FAIL:", f)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
