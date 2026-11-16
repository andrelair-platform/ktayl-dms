"""Paperless REST client: read a document + its OCR-less raw file, and write the business custom field
+ a `filed`/`needs-review` tag. The ONLY system the worker writes to (SEC-04). Idempotent (FR-05):
a document already carrying a `filed`/`needs-review` tag is treated as processed → re-delivery is a no-op.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import settings

FIELD_NAMES = ("policy_number", "claim_number", "client")
TAG_FILED = "filed"
TAG_NEEDS_REVIEW = "needs-review"


class Paperless:
    def __init__(self) -> None:
        self._token: str | None = None
        self._field_ids: dict[str, int] = {}
        self._tag_ids: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def _client(self) -> httpx.AsyncClient:
        headers = {"Authorization": f"Token {self._token}"} if self._token else {}
        return httpx.AsyncClient(
            base_url=settings.paperless_url, headers=headers, timeout=settings.http_timeout_seconds
        )

    async def ensure_ready(self) -> None:
        """Mint a token + resolve custom-field/tag name→id maps (once)."""
        async with self._lock:
            if self._token and self._field_ids and self._tag_ids:
                return
            async with httpx.AsyncClient(base_url=settings.paperless_url, timeout=settings.http_timeout_seconds) as c:
                r = await c.post(
                    "/api/token/",
                    json={
                        "username": settings.paperless_admin_user,
                        "password": settings.paperless_admin_password,
                    },
                )
                r.raise_for_status()
                self._token = r.json()["token"]
            async with self._client() as c:
                fields = (await c.get("/api/custom_fields/?page_size=200")).json().get("results", [])
                self._field_ids = {f["name"]: f["id"] for f in fields}
                tags = (await c.get("/api/tags/?page_size=200")).json().get("results", [])
                self._tag_ids = {t["name"]: t["id"] for t in tags}

    async def get_document(self, doc_id: int) -> dict[str, Any]:
        async with self._client() as c:
            r = await c.get(f"/api/documents/{doc_id}/")
            r.raise_for_status()
            return r.json()

    async def download(self, doc_id: int) -> bytes:
        async with self._client() as c:
            r = await c.get(f"/api/documents/{doc_id}/download/")
            r.raise_for_status()
            return r.content

    def already_processed(self, doc: dict[str, Any]) -> bool:
        tag_ids = set(doc.get("tags", []))
        return any(self._tag_ids.get(t) in tag_ids for t in (TAG_FILED, TAG_NEEDS_REVIEW) if t in self._tag_ids)

    async def _patch(self, doc_id: int, body: dict[str, Any]) -> None:
        async with self._client() as c:
            r = await c.patch(f"/api/documents/{doc_id}/", json=body)
            r.raise_for_status()

    async def _add_tag(self, doc: dict[str, Any], tag_name: str) -> None:
        tag_id = self._tag_ids.get(tag_name)
        if tag_id is None:
            return
        tags = sorted(set(doc.get("tags", [])) | {tag_id})
        await self._patch(doc["id"], {"tags": tags})

    async def mark_filed(self, doc: dict[str, Any], field_name: str, value: str) -> None:
        """Set the business custom field (merged with existing) + add the `filed` tag."""
        field_id = self._field_ids.get(field_name)
        existing = [cf for cf in doc.get("custom_fields", []) if cf.get("field") != field_id]
        if field_id is not None:
            existing.append({"field": field_id, "value": value})
            await self._patch(doc["id"], {"custom_fields": existing})
        await self._add_tag(await self.get_document(doc["id"]), TAG_FILED)

    async def mark_needs_review(self, doc: dict[str, Any]) -> None:
        await self._add_tag(doc, TAG_NEEDS_REVIEW)

    # --- retention/archival helpers (additive; used by the archive-only retention job) ---

    async def list_documents(self) -> list[dict[str, Any]]:
        """All documents (paginated). Read-only; used by the retention CronJob to pick un-archived docs."""
        out: list[dict[str, Any]] = []
        async with self._client() as c:
            url: str | None = "/api/documents/?page_size=100&ordering=id"
            while url:
                r = await c.get(url)
                r.raise_for_status()
                page = r.json()
                out.extend(page.get("results", []))
                nxt = page.get("next")
                # `next` is an absolute URL; httpx AsyncClient honours it relative to base_url
                url = nxt.replace(settings.paperless_url, "") if nxt else None
        return out

    async def ensure_tag(self, name: str) -> int:
        """Get-or-create a tag by name; returns its id and refreshes the local map (idempotent)."""
        async with self._client() as c:
            existing = (await c.get(f"/api/tags/?name__iexact={name}")).json().get("results", [])
            if existing:
                tid = existing[0]["id"]
            else:
                r = await c.post("/api/tags/", json={"name": name})
                r.raise_for_status()
                tid = r.json()["id"]
        self._tag_ids[name] = tid
        return tid

    async def add_named_tag(self, doc: dict[str, Any], tag_name: str) -> None:
        """Public: ensure the tag exists then attach it (merged with existing tags)."""
        await self.ensure_tag(tag_name)
        await self._add_tag(doc, tag_name)

    def field_id_to_name(self) -> dict[int, str]:
        return {v: k for k, v in self._field_ids.items()}

    def tag_id_to_name(self) -> dict[int, str]:
        return {v: k for k, v in self._tag_ids.items()}
