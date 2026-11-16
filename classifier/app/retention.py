"""Archive-only document retention (DMS Phase 3, #24; policy = docs/retention-policy.md).

Gives every DMS document a durable OFFSITE copy on Cloudflare R2, organised by its legal retention class
and keep-until year, so regulated records survive a DMS/Longhorn loss (DORA Art. 11-12). It is
**archive-only**: it NEVER deletes anything — not from Paperless, not from R2. Idempotent via an `archived`
tag. DRY-RUN by default (reports what it would archive; set RETENTION_DRY_RUN=false to actually upload).

Run as an admin process in the classifier image (12-factor #12):  `python -m app.retention`
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging

from app.config import settings
from app.paperless import Paperless

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("retention")

# The retention standard (docs/retention-policy.md). Conservative default = the longest common window.
RETENTION_YEARS: dict[str, int] = {
    "policy": 10,
    "claim": 10,
    "financial": 10,
    "kyc": 5,
    "regulatory": 10,
    "correspondence": 5,
    "internal": 3,
    "marketing": 1,
    "default": 10,
}
_TAG_CLASSES = ("kyc", "regulatory", "financial", "correspondence", "internal", "marketing")


def classify(doc: dict, field_id_to_name: dict[int, str], tag_id_to_name: dict[int, str]) -> str:
    """Map a Paperless document to a retention class (pure; unit-tested).

    Precedence: an explicit business custom field (claim#/policy#) → a class-named tag → the conservative
    `default`. doc_type isn't modelled as a class source yet (a future enhancement).
    """
    for cf in doc.get("custom_fields", []):
        name = field_id_to_name.get(cf.get("field"))
        if name == "claim_number" and cf.get("value"):
            return "claim"
        if name == "policy_number" and cf.get("value"):
            return "policy"
    tag_names = {tag_id_to_name.get(t, "").lower() for t in doc.get("tags", [])}
    for cls in _TAG_CLASSES:
        if cls in tag_names:
            return cls
    return "default"


def keep_until(created_iso: str, retention_class: str) -> dt.date:
    """keep-until = the document's created date + the class window. `created` is a safe (over-retaining)
    proxy for the true trigger (contract-end / claim-closure), which the DMS doesn't model yet."""
    years = RETENTION_YEARS.get(retention_class, RETENTION_YEARS["default"])
    created = dt.date.fromisoformat(created_iso[:10])
    try:
        return created.replace(year=created.year + years)
    except ValueError:  # 29 Feb → 28 Feb
        return created.replace(year=created.year + years, day=28)


def _r2():
    """Lazily build the R2 (S3-compatible) client — only when actually uploading (dry-run skips boto3)."""
    import boto3  # imported lazily so a dry-run needs no AWS SDK at import time

    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint,
        aws_access_key_id=settings.r2_access_key,
        aws_secret_access_key=settings.r2_secret_key,
        region_name="auto",
    )


async def run() -> dict[str, int]:
    pl = Paperless()
    await pl.ensure_ready()
    f2n, t2n = pl.field_id_to_name(), pl.tag_id_to_name()
    archived_tag_id = await pl.ensure_tag(settings.archived_tag)

    docs = await pl.list_documents()
    s3 = None if settings.retention_dry_run else _r2()
    stats = {"total": len(docs), "already": 0, "archived": 0, "errors": 0}

    for doc in docs:
        if archived_tag_id in set(doc.get("tags", [])):
            stats["already"] += 1
            continue
        try:
            cls = classify(doc, f2n, t2n)
            ku = keep_until(doc.get("created") or doc.get("added") or "1970-01-01", cls)
            fname = doc.get("original_file_name") or f"{doc['id']}"
            key = f"{settings.archive_prefix}/{cls}/{ku.year}/{doc['id']}/{fname}"
            meta = {
                "id": doc["id"], "retention_class": cls, "keep_until": ku.isoformat(),
                "created": doc.get("created"), "title": doc.get("title"),
            }
            if settings.retention_dry_run:
                log.info("DRY-RUN would archive doc %s → s3://%s/%s (keep_until %s)",
                         doc["id"], settings.r2_bucket, key, ku.isoformat())
            else:
                assert s3 is not None  # non-dry-run ⇒ the R2 client was built above
                content = await pl.download(doc["id"])
                s3.put_object(Bucket=settings.r2_bucket, Key=key, Body=content)
                s3.put_object(Bucket=settings.r2_bucket, Key=key + ".meta.json",
                              Body=json.dumps(meta).encode(), ContentType="application/json")
                await pl.add_named_tag(doc, settings.archived_tag)  # idempotency marker (only after a real upload)
                log.info("archived doc %s → s3://%s/%s", doc["id"], settings.r2_bucket, key)
            stats["archived"] += 1
        except Exception:  # per-doc failure must not abort the whole run (best-effort, logged)
            log.exception("failed to archive doc %s", doc.get("id"))
            stats["errors"] += 1

    log.info("retention run complete (dry_run=%s): %s", settings.retention_dry_run, stats)
    return stats


if __name__ == "__main__":
    asyncio.run(run())
