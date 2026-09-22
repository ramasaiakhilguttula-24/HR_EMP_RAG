"""Eval tests: metric math + gates + dataset schema (offline, faked LLM)."""
import json
from pathlib import Path
from unittest.mock import patch

from backend.app.services.evaluation.metrics import (
    METRICS,
    answer_correctness,
    answer_relevancy,
    check_gates,
    context_precision,
    context_recall,
    cosine,
    faithfulness,
    mean,
    split_sentences,
)


def _gen_yes(_msgs):
    return ("YES", {})


def _gen_no(_msgs):
    return ("NO", {})


def _gen_num(n):
    return lambda _msgs: (str(n), {})


def test_mean_cosine_sentences():
    assert mean([1.0, 0.5]) == 0.75 and mean([]) == 0.0
    assert abs(cosine([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert split_sentences("First. Second! Tiny") == ["First.", "Second!", "Tiny"]
    assert split_sentences("Hi. OK.") == []


def test_faithfulness_all_supported():
    gen = lambda msgs: ("Claim one\nClaim two", {}) if "Split" in msgs[0]["content"] else ("YES", {})
    assert faithfulness("answer", ["ctx"], gen) == 1.0


def test_faithfulness_none_supported():
    gen = lambda msgs: ("Only claim", {}) if "Split" in msgs[0]["content"] else ("NO", {})
    assert faithfulness("answer", ["ctx"], gen) == 0.0


def test_faithfulness_empty_answer():
    assert faithfulness("", ["ctx"], lambda m: ("", {})) == 0.0


def test_answer_relevancy_perfect():
    gen = lambda msgs: ("Q1\nQ2\nQ3", {})
    emb = lambda texts: [[1.0, 0.0] for _ in texts]
    assert answer_relevancy("q", "a", gen, emb) == 1.0


def test_context_precision_rank_weighted():
    calls = {"n": 0}

    def gen(msgs):
        calls["n"] += 1
        return ("YES" if calls["n"] == 1 else "NO", {})

    assert context_precision("q", ["c1", "c2"], gen) == 1.0  # only top ctx relevant
    assert context_precision("q", ["c1"], _gen_yes) == 1.0
    assert context_precision("q", ["c1"], _gen_no) == 0.0
    assert context_precision("q", [], _gen_yes) == 0.0


def test_context_recall_partial():
    calls = {"n": 0}

    def gen(msgs):
        calls["n"] += 1
        return ("YES" if calls["n"] == 1 else "NO", {})

    assert context_recall("Dogs bark. Cats meow.", ["dogs bark loudly"], gen) == 0.5
    assert context_recall("Dogs bark.", [], _gen_yes) == 0.0


def test_answer_correctness_parses_number():
    assert answer_correctness("a", "ref", _gen_num(87)) == 0.87
    assert answer_correctness("a", "ref", lambda m: ("no number", {})) == 0.0


def test_strip_markers_not_claims():
    from backend.app.services.evaluation.metrics import _strip_markers, faithfulness

    gen = lambda msgs: ("Only claim", {}) if "Split" in msgs[0]["content"] else ("YES", {})
    assert faithfulness("Answer here [1].", ["ctx"], gen) == 1.0
    assert "1" not in _strip_markers("Take 18 days [1].").replace("18", "")


def test_rerank_degradation_keeps_top_chunk():
    from backend.app.services.generation.rag_pipeline import prepare
    from backend.app.services.retrieval.vector_search import RetrievedChunk

    chunk = RetrievedChunk("c1", "text", 0.9, "d", "doc.pdf", 1, None, 1)
    with patch("backend.app.services.retrieval.hybrid_search.hybrid_search",
               return_value=[chunk]), \
         patch("backend.app.services.retrieval.reranker.rerank_chunks", return_value=[]):
        chunks, _, _, fb = prepare("q?", top_k=5, search_mode="hybrid", rerank=True)
    assert fb is None and chunks == [chunk]


def test_check_gates():
    good = {name: target for name, (_, target) in METRICS.items()}
    passed, failures = check_gates(good)
    assert passed and failures == []
    bad = dict(good, faithfulness=0.1)
    passed, failures = check_gates(bad)
    assert not passed and len(failures) == 1 and "faithfulness" in failures[0]


def test_resume_helpers(tmp_path):
    import sys

    sys.path.insert(0, "evaluation")
    try:
        from run_evaluation import load_results, pending_items, save_results

        assert load_results(tmp_path / "missing.json") == []
        rows = [{"id": "a", "faithfulness": 1.0}]
        save_results(tmp_path / "r.json", rows)
        assert load_results(tmp_path / "r.json") == rows
        items = [{"id": "a"}, {"id": "b"}]
        assert [i["id"] for i in pending_items(items, rows)] == ["b"]
        assert pending_items(items, []) == items
    finally:
        sys.path.remove("evaluation")


def test_golden_dataset_schema():
    items = json.loads(Path("evaluation/golden_dataset.json").read_text(encoding="utf-8"))
    assert len(items) >= 10
    ids = set()
    for item in items:
        assert {"id", "category", "question", "ground_truth"} <= set(item.keys())
        assert item["question"].strip() and item["ground_truth"].strip()
        assert item["id"] not in ids
        ids.add(item["id"])
    cats = {item["category"] for item in items}
    assert {"Leave", "Separation", "Code of Conduct", "Compliance"} <= cats
