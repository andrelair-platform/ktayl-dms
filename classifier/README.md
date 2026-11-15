# dms-classifier

> The DMS "document brain" (ktayl-dms #24, Phase 2) — a NATS JetStream worker that matches a scanned
> insurance document to its **claim# / policy# / client** and files it in Paperless, with a
> **human-in-the-loop** gate on anything uncertain. Governed AI: **PII is masked (Presidio) before the
> LLM**, every classification is **Langfuse-traced**, and a candidate is **validated against the system
> of record** before it's accepted. Contract: [`docs/specs/spec-dms-classifier`](../docs/specs/spec-dms-classifier/SPEC.md).

## Flow
```
NATS dms.doc.consumed ─▶ GET raw doc (Paperless) ─▶ indra OCR ─▶ Presidio mask [SEC-01]
   ─▶ LiteLLM extract (Langfuse) ─▶ validate vs claims/policy lookup [FR-02]
   ─▶ confident+validated → PATCH custom field + `filed` tag   | else → `needs-review` tag (HITL)
```
Idempotent (FR-05): a document already tagged `filed`/`needs-review` is skipped — re-delivery is safe.

## Why these controls
- **SEC-01** — no unmasked PII reaches the LLM; the masker **fails closed** if Presidio is down.
- **FR-02 / AI-01** — the model *suggests*, the lookup *verifies*, a human *confirms* the doubtful; a
  number that validates but belongs to a **different client** (confused-deputy) → HITL, never auto-filed.
- **SEC-04** — the worker only ever **writes to Paperless**; it only **reads** claims/policy to validate.

## Config (env — 12-factor; see `app/config.py`)
NATS · Paperless (admin creds → token) · indra OCR · Presidio · LiteLLM + model · Langfuse (dedicated
project, label-routed prompt) · claims/policy lookup URLs (+ optional M2M bearer) · confidence threshold.

## Local dev
```bash
make install   # pip install -e ".[test]"
make lint      # ruff + mypy
make test      # L1 unit (the decision gates, the parser, the PII fail-closed)
make run
```

## Deployment
CI (`.github/workflows/ci-classifier.yml`) builds the image → Harbor (dev) + ghcr (prod, cosign + SBOM).
Deploy wiring (wrapper chart, KEDA scale-to-zero on the NATS stream, two-sided NetworkPolicy, the
LLMOps Langfuse project + ESO secrets) lives in `minicloud-gitops` (`services/dms-classifier/`).
