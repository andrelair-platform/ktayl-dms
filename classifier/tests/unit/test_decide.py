"""L1 — the decision gates (FR-02/04, AI-01): confident+validated files; everything uncertain → HITL."""

from app import classify as C
from app import lookups
from app.extract import Candidate


class FakePaperless:
    def __init__(self) -> None:
        self.filed: tuple[str, str] | None = None
        self.review = False

    async def mark_filed(self, doc, field, value) -> None:
        self.filed = (field, value)

    async def mark_needs_review(self, doc) -> None:
        self.review = True


async def test_low_confidence_routes_to_hitl() -> None:
    pl = FakePaperless()
    cand = Candidate(kind="claim", number="SIN-1", confidence=0.3)
    out = await C._decide({"id": 1}, cand, pl, None)
    assert out == "needs-review"
    assert pl.review and pl.filed is None


async def test_unknown_routes_to_hitl() -> None:
    pl = FakePaperless()
    cand = Candidate(kind="unknown", number=None, confidence=0.99)
    out = await C._decide({"id": 1}, cand, pl, None)
    assert out == "needs-review" and pl.filed is None


async def test_not_found_routes_to_hitl(monkeypatch) -> None:
    async def fake_validate(_c):
        return lookups.Validation(exists=False)

    monkeypatch.setattr(C.lookups, "validate", fake_validate)
    pl = FakePaperless()
    cand = Candidate(kind="policy", number="POL-404", confidence=0.95)
    out = await C._decide({"id": 1}, cand, pl, None)
    assert out == "needs-review" and pl.filed is None


async def test_client_mismatch_is_confused_deputy_hitl(monkeypatch) -> None:
    async def fake_validate(_c):
        return lookups.Validation(exists=True, record_client="ACME SA")

    monkeypatch.setattr(C.lookups, "validate", fake_validate)
    pl = FakePaperless()
    cand = Candidate(kind="policy", number="POL-1", client="Other Corp", confidence=0.95)
    out = await C._decide({"id": 1}, cand, pl, None)
    assert out == "needs-review" and pl.filed is None


async def test_confident_validated_files(monkeypatch) -> None:
    async def fake_validate(_c):
        return lookups.Validation(exists=True, record_client="ACME SA")

    monkeypatch.setattr(C.lookups, "validate", fake_validate)
    pl = FakePaperless()
    cand = Candidate(kind="claim", number="SIN-42", client="ACME SA", confidence=0.95)
    out = await C._decide({"id": 1}, cand, pl, None)
    assert out == "filed"
    assert pl.filed == ("claim_number", "SIN-42")
