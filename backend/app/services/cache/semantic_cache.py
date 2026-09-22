"""Two-layer semantic cache (Feature 11): L1 in-memory LRU (100) + L2 Redis.

Hit order: exact key (L1, L2) then embedding-similarity (>= threshold, same params).
Every Redis op is best-effort — a down Redis degrades to L1 instead of failing.
"""
import hashlib
import json
import time
from collections import OrderedDict

from backend.app.core.config import get_settings

L1_CAP = 100
INDEX_KEY = "rag:cache:index"
INDEX_CAP = 500


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def cache_key(query: str, params: dict) -> str:
    canonical = json.dumps({"q": query.strip().lower(), "p": params or {}},
                           sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def params_hash(params: dict) -> str:
    return hashlib.sha256(json.dumps(params or {}, sort_keys=True,
                                     default=str).encode()).hexdigest()


class SemanticCache:
    def __init__(self, redis_fn=None, embed_fn=None,
                 ttl_std: int | None = None, ttl_ben: int | None = None,
                 sim_threshold: float | None = None) -> None:
        s = get_settings()
        self._redis_fn = redis_fn
        self._embed_fn = embed_fn
        self.ttl_std = s.CACHE_TTL_STANDARD if ttl_std is None else ttl_std
        self.ttl_ben = s.CACHE_TTL_BENEFITS if ttl_ben is None else ttl_ben
        self.sim_threshold = sim_threshold if sim_threshold is not None else s.CACHE_SIM_THRESHOLD
        self._l1: OrderedDict = OrderedDict()

    def _redis(self):
        from backend.app.core.redis_client import get_redis_client

        return (self._redis_fn or get_redis_client)()

    def _ttl(self, category: str | None) -> int:
        return self.ttl_ben if (category or "").lower() == "benefits" else self.ttl_std

    def _l1_get(self, key: str):
        entry = self._l1.get(key)
        if entry is None:
            return None
        if entry["exp"] <= time.time():
            del self._l1[key]
            return None
        self._l1.move_to_end(key)
        return entry["response"]

    def _l1_put(self, key: str, entry: dict) -> None:
        self._l1[key] = entry
        self._l1.move_to_end(key)
        while len(self._l1) > L1_CAP:
            self._l1.popitem(last=False)

    async def _l2_get(self, key: str):
        try:
            r = self._redis()
            raw = await r.get(f"rag:cache:{key}")
            await r.aclose()
            if not raw:
                return None
            entry = json.loads(raw)
            if entry["exp"] <= time.time():
                return None
            return entry
        except Exception:
            return None

    async def _l2_put(self, key: str, entry: dict, ttl: int) -> None:
        try:
            r = self._redis()
            await r.set(f"rag:cache:{key}", json.dumps(entry), ex=ttl)
            await r.sadd(INDEX_KEY, key)
            if await r.scard(INDEX_KEY) > INDEX_CAP:
                await r.spop(INDEX_KEY)
            await r.aclose()
        except Exception:
            pass

    async def _l2_scan(self, phash: str):
        try:
            r = self._redis()
            keys = [k async for k in r.scan_iter(match="rag:cache:*")]
            out = []
            for k in keys:
                if k == INDEX_KEY:
                    continue
                raw = await r.get(k)
                if raw:
                    out.append(json.loads(raw))
            await r.aclose()
            now = time.time()
            return [e for e in out if e.get("phash") == phash and e.get("exp", 0) > now]
        except Exception:
            return []

    def _embed(self, text: str) -> list[float] | None:
        try:
            fn = self._embed_fn
            if fn is None:
                from backend.app.services.ingestion.embedder import get_embedder

                fn = get_embedder().embed_query
            return [float(x) for x in fn(text)]
        except Exception:
            return None

    async def get(self, query: str, params: dict | None = None) -> dict | None:
        """Exact hit, else semantic hit. Returns stored response or None."""
        params = params or {}
        key = cache_key(query, params)
        hit = self._l1_get(key)
        if hit is not None:
            return hit
        entry = await self._l2_get(key)
        if entry is not None:
            self._l1_put(key, entry)
            return entry["response"]

        qvec = self._embed(query)
        if qvec is None:
            return None
        phash = params_hash(params)
        candidates = [e for e in self._l1.values()
                      if e.get("phash") == phash and e.get("exp", 0) > time.time()]
        candidates += await self._l2_scan(phash)
        best, best_sim = None, self.sim_threshold
        for e in candidates:
            sim = _cosine(qvec, e.get("emb", []))
            if sim >= best_sim:
                best, best_sim = e, sim
        if best is None:
            return None
        self._l1_put(key, best)
        return best["response"]

    async def put(self, query: str, params: dict | None, response: dict,
                  category: str | None = None) -> None:
        """Store response with query embedding for semantic hits."""
        params = params or {}
        emb = self._embed(query)
        if emb is None:
            return
        ttl = self._ttl(category)
        entry = {"response": response, "emb": emb, "phash": params_hash(params),
                 "exp": time.time() + ttl}
        key = cache_key(query, params)
        self._l1_put(key, entry)
        await self._l2_put(key, entry, ttl)

    async def invalidate(self) -> None:
        """Force-clear on document re-ingest."""
        self._l1.clear()
        try:
            r = self._redis()
            keys = [k async for k in r.scan_iter(match="rag:cache:*")]
            if keys:
                await r.delete(*keys)
            await r.delete(INDEX_KEY)
            await r.aclose()
        except Exception:
            pass


_cache: SemanticCache | None = None


def get_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache
