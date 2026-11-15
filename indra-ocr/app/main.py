"""indra OCR service — a small FastAPI wrapper around the indra CPU OCR engine.

POST /ocr   multipart file upload → normalised OCR JSON (text + per-page lines/boxes)
GET  /health  liveness/readiness
GET  /metrics Prometheus

Reached only in-cluster by the Phase-2 DMS classifier (and, optionally later, a Paperless
pre-consume script) — netpol-gated, no SSO surface (ADR-002). No egress, no secrets.
"""

from __future__ import annotations

import os
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from app import ocr

MAX_UPLOAD_BYTES = int(os.getenv("INDRA_MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))  # 50 MiB

_REQUESTS = Counter("indra_ocr_requests_total", "OCR requests", ["outcome"])
_LATENCY = Histogram("indra_ocr_seconds", "OCR wall-clock seconds")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Load the (image-baked) model once at startup so the first real request isn't slow.
    ocr.warm()
    yield


app = FastAPI(title="indra-ocr-service", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/ocr")
async def run_ocr(file: Annotated[UploadFile, File()]) -> JSONResponse:
    data = await file.read()
    if not data:
        _REQUESTS.labels("bad_request").inc()
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        _REQUESTS.labels("too_large").inc()
        raise HTTPException(status_code=413, detail="file too large")

    suffix = os.path.splitext(file.filename or "")[1] or ".bin"
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        start = time.perf_counter()
        result = ocr.run_ocr(tmp_path)
        _LATENCY.observe(time.perf_counter() - start)
        _REQUESTS.labels("ok").inc()
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as exc:  # surface a clean 500, never leak a stack trace to the caller
        _REQUESTS.labels("error").inc()
        raise HTTPException(status_code=500, detail=f"ocr failed: {type(exc).__name__}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
