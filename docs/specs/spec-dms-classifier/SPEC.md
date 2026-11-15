# SPEC — DMS document classifier (the "document brain", Phase 2)

**Epic:** ktayl-dms #24 Phase 2 — AI document↔record matching · **Status:** Approved for build (owner-approved
2026-11-15) · **Owner:** SA/TL + SEC · **Delivery path:** B (new AI capability on an existing product) **+ the
governance gate** (crosses the AI + P2/P3-PII boundary). Derived from **ADR-001** (DMS role + the matching model)
and **ADR-002** (indra OCR). This is the compact implementation contract the build works against.

## 1. Context & scope
When a scanned/photographed insurance document lands in Paperless (a claim invoice, a policy schedule, a KYC
proof), it is just a filed image until it's linked to the **business record** it belongs to. This epic builds the
**classifier**: an event-driven worker that reads the document, infers the **claim# / policy# / client** it
concerns, **validates** that against the real systems of record, and files it as Paperless **custom fields** —
with a **human-in-the-loop** gate on anything uncertain, so a sinistre document is never silently mis-filed.

**In scope:** the classifier service + the Paperless custom-field schema + the NATS trigger + the post-consume
hook. **Out of scope (explicit):** office-doc OCR (Phase 3), e-sign (Phase 3), per-domain doc *generation* (lives
in each `ktayl-core` domain module — ADR-001), and any *write* to a claim/policy system (the classifier only
*reads* to validate and only *writes* to Paperless).

## 2. Requirements (stable IDs — traceability per `documentation-standard.md`)
| ID | Requirement (observable) |
|---|---|
| **FR-01** | On a `dms.doc.consumed` event, the worker OCRs the document (indra) and extracts candidate claim#/policy#/client. |
| **FR-02** | A candidate is **validated** against the system of record (claims lookup / policy lookup) before it is accepted. |
| **FR-03** | On a **confident + validated** match, the worker sets the matching Paperless custom field(s) + a `filed` tag. |
| **FR-04** | On **low-confidence / ambiguous / not-found**, the worker sets a `needs-review` tag and does **not** auto-file (HITL). |
| **FR-05** | Processing is **idempotent** — re-delivery of the same event never double-files or duplicates side-effects. |
| **NFR-01** | The worker scales to **zero** when idle and wakes on queue depth (KEDA/NATS); a backlog drains without manual action. |
| **NFR-02** | Every classification emits a **Langfuse trace** (Trace→Span→Generation + token usage + cost), tagged with the doc id. |
| **NFR-03** | Mean end-to-end classify latency (event→filed) **< 30 s** p95 at 1 doc/s on dev (SLO; revisit for prod). |
| **SEC-01** | **No unmasked PII reaches any LLM** — Presidio masks the OCR text before the extract call (deny-by-default). |
| **SEC-02** | The worker's egress is **default-deny + explicit allow** (indra, LiteLLM, Langfuse, the lookups, NATS, DNS) — nothing else. |
| **SEC-03** | The worker authenticates to the lookups with a **scoped M2M identity** (Authentik client-credentials), not a human token. |
| **SEC-04** | The worker holds **no write** capability on any claim/policy system; it can only PATCH Paperless custom fields. |
| **AI-01** | A low-confidence or cross-record-ambiguous extraction **must** route to HITL (FR-04), never auto-file (EU AI-Act control). |

## 3. The flow (the implementation contract)
```
Paperless (post-consume script) ── nats pub dms.doc.consumed {document_id} ──▶ JetStream stream DMS_DOC (durable)
                                                                                      │
                               KEDA (NATS JetStream trigger, minReplicas 0) ──wakes──▶ dms-classifier 0→1
                                                                                      ▼
  1. GET  {paperless}/api/documents/{id}/download/            → the raw file         (Paperless API token, read)
  2. POST {indra}/ocr  (the raw file)                          → clean text + boxes    [SEC: in-cluster only]
  3. Presidio mask the text                                    → masked text           [SEC-01: before any LLM]
  4. LiteLLM chat.completions (masked text, extraction prompt) → candidate {claim#|policy#|client, confidence}
                                                                 [NFR-02: Langfuse Trace→Span→Generation]
  5. validate the candidate against the system of record:
        claim#  → GET {ktayl-claims}/…/{claimNumber}           (200 ⇒ exists)          [SEC-03 M2M]
        policy# → GET {ktayl-core}/api/billing/policies/{n}    (200 ⇒ exists)
  6a. confident (≥ τ) AND validated  → PATCH {paperless}/api/documents/{id}/ custom_fields + add `filed` tag
  6b. else                           → add `needs-review` tag; do NOT set the business field   [FR-04 / AI-01]
  7. ack the JetStream message (redelivery on failure → FR-05 idempotency via the custom-field check)
```
**Confidence threshold `τ`** is a config value (start conservative; tune from the HITL review rate). Idempotency
(FR-05): before filing, the worker checks the document doesn't already carry the business field → re-delivery is a
no-op.

