"""Redis-backed blacklist + login rate limiting with in-memory fallback.

Fallback exists so unit tests and learning-mode runs work without Docker.
In production Redis is required (single source of truth across instances).
"""
import time

_memory_blacklist: dict[str, float] = {}  # jti -> expire_ts
_memory_limits: dict[str, tuple[int, float]] = {}  # key -> (count, expire_ts)

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


def _mem_sweep() -> None:
    now = time.time()
    for jti in [k for k, exp in _memory_blacklist.items() if exp <= now]:
        del _memory_blacklist[jti]
    for k in [k for k, (_, exp) in _memory_limits.items() if exp <= now]:
        del _memory_limits[k]


async def blacklist_jti(jti: str, ttl_seconds: int) -> None:
    _mem_sweep()
    try:
        from backend.app.core.redis_client import get_redis_client

        r = get_redis_client()
        await r.set(f"auth:blacklist:{jti}", "1", ex=max(1, int(ttl_seconds)))
        await r.aclose()
    except Exception:
        _memory_blacklist[jti] = time.time() + max(1, ttl_seconds)
    else:
        _memory_blacklist.pop(jti, None)


async def is_blacklisted(jti: str) -> bool:
    _mem_sweep()
    if jti in _memory_blacklist:
        return True
    try:
        from backend.app.core.redis_client import get_redis_client

        r = get_redis_client()
        hit = await r.exists(f"auth:blacklist:{jti}")
        await r.aclose()
        return bool(hit)
    except Exception:
        return jti in _memory_blacklist


async def is_login_locked(identifier: str) -> bool:
    """True when >=5 failures within 15 min window."""
    _mem_sweep()
    key = f"ratelimit:login:{identifier.lower()}"
    try:
        from backend.app.core.redis_client import get_redis_client

        r = get_redis_client()
        count = await r.get(key)
        await r.aclose()
        return int(count or 0) >= MAX_ATTEMPTS
    except Exception:
        entry = _memory_limits.get(key)
        return entry is not None and entry[0] >= MAX_ATTEMPTS


async def record_failed_login(identifier: str) -> None:
    key = f"ratelimit:login:{identifier.lower()}"
    try:
        from backend.app.core.redis_client import get_redis_client

        r = get_redis_client()
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, LOCKOUT_SECONDS)
        await r.aclose()
    except Exception:
        count, exp = _memory_limits.get(key, (0, time.time() + LOCKOUT_SECONDS))
        if exp <= time.time():
            count, exp = 0, time.time() + LOCKOUT_SECONDS
        _memory_limits[key] = (count + 1, exp)


async def reset_login_attempts(identifier: str) -> None:
    key = f"ratelimit:login:{identifier.lower()}"
    _memory_limits.pop(key, None)
    try:
        from backend.app.core.redis_client import get_redis_client

        r = get_redis_client()
        await r.delete(key)
        await r.aclose()
    except Exception:
        pass


async def clear_test_state() -> None:
    """Test-only: wipe memory fallback + Redis auth keys. Best-effort, never raises."""
    _memory_blacklist.clear()
    _memory_limits.clear()
    _memory_strikes.clear()
    try:
        from backend.app.core.redis_client import get_redis_client

        r = get_redis_client()
        for pattern in ("auth:blacklist:*", "ratelimit:login:*", "injection:*"):
            keys = [k async for k in r.scan_iter(match=pattern)]
            if keys:
                await r.delete(*keys)
        await r.aclose()
    except Exception:
        pass


INJECTION_MAX = 3
INJECTION_LOCK_SECONDS = 3600
_memory_strikes: dict[str, tuple[int, float]] = {}  # id -> (count, lock_until or 0)


async def record_injection(identifier: str) -> int:
    """Record a detected attempt. Returns total count."""
    key = f"injection:strikes:{identifier}"
    try:
        from backend.app.core.redis_client import get_redis_client

        r = get_redis_client()
        count = await r.incr(key)
        await r.expire(key, INJECTION_LOCK_SECONDS * 24)
        if count >= INJECTION_MAX:
            await r.set(f"injection:lock:{identifier}", "1", ex=INJECTION_LOCK_SECONDS)
        await r.aclose()
    except Exception:
        count, lock_until = _memory_strikes.get(identifier, (0, 0))
        count += 1
        if count >= INJECTION_MAX:
            lock_until = time.time() + INJECTION_LOCK_SECONDS
        _memory_strikes[identifier] = (count, lock_until)
    return count


async def is_injection_locked(identifier: str) -> bool:
    try:
        from backend.app.core.redis_client import get_redis_client

        r = get_redis_client()
        hit = await r.exists(f"injection:lock:{identifier}")
        await r.aclose()
        return bool(hit)
    except Exception:
        _, lock_until = _memory_strikes.get(identifier, (0, 0))
        return lock_until > time.time()
