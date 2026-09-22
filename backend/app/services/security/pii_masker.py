"""PII detection + masking (Feature 13).

Uses Presidio AnonymizerEngine for replacement. Detection uses built-in pattern
recognizers (email/phone/SSN/PAN/dates/salary/medical) because Presidio's
AnalyzerEngine (spaCy NER) cannot load on machines with strict Application
Control policies — where it imports, swap `_find_spans` for AnalyzerEngine and
keep the same `mask_text` contract. No reversible vault by design (one-way).
"""
import re

HR_PATTERNS: list[tuple[str, str]] = [
    ("EMAIL_ADDRESS", r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),
    ("US_SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
    ("IN_PAN", r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    ("PHONE_NUMBER", r"\+?\d[\d\s\-()]{7,}\d"),
    ("DATE_OF_BIRTH", r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    ("SALARY", r"(?:₹|\$|Rs\.?|INR)\s?[\d,]+(?:\s?(?:per annum|p\.a\.|lakh|LPA))?"),
    ("SALARY", r"\b\d[\d,]*\s?(?:per annum|p\.a\.|LPA|lakh(?:s)?\s?(?:per annum)?)\b"),
]

MEDICAL_TERMS = [
    "cancer", "depression", "diabetes", "hiv", "aids", "tuberculosis", "asthma",
    "epilepsy", "anxiety", "bipolar", "schizophrenia", "alzheimer", "parkinson",
    "hepatitis", "covid", "malaria", "dengue", "hypertension", "arthritis",
]
_MEDICAL_RE = re.compile(r"\b(?:" + "|".join(MEDICAL_TERMS) + r")\b", re.IGNORECASE)

# PERSON has no reliable regex (full NER only where Presidio analyzer loads), so
# we only tag Title-Case names with a person indicator nearby (high precision).
_PERSON_RE = re.compile(
    r"(?:\b[Mm]r\.?|\b[Mm]rs\.?|\b[Mm]s\.?|\b[Dd]r\.?"
    r"|(?i:reported by|contact|manager|employee|colleague|supervisor|\bhr\b|candidate))"
    r"\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b"
)

_COMPILED = [(entity, re.compile(pattern)) for entity, pattern in HR_PATTERNS]


def _phone_valid(candidate: str) -> bool:
    digits = re.sub(r"\D", "", candidate)
    if not 8 <= len(digits) <= 15:
        return False
    try:
        import phonenumbers

        num = phonenumbers.parse(candidate if candidate.startswith("+") else f"+{digits}",
                                 None if candidate.startswith("+") else "IN")
        return phonenumbers.is_possible_number(num)
    except Exception:
        return len(digits) >= 10


def find_spans(text: str) -> list[dict]:
    """Detect PII spans. Returns [{entity, start, end, score}]."""
    spans: list[dict] = []
    for entity, rx in _COMPILED:
        for m in rx.finditer(text or ""):
            if entity == "PHONE_NUMBER" and not _phone_valid(m.group()):
                continue
            spans.append({"entity": entity, "start": m.start(), "end": m.end(), "score": 0.9})
    for m in _MEDICAL_RE.finditer(text or ""):
        spans.append({"entity": "MEDICAL_CONDITION", "start": m.start(), "end": m.end(), "score": 0.8})
    for m in _PERSON_RE.finditer(text or ""):
        spans.append({"entity": "PERSON", "start": m.start(1), "end": m.end(1), "score": 0.6})

    # Drop spans fully contained in a longer span (e.g. DOB inside longer match).
    spans.sort(key=lambda s: (s["start"], -(s["end"] - s["start"])))
    kept: list[dict] = []
    for s in spans:
        if not any(k["start"] <= s["start"] and s["end"] <= k["end"] and k is not s for k in kept):
            kept.append(s)
    return kept


def _operators(spans: list[dict]) -> dict:
    from presidio_anonymizer.entities import OperatorConfig

    return {s["entity"]: OperatorConfig("replace", {"new_value": f"<{s['entity']}>"}) for s in spans}


def mask_text(text: str) -> tuple[str, list[dict]]:
    """Mask PII with <ENTITY> tokens. Returns (masked_text, findings)."""
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import RecognizerResult

    spans = find_spans(text or "")
    if not spans:
        return text, []
    results = [RecognizerResult(s["entity"], s["start"], s["end"], s["score"]) for s in spans]
    masked = AnonymizerEngine().anonymize(text, results, _operators(spans)).text
    return masked, spans
