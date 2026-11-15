# indra-ocr

> Self-hosted, **CPU-only** OCR microservice (the [indra](https://github.com/datalab-to/indra) engine)
> for the ktayl DMS (#24). Turns a scanned/photographed insurance document into clean text + per-line
> bounding boxes — the quality that the Phase-2 document-classifier's claim#/policy# matching depends on.
> Chosen over Tesseract in **[ADR-002](../docs/architecture/adr/ADR-002-ocr-engine-indra.md)**.

## Why it exists

Paperless-ngx ships Tesseract, which is weak on handwriting, tables, and poor scans — exactly the
insurance document reality (FNOL forms, loss-adjuster reports, faxes). indra scores far higher
(46.7 vs 19.3 on OmniParseBench) and runs **without a GPU**, so the DMS gets a real accuracy uplift
while staying sovereign (the P2/P3 PII never leaves the cluster — there is no external OCR API).

## Endpoints

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/ocr` | multipart `file` (PDF/image) | `{ "text": "...", "pages": [{ "page", "markdown", "text", "lines": [{text, bbox, confidence}] }] }` |
| `GET` | `/health` | — | `{"status":"ok"}` |
| `GET` | `/metrics` | — | Prometheus |

It is reached **only in-cluster** by the Phase-2 classifier (netpol-gated) — no SSO surface, no egress,
no secrets.

## The model is baked into the image

The ~76 MB indra model is downloaded **at image-build time** (`Dockerfile`) because the runtime cluster
is default-deny-egress — there is **no** HuggingFace fetch at run time. `INDRA_OCR_MODEL_DIR` points at
the baked directory.

## Local dev

```bash
make install       # pip install -e ".[test]"
make lint          # ruff + mypy
make test          # L1 unit (indra mocked, fast)
make test-smoke    # runs the REAL indra model (downloads it; slow)
make run           # uvicorn on :8000
```

## Deployment

Image built by CI (`.github/workflows/ci-indra-ocr.yml`) → Harbor (dev) + ghcr (prod, cosign + SBOM).
Deploy wiring (wrapper chart, ArgoCD app, NetworkPolicy) lives in `minicloud-gitops`
(`services/dms-indra-ocr/helm`) per the repo's deploy-vs-code split.

## Licence

Service code: MIT (this repo). The indra **model weights** are OpenRAIL-M (free for research/personal/
<$20M-revenue) — compliant for ktayl (synthetic lab); see ADR-002 for the full licence posture.
