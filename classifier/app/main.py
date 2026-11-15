"""DMS classifier worker — a NATS JetStream durable consumer of `dms.doc.consumed`, with a tiny HTTP
surface for k8s probes + Prometheus. KEDA scales it 0→N on the stream's pending count; it files each
document (or routes it to HITL) and acks. Redelivery is safe (classify is idempotent, FR-05)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import nats
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from app.classify import classify
from app.config import settings
from app.paperless import Paperless

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("dms-classifier")

_OUTCOMES = Counter("dms_classifier_outcomes_total", "Classification outcomes", ["outcome"])

_paperless = Paperless()
_stop = asyncio.Event()


async def _handle(msg: Any) -> None:
    try:
        payload = json.loads(msg.data.decode())
        raw_id = str(payload.get("document_id", "")).strip()
        doc_id = int(raw_id)  # Paperless doc ids are integers; anything else is test/garbage
    except (ValueError, json.JSONDecodeError):
        _OUTCOMES.labels("ignored").inc()
        await msg.ack()  # unparseable → drop, don't redeliver forever
        return
    try:
        outcome = await classify(doc_id, _paperless)
        _OUTCOMES.labels(outcome).inc()
        log.info("document %s → %s", doc_id, outcome)
        await msg.ack()
    except Exception as exc:  # transient (OCR/LLM/Paperless down) → redeliver later
        _OUTCOMES.labels("error").inc()
        log.warning("document %s failed, will redeliver: %r", doc_id, exc)
        await msg.nak(delay=10)


async def _consume() -> None:
    nc = await nats.connect(settings.nats_url, name="dms-classifier")
    js = nc.jetstream()
    sub = await js.pull_subscribe(settings.nats_subject, durable=settings.nats_durable, stream=settings.nats_stream)
    log.info(
        "consuming %s (stream %s, durable %s)",
        settings.nats_subject,
        settings.nats_stream,
        settings.nats_durable,
    )
    try:
        while not _stop.is_set():
            try:
                msgs = await sub.fetch(batch=1, timeout=5)
            except TimeoutError:
                continue
            except Exception as exc:
                log.warning("fetch error: %r", exc)
                await asyncio.sleep(2)
                continue
            for msg in msgs:
                await _handle(msg)
    finally:
        await nc.drain()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_consume())
    try:
        yield
    finally:
        _stop.set()
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task


app = FastAPI(title="dms-classifier", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
