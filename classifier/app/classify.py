"""The classification flow (spec-dms-classifier §3). Orchestrates OCR → PII-mask → extract → validate →
file-or-HITL. The confidence/validation/confused-deputy gates (FR-02/04, AI-01) decide file vs HITL."""

from __future__ import annotations

import contextlib
from typing import Any

from app import extract as extract_mod
from app import lookups, ocr_client, pii, tracing
from app.config import settings
from app.extract import Candidate
from app.paperless import Paperless

_FIELD_FOR = {"policy": "policy_number", "claim": "claim_number"}


def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def _finish(trace: Any, outcome: str, cand: Candidate) -> None:
    if trace is not None:
        with contextlib.suppress(Exception):
            trace.update(output={"outcome": outcome, "candidate": cand.model_dump()})


async def classify(doc_id: int, pl: Paperless) -> str:
    """Returns one of: skip · filed · needs-review."""
    await pl.ensure_ready()
    doc = await pl.get_document(doc_id)
    if pl.already_processed(doc):
        return "skip"  # FR-05 idempotency: already filed or already flagged

    raw = await pl.download(doc_id)
    text = await ocr_client.ocr(raw, filename=str(doc.get("original_file_name") or doc_id))
    masked = await pii.mask(text)  # SEC-01: no unmasked PII to the LLM

    trace = tracing.new_trace("document_classification", str(doc_id), inp={"ocr_chars": len(masked)})
    cand = await extract_mod.extract(masked, trace)
    outcome = await _decide(doc, cand, pl, trace)
    tracing.flush()
    return outcome


async def _decide(doc: dict[str, Any], cand: Candidate, pl: Paperless, trace: Any) -> str:
    # FR-04 / AI-01 — unknown, no number, or low confidence → never auto-file.
    if cand.kind == "unknown" or not cand.number or cand.confidence < settings.confidence_threshold:
        await pl.mark_needs_review(doc)
        _finish(trace, "needs-review:low-confidence", cand)
        return "needs-review"

    # FR-02 — the candidate must exist in the system of record.
    v = await lookups.validate(cand)
    if not v.exists:
        await pl.mark_needs_review(doc)
        _finish(trace, "needs-review:not-found", cand)
        return "needs-review"

    # Confused-deputy — a number that validates but belongs to a DIFFERENT client → HITL.
    if v.record_client and cand.client and _norm(v.record_client) != _norm(cand.client):
        await pl.mark_needs_review(doc)
        _finish(trace, "needs-review:client-mismatch", cand)
        return "needs-review"

    # FR-03 — confident + validated → file it.
    await pl.mark_filed(doc, _FIELD_FOR[cand.kind], cand.number)
    _finish(trace, "filed", cand)
    return "filed"
