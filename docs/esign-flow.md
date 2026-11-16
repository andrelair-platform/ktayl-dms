# DMS ↔ Docuseal e-signature — reference flow (design sketch)

> **Status: DESIGN SKETCH, not built.** Phase-3 e-sign wiring for the DMS (#24). Docuseal is already live
> on the platform (`https://sign.devandre.sbs` / `docuseal.sign.svc.cluster.local:3000`); this sketches the
> thin, reversible integration that lets a DMS document be sent for signature and captured back. Scope it to
> **one reference flow first** (a broker mandate), then generalise. Owner: SA/TL + Compliance (#15).

## What it connects
```
Paperless doc flagged for signature          Docuseal (live, ns `sign`)
  (a `needs-signature` tag / a custom field)       REST API + templates + webhooks
          │                                              │
          ▼  (1) create submission (REST)                │
   dms-esign worker ──────────────────────────────────▶ Docuseal: create a submission from the
   (same classifier image, 12-factor #12)               document/template, add the signer(s)
          ▲                                              │
          │  (3) capture-back the signed PDF             │ (2) signer completes in the browser
          └──────────────◀──────── Docuseal webhook ─────┘     (SSO'd; BYOD browser-first)
                     NATS `dms.esign.completed`
```

## The flow (one reference case: a broker mandate)
1. **Trigger** — a Paperless document gets a `needs-signature` tag (by a human, or a future rule). A small
   worker (reusing the classifier image + its Paperless client; **not** a new service) lists
   `needs-signature` docs and, for each, calls the **Docuseal REST API** to create a *submission*: upload
   the PDF (or reference a Docuseal template), set the signer email(s), set a webhook/redirect. Docuseal
   returns a submission id + a signing URL. Tag the doc `esign-sent` (idempotent).
2. **Sign** — the signer opens the signing URL in the browser (BYOD, SSO where applicable), signs. No local
   file handling — data stays server-side (`workplace-architecture.md`).
3. **Capture-back** — Docuseal fires a **completion webhook**. A tiny webhook receiver (or n8n) publishes
   **`dms.esign.completed {submission_id, document_id}`** to NATS JetStream; a consumer (the same worker)
   downloads the **signed PDF** from Docuseal and re-ingests it into Paperless (Paperless consume dir / API),
   linked to the original (a `signed-of:<id>` custom field), and tags the original `esign-complete`.

## Pieces to build (when this graduates from sketch → build)
- **Docuseal API token** → Vault `secret/platform/docuseal` → ESO → the worker env (never inline).
- **A `dms-esign` worker** — reuse the classifier image (`python -m app.esign`), a `needs-signature`
  Paperless query + a Docuseal REST client (httpx). Archive-only on the DMS side (it adds a doc, never deletes).
- **A webhook path** — either a thin FastAPI receiver (Gatekeeper-compliant, SSO/forward-auth or a shared
  secret) that publishes to NATS, **or** an **n8n** workflow (already live) doing Docuseal-webhook → NATS →
  Paperless (lowest-code; preferred for a reference flow).
- **NetworkPolicy** — the worker egress to `sign` ns :3000 (Docuseal) + Docuseal→webhook ingress; same
  open-egress + ingress-deny posture as the rest of ktayl-dms.
- **A NATS stream** `DMS_ESIGN` (subject `dms.esign.*`) — stream-init Job (the `DMS_DOC` pattern).

## Why a sketch, not a build (now)
E-sign crosses a **service boundary + a legal-evidence boundary** (a signed mandate is a regulated record):
it warrants a short SDD + a security review (the governance gate) and a decision on the **signature
assurance level** (simple vs advanced/qualified eIDAS — Docuseal is simple/advanced, not QES). Build it as a
scoped Path-B epic on board #24 once the reference case (broker mandate) is confirmed. The signed output then
flows into the **retention** archival (class `regulatory`/`policy`, 10-yr window — `retention-policy.md`).

Related: `workplace-architecture.md` (browser-first, data-server-side), `bmad-compliance.md` (governance
gate + regulatory layer), `retention-policy.md` (the signed record's retention), the live Docuseal deploy.
