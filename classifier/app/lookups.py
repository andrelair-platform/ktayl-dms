"""FR-02: validate a candidate against the system of record. The worker only READS (SEC-04).

- claim#  → GET {claims_lookup}/{number}  (200 ⇒ exists; returns claimNumber/policyNumber/status/…)
- policy# → GET {policy_lookup}/{number}  (200 ⇒ exists)

A non-200 ⇒ not found ⇒ route to HITL. Where the record exposes a client/holder, it's returned so the
caller can run the confused-deputy check (a number that validates but belongs to a DIFFERENT client).
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel

from app.config import settings
from app.extract import Candidate


class Validation(BaseModel):
    exists: bool = False
    record_client: str | None = None


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.lookup_bearer}"} if settings.lookup_bearer else {}


def _client_of(record: dict) -> str | None:
    for key in ("client", "clientName", "holder", "holderName", "policyHolder", "insured"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


async def validate(cand: Candidate) -> Validation:
    if cand.kind == "unknown" or not cand.number:
        return Validation(exists=False)
    base = settings.claims_lookup_url if cand.kind == "claim" else settings.policy_lookup_url
    url = f"{base.rstrip('/')}/{cand.number}"
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        try:
            resp = await client.get(url, headers=_headers())
        except httpx.HTTPError:
            return Validation(exists=False)
    if resp.status_code != 200:
        return Validation(exists=False)
    record = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    return Validation(exists=True, record_client=_client_of(record) if isinstance(record, dict) else None)
