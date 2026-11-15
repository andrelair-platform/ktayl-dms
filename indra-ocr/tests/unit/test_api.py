"""L1 unit — the FastAPI surface (indra mocked, no real model)."""

import app.ocr as ocr_mod
from app.main import app
from fastapi.testclient import TestClient


def test_health(monkeypatch) -> None:
    monkeypatch.setattr(ocr_mod, "warm", lambda: None)
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_ocr_rejects_empty_file(monkeypatch) -> None:
    monkeypatch.setattr(ocr_mod, "warm", lambda: None)
    with TestClient(app) as client:
        resp = client.post("/ocr", files={"file": ("scan.png", b"", "image/png")})
        assert resp.status_code == 400


def test_ocr_returns_normalised_result(monkeypatch) -> None:
    monkeypatch.setattr(ocr_mod, "warm", lambda: None)
    monkeypatch.setattr(
        ocr_mod,
        "run_ocr",
        lambda _path: {"text": "SINISTRE 2026-0042", "pages": [{"page": 0, "lines": []}]},
    )
    with TestClient(app) as client:
        resp = client.post("/ocr", files={"file": ("scan.png", b"\x89PNGfake", "image/png")})
        assert resp.status_code == 200
        body = resp.json()
        assert body["text"] == "SINISTRE 2026-0042"
        assert body["pages"][0]["page"] == 0


def test_metrics_exposed(monkeypatch) -> None:
    monkeypatch.setattr(ocr_mod, "warm", lambda: None)
    with TestClient(app) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert b"indra_ocr_requests_total" in resp.content
