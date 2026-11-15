"""L1 — the model-output parser is tolerant (clean JSON, prose-wrapped, garbage → unknown/HITL)."""

from app.extract import Candidate, _parse


def test_parse_clean_json() -> None:
    c = _parse('{"kind":"claim","number":"SIN-1","client":"ACME","confidence":0.9}')
    assert c.kind == "claim" and c.number == "SIN-1" and c.client == "ACME" and c.confidence == 0.9


def test_parse_prose_wrapped_json() -> None:
    c = _parse('Sure:\n{"kind":"policy","number":"POL-7","client":null,"confidence":0.8}\nDone.')
    assert c.kind == "policy" and c.number == "POL-7" and c.client is None


def test_parse_garbage_is_unknown_zero_confidence() -> None:
    c = _parse("I cannot tell from this text.")
    assert c.kind == "unknown" and c.number is None and c.confidence == 0.0


def test_parse_clamps_confidence() -> None:
    # pydantic enforces 0..1 → an out-of-range value fails validation → unknown fallback
    c = _parse('{"kind":"claim","number":"X","confidence":5}')
    assert isinstance(c, Candidate) and c.kind == "unknown"