## 4. Interfaces
| Collaborator | Interface | Direction | Auth |
|---|---|---|---|
| NATS JetStream | stream `DMS_DOC`, subject `dms.doc.consumed`, durable consumer | consume | in-mesh |
| Paperless | `GET /api/documents/{id}/download/`, `PATCH /api/documents/{id}/`, custom-fields API | read + write(Paperless-only) | API token (ESO→Vault) |
| indra OCR | `POST http://dms-indra-ocr:8000/ocr` | call | none (in-ns netpol) |
| LiteLLM | `POST http://litellm.ai.svc.cluster.local:4000/v1/chat/completions` | call | team key (ESO→Vault) |
| Langfuse | SDK (dedicated project) | emit | keys (ESO→Vault) |
| ktayl-claims | claim lookup (route confirmed at build) | read | Authentik client-credentials (M2M) |
| ktayl-core | `GET /api/billing/policies/{policyNumber}` | read | Authentik client-credentials (M2M) |

The LLM contract (the extract call) and each lookup is covered by an **L3 contract test** — a mocked boundary is
not a tested boundary (`testing.md`).

## 5. EU AI-Act classification (the gate)
**Risk tier: LIMITED-RISK — HITL-assisted document classification.** The system *suggests* a filing and a human
confirms anything uncertain (FR-04/AI-01); it makes **no automated decision with legal/material effect on a
person** (it does not price, underwrite, pay, deny, or score an individual). It is **not** Annex-III high-risk
(ktayl is B2B/IARD; the classifier only routes a document to a record). Controls, proportionate to the tier:
transparency (every suggestion is traceable in Langfuse), **human oversight** (the HITL gate is a hard control,
not advisory), **data governance** (PII masked before the model), and **accuracy monitoring** (the HITL review
rate is the quality signal). Classified via the `ai-act-gate`; obligation recorded in `ktayl-compliance`
(obligations register, see §8).

## 6. Threat model (STRIDE-lite — the PII→LLM + cross-system boundary)
Full model: **`docs/security/dms-classifier-threat-model.md`**. The trust boundaries + top controls:
| Boundary | Threat | Control |
|---|---|---|
| OCR text → LLM | **Information disclosure** — PII leaks to the model/provider | SEC-01 Presidio mask *before* the call; on-cluster free model first; never a US model with unmasked PII |
| worker → lookups | **Elevation** — the worker over-reaches into claim/policy systems | SEC-03 scoped read-only M2M identity; SEC-04 no write; SEC-02 explicit-allow egress |
| event → worker | **Tampering/Spoofing** — a forged/replayed event mis-files a doc | JetStream in-mesh; FR-05 idempotency; validation (FR-02) gates every file |
| worker → Paperless | **Repudiation** — an unauditable auto-file | NFR-02 Langfuse trace per classification; the `filed`/`needs-review` tag is the audit marker |
| the model | **Hallucinated match** | FR-02 validation (a claim#/policy# that doesn't exist is rejected) + AI-01 HITL on low confidence |

## 7. NFRs, cost & operational
- **SLO** NFR-03 (latency) + the KEDA scale-to-zero (NFR-01). **Cost:** on-cluster **free** model first (extraction
  is a short structured task); an EU-paid tier only if accuracy needs it — LiteLLM team budget caps it. Langfuse
  tracks per-call tokens/cost (`llmops.md`). **Footprint:** idle = 0 pods (scaled to zero); the indra service is
  the only always-on addition (already deployed).
- **Deploy:** GAP wrapper chart `services/dms-classifier/helm` + KEDA ScaledObject + two-sided netpol
  (`gitops.md`); Kargo when a prod env exists. **LLMOps:** the five mandatory pieces (`llmops.md`) — dedicated
  Langfuse project, ESO keys, two-sided netpol, the trace tree, prompt management.

## 8. Definition of Done (the build is not done until all hold)
- [ ] FR-01…05, SEC-01…04, AI-01 implemented + the confidence/HITL gate wired.
- [ ] Tests: L0 lint/type · L1 unit (extraction parse, confidence gate, idempotency) · **L2** integration (real
      NATS + a stub Paperless) · **L3 contract** (the LLM extract shape + each lookup OpenAPI) · L4 smoke.
- [ ] LLMOps: the 5 pieces live (dedicated Langfuse project, traces visible, prompt managed).
- [ ] **Live QA gate (L5)** on dev — adversarial: garbage OCR, wrong/missing number, a number that validates but
      belongs to a *different* client, redelivery/idempotency, HITL routing. Blockers gate prod promotion.
- [ ] Docs DoD: the DMS as-built page updated (the classifier section) + build-checked.
- [ ] Governance gate: this SPEC + the threat model + the AI-Act classification reviewed/approved; the
      obligation row added to `ktayl-compliance` (frameworks: EU AI-Act limited-risk, GDPR Art. 5/32 for the
      PII masking + the document data).

## 9. Governance sign-off (the record)
- **Architecture review:** approved — the module boundaries (own service, Python/ML stack, strong data isolation)
  justify a separate service over a `ktayl-core` module (`architecture-strategy.md` extraction test).
- **Security review:** approved on the controls above — the PII→LLM boundary (SEC-01), the scoped M2M read-only
  identity (SEC-03/04), and the explicit-allow egress (SEC-02) are the conditions of build.
- This is cert evidence for **BC02 (concevoir & développer)** / **BC03 (déployer & sécuriser)**.

Related: `ADR-001`, `ADR-002`, `llmops.md`, `qa-gate.md`, `testing.md`, `bmad-compliance.md` (AI-Act + the gate),
`architecture-strategy.md`, `software-evaluation.md`, `docs/security/dms-classifier-threat-model.md`.
