"""Metadata filter builder + LLM filter extraction (Feature 8).

Auto-filters come from the JWT user profile; manual filters win on conflict;
hr_manager/admin can disable profile filters for cross-department queries.
"""
import json

from qdrant_client.http.models import FieldCondition, Filter, MatchAny, MatchValue, Range

PROFILE_KEYS = ("department", "location", "employment_type", "seniority")

ROLE_ACCESS: dict[str, list[str] | None] = {
    # None = unrestricted (admin). Order: least to most privilege.
    "employee": ["public"],
    "hr_manager": ["public", "internal"],
    "department_head": ["public", "internal"],
    "legal_counsel": ["public", "internal", "restricted"],
    "admin": None,
}

PRIVILEGED_ROLES = ("hr_manager", "admin")


def profile_of(user) -> dict:
    """Extract filterable attributes from a User row (None values dropped)."""
    return {k: getattr(user, k, None) for k in PROFILE_KEYS if getattr(user, k, None)}


def build_qdrant_filter(
    user=None,
    manual: dict | None = None,
    use_profile_filters: bool = True,
) -> tuple[Filter, dict]:
    """Returns (Qdrant Filter, applied_filters dict for logging)."""
    manual = manual or {}
    applied: dict = {}

    role = (getattr(getattr(user, "role", None), "value", "") or "").lower()
    if use_profile_filters or role not in PRIVILEGED_ROLES:
        applied.update(profile_of(user) if user else {})
    # Manual filters override profile values.
    applied.update({k: v for k, v in manual.items() if v is not None and k != "effective_date_from"})

    must = [FieldCondition(key="is_active", match=MatchValue(value=True))]
    for key in ("department", "location", "employment_type", "policy_category", "seniority"):
        if applied.get(key):
            must.append(FieldCondition(key=key, match=MatchValue(value=applied[key])))
    # F14: chunk-level access control from JWT role.
    allowed = ROLE_ACCESS.get(role, ["public"])
    if allowed is not None:
        match = MatchValue(value=allowed[0]) if len(allowed) == 1 else MatchAny(any=allowed)
        must.append(FieldCondition(key="access_level", match=match))
    if manual.get("effective_date_from"):
        from backend.app.services.ingestion.pipeline import _to_epoch

        gte = _to_epoch(manual["effective_date_from"])
        if gte is not None:
            must.append(FieldCondition(key="effective_date_ts", range=Range(gte=gte)))
            applied["effective_date_from"] = manual["effective_date_from"]
    return Filter(must=must), applied


EXTRACT_SYSTEM = (
    "Extract HR metadata filters from the employee question. "
    "Return ONLY a JSON object with any of these keys: "
    "department, location, employment_type, policy_category, seniority. "
    "Omit keys not mentioned. Example: {\"location\": \"UK\"}"
)


def extract_filters_llm(query: str) -> dict:
    """Detect filter intent from query text (e.g. UK in 'leave rules for UK staff?')."""
    import httpx

    from backend.app.core.config import get_settings
    from backend.app.services.generation.rag_pipeline import GROQ_URL

    settings = get_settings()
    if not settings.GROQ_API_KEY:
        return {}
    try:
        with httpx.Client(timeout=20) as client:
            r = client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}",
                         "Content-Type": "application/json"},
                json={"model": settings.LLM_MODEL,
                      "messages": [{"role": "system", "content": EXTRACT_SYSTEM},
                                   {"role": "user", "content": query}],
                      "temperature": 0.0, "stream": False},
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"] or "{}"
        data = json.loads(content[content.index("{"): content.rindex("}") + 1])
        return {k: v for k, v in data.items()
                if k in ("department", "location", "employment_type", "policy_category", "seniority") and v}
    except Exception:
        return {}
