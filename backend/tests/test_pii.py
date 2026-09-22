"""PII masking tests: entities, tokens, span hygiene (local, no network)."""
from backend.app.services.security.pii_masker import find_spans, mask_text


def entities(text):
    return {s["entity"] for s in find_spans(text)}


def test_email():
    masked, findings = mask_text("Contact John Smith at john@company.com for help.")
    assert "<EMAIL_ADDRESS>" in masked and "john@company.com" not in masked
    assert "<PERSON>" in masked and "John Smith" not in masked


def test_phone():
    masked, _ = mask_text("Call me at +91-9876543210 tomorrow.")
    assert "<PHONE_NUMBER>" in masked and "9876543210" not in masked


def test_ssn_and_pan():
    assert "US_SSN" in entities("SSN 123-45-6789 on file.")
    assert "IN_PAN" in entities("PAN ABCDE1234F verified.")


def test_salary():
    masked, _ = mask_text("CTC is Rs. 12,00,000 per annum.")
    assert "<SALARY>" in masked and "12,00,000" not in masked


def test_medical():
    masked, findings = mask_text("Leave reason: depression treatment.")
    assert "<MEDICAL_CONDITION>" in masked
    assert any(f["entity"] == "MEDICAL_CONDITION" for f in findings)


def test_clean_text_passthrough():
    masked, findings = mask_text("How many days of annual leave do I get?")
    assert masked.startswith("How many days") and findings == []


def test_person_heuristic_with_indicator():
    masked, _ = mask_text("Reported by John Smith yesterday.")
    assert "<PERSON>" in masked and "John Smith" not in masked


def test_person_ignored_without_indicator():
    # Policy terms like "Sexual Harassment" must NOT be masked as names.
    masked, findings = mask_text("Prevention of Sexual Harassment. Yesterday. John went home.")
    assert "<PERSON>" not in masked
    assert all(f["entity"] != "PERSON" for f in findings)


def test_overlapping_spans_deduped():
    spans = find_spans("Mail john@company.com today.")
    assert len([s for s in spans if s["entity"] == "EMAIL_ADDRESS"]) == 1
