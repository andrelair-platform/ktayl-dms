"""SEC-01: mask PII in the OCR text BEFORE it ever reaches the LLM (deny-by-default).

Uses the in-cluster Presidio (analyzer → anonymizer, the same services LiteLLM uses). Business
identifiers (policy#/claim#) are NOT PII and survive masking — names/addresses/emails/phones etc. are
replaced. If Presidio is unreachable, we FAIL CLOSED (raise) rather than send raw PII to the model.
"""

from __future__ import annotations

import httpx

from app.config import settings

# Entities Presidio should redact. Deliberately does NOT include anything that could be a policy/claim
# number — those are the signal we need the model to read.
_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
    "LOCATION",
    "US_SSN",
    "MEDICAL_LICENSE",
    "NRP",
]


async def mask(text: str, *, language: str = "en") -> str:
    """Analyze + anonymize `text`; return the masked text. Fails closed if Presidio is down."""
    if not text.strip():
        return text
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        analyze = await client.post(
            f"{settings.presidio_analyzer_url}/analyze",
            json={"text": text, "language": language, "entities": _ENTITIES},
        )
        analyze.raise_for_status()
        results = analyze.json()
        if not results:
            return text
        anonymize = await client.post(
            f"{settings.presidio_anonymizer_url}/anonymize",
            json={
                "text": text,
                "analyzer_results": results,
                "anonymizers": {"DEFAULT": {"type": "replace", "new_value": "<REDACTED>"}},
            },
        )
        anonymize.raise_for_status()
        return anonymize.json()["text"]
