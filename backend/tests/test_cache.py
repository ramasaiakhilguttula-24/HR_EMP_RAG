"""Semantic cache tests: exact/semantic hits, TTL, LRU, invalidate, Redis-down."""
import asyncio

from backend.app.services.cache.semantic_cache import SemanticCache, cache_key


def _cache(**kw):
    kw.setdefault("redis_fn", lambda: (_ for _ in ()).throw(Exception("no redis")))
    kw.setdefault("embed_fn", lambda t: [1.0, 0.0] if "leave" in t else [0.0, 1.0])
    return SemanticCache(**kw)


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


RESP = {"answer": "18 days [1].", "citations": []}


def test_exact_hit():
    c = _cache()
    run(c.put("How many leaves?", {"top_k": 5}, RESP))
    assert run(c.get("How many leaves?", {"top_k": 5})) == RESP


def test_normalized_query_matches():
    c = _cache()
    run(c.put("How many leaves?", {}, RESP))
    assert run(c.get("  how MANY leaves? ", {})) == RESP


def test_params_mismatch_misses():
    c = _cache()
    run(c.put("leaves?", {"top_k": 5}, RESP))
    assert run(c.get("leaves?", {"top_k": 3})) is None


def test_semantic_hit_paraphrase():
    c = _cache()
    run(c.put("annual leave days?", {"m": "h"}, RESP))
    # different wording, same fake embedding bucket
    assert run(c.get("annual leave days!", {"m": "h"})) == RESP


def test_semantic_miss_different_meaning():
    c = _cache(embed_fn=lambda t: [1.0, 0.0])
    run(c.put("leave policy?", {}, RESP))
    c._embed_fn = lambda t: [0.0, 1.0]  # new query embeds far away
    assert run(c.get("leave policy!", {})) is None


def test_expired_entry_misses():
    c = _cache(ttl_std=0, ttl_ben=0)
    run(c.put("q?", {}, RESP))
    assert run(c.get("q?", {})) is None


def test_lru_eviction():
    from backend.app.services.cache import semantic_cache as sc

    old_cap = sc.L1_CAP
    sc.L1_CAP = 3
    try:
        c = _cache()
        for i in range(4):
            run(c.put(f"q{i}?", {"i": i}, RESP))
        assert run(c.get("q0?", {"i": 0})) is None
        assert run(c.get("q3?", {"i": 3})) == RESP
    finally:
        sc.L1_CAP = old_cap


def test_invalidate_clears():
    c = _cache()
    run(c.put("q?", {}, RESP))
    run(c.invalidate())
    assert run(c.get("q?", {})) is None


def test_cache_key_stable():
    assert cache_key("A?", {"x": 1}) == cache_key("a? ", {"x": 1})
    assert cache_key("A?", {"x": 1}) != cache_key("A?", {"x": 2})


def test_benefits_ttl_shorter():
    c = _cache(ttl_std=100, ttl_ben=50)
    assert c._ttl("Benefits") == 50
    assert c._ttl("Leave") == 100
    assert c._ttl(None) == 100
