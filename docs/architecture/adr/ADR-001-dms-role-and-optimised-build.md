# ADR-001 — DMS role (transversal layer) + optimised, scale-to-zero build (ktayl-dms #24)

**Status:** Proposed / DRAFT for review (build not started — `AGENTS.md`) · **Owner:** SA/TL + SEC ·
**Board:** #24 (Documents & DMS). Decides *what the DMS is* for the insurance IS, *how it's built* (adopt the
engine, reuse the AI platform for matching), and *how it fits a resource-constrained cluster*. Applies the IS
**software-evaluation chain** (`software-evaluation.md`); the evaluation record lives **here** (not Retrieva).

## Context
Insurance is document-heavy and the documents are only valuable when **linked to the business record they
belong to**: *sinistre (claims)* docs (FNOL, loss-adjuster/expert reports, photos, invoices, correspondence,
settlement letters) → a **claim #**; *policy/client* docs (contracts, endorsements, attestations, CG/CP) + **KYC**
docs (ID, proof of address, KBIS/registry, beneficial-owner evidence) → a **policy #** / **client**. The board
scope is GED/records-mgmt · archiving · doc generation · OCR/IDP · templates · e-sign. The cluster is
**resource-constrained** (several nodes 66–83% memory, flaky Longhorn) — so the design must deliver *full
capability without a full always-on footprint*. ktayl is synthetic → built to **demonstrate** the capability.

## Decision 1 — Role = **(B) transversal capture/search/records layer**, NOT a central store-for-all
**Each business domain OWNS its operational documents; the DMS is the shared cross-cutting capability** (capture,
OCR, full-text search, records-management/retention/archiving, e-sign, doc generation) that the domains +
compliance consume. *Rejected:* (A) a central store that every domain must route through — it couples every
domain to the DMS and fights the modular-monolith principle (a module never reaches into another's data).
*Why B:* (1) matches the modular-monolith rule (domains own their data — `architecture-strategy.md`); (2) matches
**what already exists** (claims handles claim documents; policy had the attestation PDF); (3) low coupling — a
domain keeps its doc references, the DMS indexes/retains/searches/e-signs on top; (4) the DMS stays optional to
any single domain's request path (it's a capability, not a hard dependency).

