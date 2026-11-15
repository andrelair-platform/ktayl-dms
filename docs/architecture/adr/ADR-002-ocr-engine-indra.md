# ADR-002 — OCR engine = **indra** (self-hosted), superseding Tesseract for DMS scan/image OCR (ktayl-dms #24)

**Status:** Accepted (owner-approved, 2026-11-15) · **Owner:** SA/TL + SEC · **Board:** #24 (Documents & DMS).
**Supersedes:** the OCR element of **ADR-001 Decision 2** ("OCR = Tesseract, built into Paperless"). Applies the
IS **software-evaluation chain** (`software-evaluation.md`); the evaluation record lives **here** (not Retrieva).

## Context
ADR-001 adopted Paperless-ngx with its **built-in Tesseract/OCRmyPDF** OCR — a correct Phase-1 default (zero extra
footprint, good on clean printed text). But the DMS's value is **Phase 2: matching a scanned document to its claim#/
policy#/client** (ADR-001 Decision 3), and **that match accuracy is bounded by OCR quality**. Real insurance scans are
exactly Tesseract's weak spots: **handwritten** FNOL/claim forms, **loss-adjuster/expert reports with tables**, faxed/
poor-quality scans, mixed French+English. A wrong or empty OCR read → a wrong business-key extraction → a mis-filed
sinistre document. So the OCR engine is a **design decision with a business-accuracy consequence**, not a default to
inherit. This ADR re-opens only the OCR choice (everything else in ADR-001 stands).

## Decision — adopt **indra** (`datalab-to/indra`) as the DMS scan/image OCR engine
A self-hosted, **CPU-only** OCR engine (ONNX Runtime — no GPU, no PyTorch; ~76 MB model), wrapped in a small FastAPI
service in ns `ktayl-dms` (`POST /ocr` → text + layout boxes). It replaces **Tesseract's role** for scans/images.

**Placement (two uses, one engine):**
- **Primary — the Phase-2 classifier's OCR.** The AI-filing worker OCRs the raw document with indra for clean text
  before extraction. This is where OCR quality matters most (the business-key match) and is **fully additive** — no
  change to Paperless.
- **Optional, need-gated — Paperless *search*.** *Only if* Tesseract-quality search proves insufficient for users,
  a Paperless **pre-consume script** routes scans through the indra service and `PAPERLESS_OCR_MODE=skip` keeps
  indra's text layer (no Paperless fork; reversible). Not built pre-emptively.

**Complementary, not competing, with Gotenberg+Tika** (ADR-001 office-doc OCR): Gotenberg/Tika convert *office
formats* (docx/xlsx); indra OCRs *scans/images*. Both stay.

## Software-evaluation scorecard (`software-evaluation.md`, sovereign-first)
| Criterion | indra | Verdict |
|---|---|---|
| **Need-fit** | closes the *named* gap: Phase-2 match accuracy on handwriting/tables/poor scans | ✅ strong |
| **Self-hostable / sovereignty** | runs **in-cluster, CPU-only**; **P2/P3 PII never leaves** (an external OCR API = hard no) | ✅ the decider |
| **GPU / footprint** | **no GPU** (fits this GPU-less, memory-tight cluster); ~76 MB model (vs Docling 4.4 GB); ~15× Tesseract throughput | ✅ |
| **Accuracy** | **46.7 vs Tesseract 19.3** (OmniParseBench text); handwriting + tables + 80+ languages | ✅ decisive uplift |
| **FOSS / licence** | **code Apache-2.0**; **model weights OpenRAIL-M** (use-restricted: free for research/personal/**<$20M revenue**) | ⚠️ see licence note |
| **SSO-able** | N/A — internal service, no user surface (reached only by the classifier / pre-consume, netpol-gated) | — |
| **Golden-path fit** (Vault/ESO · GitOps · netpol) | deploys as a standard GAP wrapper chart; no secrets; same-ns-ingress netpol | ✅ |
| **Observability** | FastAPI `/metrics` (Prometheus) + request logs → Loki | ✅ |
| **DORA third-party-ICT / data class** | a **self-hosted** component (not a managed ICT third party); documents are **P2/P3** → the in-house decider | ✅ |
| **Exit / portability** | **one-command reversible** — remove the service + the classifier falls back to Paperless's Tesseract text; Paperless's own OCR is untouched | ✅ |
| **TCO** | one small CPU pod; model baked into the image | ✅ |

**Decision:** indra **wins** for the scan/image OCR role — the accuracy uplift is decisive for Phase-2 matching, and
it clears the two hard constraints (no-GPU, PII-stays-in-cluster) that rule out GPU/SaaS OCR.

## Licence note (recorded honestly — the one caveat)
- **Code:** Apache-2.0 (permissive).
- **Model weights:** **modified OpenRAIL-M** — *free for research, personal use, and organisations under $20M
  funding/revenue*; a commercial licence is required above that. **ktayl is a synthetic/portfolio lab with zero
  revenue → compliant.** A real commercial insurer deploying this would need the commercial licence — stated so an
  auditor/interviewer sees intent, not a hidden gap. This is a **use-restricted licence, not pure OSS** (the
  `software-evaluation.md` FOSS-posture criterion).
- **Re-evaluation triggers** (`software-evaluation.md`): a licence change · the project becomes unmaintained/EOL · a
  real commercial-revenue claim on ktayl → re-run the choice. **Fallback = Tesseract** (already present in Paperless;
  the switch is removing the indra service — reversible, no data migration).

## Build constraint (carry into the service build)
The ~76 MB model auto-downloads from HuggingFace on first `indra_ocr.load()`. The cluster is **default-deny-egress**
→ **bake the model into the image at build time** (`INDRA_OCR_MODEL_DIR` populated during `docker build`); the
runtime pod needs **no** HF/internet egress.

## Consequences
- **Positive:** materially better Phase-2 match accuracy (the DMS's actual value), still sovereign + CPU-only + tiny;
  one engine serves both the classifier and (optionally) Paperless search; fully reversible to Tesseract.
- **Negative / accepted:** one extra small pod (vs ADR-001's "zero OCR sidecar" ideal — judged worth it for the
  accuracy); a **use-restricted model licence** (compliant for ktayl, flagged for a real deploy); a newer/smaller
  project than Tesseract (maturity risk → the reversibility above is the mitigation).
- **Next:** build the indra OCR service (bake the model) → wire it into the Phase-2 classifier.

Related: `ADR-001` (DMS role + adopt-vs-build — this supersedes its OCR element), `software-evaluation.md`,
`llmops.md`/`ADR-005` (the governed-AI matching that consumes this OCR), `architecture-strategy.md`, `bmad-compliance.md`
(data-class + AI-Act), `scheduling.md`.
