# Threat model — DMS document classifier (STRIDE-lite)

**Scope:** the Phase-2 classifier (`spec-dms-classifier`) — an event-driven worker that OCRs a scanned insurance
document, extracts the claim#/policy#/client via an LLM, validates it against the systems of record, and files it
in Paperless. **Owner:** SEC + SA/TL. Feeds the **security-review gate** (`bmad-compliance.md`). The documents are
**P2/P3** (claims + KYC = sensitive PII/financial).

## Assets
- **The document content + OCR text** (P2/P3 PII: names, addresses, IDs, financial amounts, medical in claims).
- **The business keys** (claim#, policy#, client) and the link between a document and a record.
- **The credentials** the worker holds (Paperless API token, LiteLLM team key, the M2M lookup identity, Langfuse keys).

## Trust boundaries (where data crosses a control line)
1. **Paperless → worker** (raw document leaves the store).
2. **worker → indra OCR** (in-cluster, same ns).
3. **worker → LLM (LiteLLM → model)** — *the critical boundary*: PII could reach a model/provider.
4. **worker → systems of record** (claims, policy) — a read into regulated business systems.
5. **worker → Paperless (write)** — the auto-file action.
6. **event bus (NATS)** — the trigger.

## STRIDE

| # | Threat (STRIDE) | At | Mitigation (→ SPEC req) |
|---|---|---|---|
| 1 | **Spoofing** — a forged `dms.doc.consumed` event files an attacker-chosen doc | 6 | NATS is in-mesh (no external publishers; netpol SEC-02); every file is gated by a real Paperless doc fetch + validation (FR-02) — a bogus id simply yields nothing to file |
| 2 | **Tampering** — a replayed/duplicated event double-files | 6 | **Idempotency** (FR-05): the worker checks the doc doesn't already carry the business field before writing → redelivery is a no-op; JetStream ack semantics |
| 3 | **Repudiation** — an auto-file with no audit trail | 5 | Every classification emits a **Langfuse trace** (NFR-02) with the doc id + the model decision; the `filed`/`needs-review` tag is the on-document audit marker |
| 4 | **Information disclosure** — **PII leaks to the LLM/provider** | 3 | **SEC-01: Presidio masks the OCR text *before* the extract call** (deny-by-default); **on-cluster free model first**; an EU-resident model only, **never a US model with unmasked PII**; LiteLLM governs model routing |
| 5 | **Information disclosure** — the raw document egresses somewhere unintended | 2,3 | **SEC-02 explicit-allow egress** — the worker may reach *only* indra, LiteLLM, Langfuse, the two lookups, NATS, DNS; nothing else (default-deny); indra is in-cluster + self-hosted (ADR-002 — OCR itself never leaves) |
| 6 | **Elevation of privilege** — the worker over-reaches into claim/policy systems (reads more than it should, or writes) | 4 | **SEC-03** a *scoped, read-only* M2M identity (Authentik client-credentials, lookup scope only) — not a human token, not a write scope; **SEC-04** the worker has **no** write capability on any claim/policy system (it only PATCHes Paperless custom fields) |
| 7 | **Integrity** — a **hallucinated** or wrong match mis-files a sinistre document | 3 | **FR-02 validation** (a claim#/policy# that doesn't exist in the SoR is rejected) **+ AI-01 HITL** on low confidence/ambiguity (never auto-file an uncertain match) — the model *suggests*, the system *verifies*, a human *confirms* the doubtful |
| 8 | **Confused-deputy** — a doc that validates but belongs to a *different* client | 3,4 | the QA gate explicitly tests this; the validation returns the record's client → compared to the extracted client; mismatch → `needs-review` (HITL), not auto-file |
| 9 | **Credential compromise** — the worker's tokens leak | assets | all creds via **ESO→Vault** (never in git — `guard-write`); least-privilege (read-only lookup scope, Paperless-only write); rotate on the normal ESO cadence |
| 10 | **DoS** — a flood of documents starves the cluster | 1 | KEDA bounds `maxReplicas`; LiteLLM budget caps spend; the worker is CPU-modest (OCR is the indra service, separately bounded) |

## Residual / accepted
- **The masked text still goes to an on-cluster model.** Accepted: the model is EU-resident/on-cluster, masked,
  and traced; this is the limited-risk AI-Act posture (`spec-dms-classifier` §5). Revisit if the data class rises
  or a model moves off-cluster.
- **Presidio masking is best-effort** (NER recall < 100%). Compensating: on-cluster model (not a public API),
  default-deny egress, and the document never leaving the cluster for OCR. Revisit trigger: a real-PII / prod claim.

## Review
Approved at the security-review gate as the condition of build (SEC-01…04 + AI-01 are mandatory, not optional).
Cert evidence: **BC03 (déployer & sécuriser)**. Related: `spec-dms-classifier/SPEC.md`, `ADR-001`, `ADR-002`,
`bmad-compliance.md`, `llmops.md`.
