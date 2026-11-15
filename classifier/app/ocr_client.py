"""Client for the in-cluster indra OCR service (ADR-002)."""

from __future__ import annotations

import httpx

from app.config import settings


async def ocr(raw: bytes, filename: str = "document") -> str:
    """POST the raw document to indra → return the extracted text."""
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        resp = await client.post(
            f"{settings.indra_ocr_url}/ocr",
            files={"file": (filename, raw, "application/octet-stream")},
        )
        resp.raise_for_status()
        return resp.json().get("text", "")