## Decision 2 — Adopt the engine, reuse the platform, build only the glue (`architecture-strategy.md` split)
| Part | Decision | Tool |
|---|---|---|
| Capture / **OCR** (PDF+image) / **full-text search** / store / UI | **ADOPT** | **Paperless-ngx** — ~~OCR (Tesseract/OCRmyPDF)~~ **and** search (Whoosh) are **built into the main container**: **no Elasticsearch, no OCR sidecar** for the common insurance doc. ⚠️ **The OCR element is SUPERSEDED by [ADR-002](./ADR-002-ocr-engine-indra.md):** scan/image OCR moved to the self-hosted **indra** engine (CPU-only, far higher accuracy on handwriting/tables/poor scans — Phase-2 match accuracy depends on it). Paperless keeps its built-in Tesseract as the reversible fallback. |
| **Matching** (a doc → its claim#/policy#/client) — the real value-add | **BUILD (governed AI glue)** | **reuse the live AI platform** (LiteLLM + Qdrant + Langfuse): a small event-driven worker extracts the business key + files the doc; **no new ML infra** |
| **E-signature** | **ADOPT (already live)** | **Docuseal** (ns `sign`, running) |
| **Doc generation** (policy PDF / attestation) | **BUILD (per-domain lib)** | a PDF/template library *in the owning ktayl-core module* — ~zero standing pods |
| Office-doc OCR (docx/xlsx → PDF) | **ADOPT, but dormant** | Gotenberg + Tika — **KEDA scale-to-zero** (only on an office-doc event) |
| Retention / archiving | **BUILD (light)** | Paperless custom-fields + a retention CronJob |

**Sovereign-first scorecard (software-evaluation.md):** Paperless = self-hostable FOSS, SSO-able, golden-path
deployable, PII stays in-house → **wins** over a commercial ECM/DMS SaaS (sovereignty/licence/TCO + a material
ICT third-party) and over building a store from scratch.

## Decision 3 — The "matching" model (the document brain)
Two layers: **metadata** (every doc carries `policy#` / `claim#` / `client` as Paperless custom-fields — near-zero
cost) + **AI extraction** (an inbound/scanned doc is read by a governed LLM that infers the business key and
auto-files it to the right claim/policy). Governed-AI rails (reuse `ADR-005`/`llmops.md`): **PII Presidio-masked
before any LLM**, identity-propagated, **Langfuse-traced**, **HITL on an ambiguous/low-confidence match** (don't
mis-file a sinistre doc silently). EU AI-Act: *limited-risk* (HITL-assisted classification, not an autonomous
decision on a person).

## Decision 4 — Optimised, scale-to-zero footprint (the tight-cluster answer)
Full capability, minimal standing footprint — levers:
1. **Built-ins over sidecars** — OCR + search live in the one Paperless pod (the biggest saving; no ES, no Gotenberg/Tika for PDF/image).
2. **KEDA scale-to-zero** — the office-OCR sidecars **and** the AI-matching worker cost ≈0 when idle; they wake on a consume event (platform already runs KEDA).
3. **Reuse, don't duplicate** — matching rides the **live AI gateway**; e-sign is **Docuseal (live)**; the broker can reuse platform **Valkey** or a 64Mi Redis.
4. **Dev-first, 1 replica, Longhorn RF=1** (the storage/dev tier); `Recreate` strategy for the RWO document PVC.
5. **Schedule to headroom** via **soft** anti-affinity (toward the light nodes) — **never a node-pin** (`scheduling.md`; Longhorn is network-attached).

**Standing footprint (idle):** `paperless-web · redis(tiny) · cnpg(1)` ≈ **3 small pods + 1 PVC** — with OCR,
search, e-sign, generation, retention and matching all *present* but built-in / reused / scaled-to-zero. (Naive
always-on full stack = ~7 pods — avoided.)

## Phased delivery (each phase demonstrable; none wasteful)
- **Phase 1 — the engine**: Paperless (built-in OCR+search) + Redis + CNPG(1) + Authentik SSO + ingress/TLS +
  storage PVCs + ESO→Vault secrets + netpols; GAP wrapper chart in `minicloud-gitops`, Kargo dev→prod. *Capture → OCR → search → store, SSO-gated.*
- **Phase 2 — the matching**: the custom-field schema (policy#/claim#/client) + the KEDA event-driven **AI-filing worker**. *The document brain.*
- **Phase 3 — the edges (on need)**: office-OCR sidecars (KEDA), Docuseal e-sign wiring into the flows, per-domain doc-generation, the retention CronJob.

## Security / data classification (for the security review)
Documents are **P2/P3** (claims + KYC docs are sensitive PII/financial). SSO-gated (Authentik); **access control
ties a doc's visibility to its domain's authz** (who may see a claim's docs = who may see the claim); default-deny
egress (only the module/worker reach Paperless; the AI worker reaches the gateway); **no unmasked PII to any LLM**;
**retention** honours insurance record-keeping (years) — a records concern, not just storage. The document PVC is
the one fragile piece on Longhorn → RF=1 dev, backup before any prod claim.

## Consequences
- **Positive:** the **full DMS capability** (capture/OCR/search/match/e-sign/generate/retain) on a **3-pod idle
  footprint**, sovereign + licence-clean, reusing the AI platform + Docuseal; the matching is the differentiated
  value (a "document brain", not a file dump); role B keeps domains decoupled.
- **Negative / accepted:** documents live on a Longhorn PVC (Paperless has no first-class S3 store) — the storage
  caveat; office-OCR is dormant until needed; free-tier scope (synthetic disclaimer).
- **Next (post-approval):** `/bmad-spec` for the DMS epic; **build Phase 1** (the Paperless GAP wrapper chart in
  `minicloud-gitops` + Authentik OIDC + the Vault secret) then Phase 2 (the AI-filing worker).

Related: `software-evaluation.md`, `architecture-strategy.md` (role + adopt-vs-build), `scheduling.md` (no pins),
`datastore-selection.md` (CNPG) + storage tiering, `ADR-005`/`llmops.md` (governed AI matching), `bmad-compliance.md`
(data-class + AI-Act), github-projects.md (#24 scope); consumers: claims (live), policy/billing (ktayl-core), compliance (#15).
