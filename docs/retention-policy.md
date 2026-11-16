# DMS Document Retention Policy (ktayl-solution)

> **Scope.** The records-retention standard for documents held in the DMS (Paperless-ngx, #24). It defines
> (a) how long each class of document must be **kept**, (b) the **offsite archival** that preserves it for
> that window, and (c) when it becomes **eligible for purge**. This is an IS organisational-governance
> artefact (compliance-by-design, `bmad-compliance.md` regulatory layer) — ktayl is a synthetic French/EU
> insurer, so the windows below follow **French + EU** statute. Owner: Regulatory & Compliance (#15).

## The two forces (both apply — don't conflate)

1. **Regulatory minimum — how long we MUST keep it.** Insurance, accounting, AML and ACPR/DORA rules set a
   *floor*: destroying a record before its window is a compliance breach.
2. **GDPR maximum — how long we MAY keep personal data.** Art. 5(1)(e) *storage limitation*: once the
   statutory window (and any active litigation hold) has lapsed, personal data **should be purged**. So a
   record has a *keep-until* and then becomes *purge-eligible* — it is not kept forever.

The DMS resolves this as: **archive offsite for the full retention window → mark purge-eligible when it
lapses → purge only by a separate, human-approved step** (never automatic — see *Deletion discipline*).

## Retention matrix (the default standard)

Each document is mapped to a **retention class** from its Paperless `doc_type` / tags / the presence of a
policy#/claim# custom field (set by the classifier, #14). Windows start from the stated trigger.

| Class | Examples | Retention window | Trigger | Legal basis |
|---|---|---|---|---|
| **policy** | contracts, policies, endorsements (avenants), schedules | **10 years** | after the contract ends | Code des assurances; aligned to the 10-yr commercial-record rule |
| **claim** | claim files (sinistres), expert reports, settlements | **10 years** | after claim closure | prescription biennale (C. assur. L114-1) + a large buffer for reopening/litigation; *life/unclaimed up to 30 yrs* |
| **financial** | premium invoices, billing, accounting, GL | **10 years** | end of the fiscal year | Code de commerce L123-22 |
| **kyc** | client identification, AML/KYC, sanctions evidence | **5 years** | after the business relationship ends | CMF L561-12 (AMLD transposition) |
| **regulatory** | compliance, audit evidence, ACPR/DORA records, PIAs | **10 years** | document date | ACPR/DORA record-keeping |
| **correspondence** | general business letters, emails of record | **5 years** | document date | prescription civile (C. civ. 2224) |
| **internal** | tariffs, internal operational notes | **3 years** | document date | operational default |
| **marketing** | non-record marketing material | **1 year** | document date | no statutory floor |
| **default (unclassified)** | anything without a mapped class | **10 years** | document date | **conservative fallback** — never under-retain an unknown record |

> **Conservative default is deliberate.** An unmapped document defaults to the longest common window
> (10 yrs) — under-retaining a regulated record is the costly error; over-retaining is a (bounded) GDPR
> concern resolved at purge time, not a compliance breach.

## Offsite archival (what the retention CronJob does — ARCHIVE-ONLY)

A daily CronJob (`services/ktayl-dms/helm` → `retention-cronjob.yaml`, runs the classifier image) gives every
DMS document a **durable offsite copy** so regulated records survive a DMS/Longhorn loss and are organised by
their legal window:

- Lists Paperless documents; for each **not yet tagged `archived`**, derives its retention class + computes
  `keepUntil` (trigger date + window), downloads the file + a metadata JSON, and **uploads to Cloudflare R2**
  under `dms-archive/<class>/<keepUntilYear>/<docId>/` (S3-compatible, zero-egress, offsite — DORA Art. 11–12
  business-continuity evidence).
- Tags the document `archived` in Paperless → **idempotent** (never re-archives).
- **It NEVER deletes anything** — not from Paperless, not from R2. Archival ≠ deletion.

## Deletion discipline (purge is OUT of this job — safe by default)

- The CronJob ships **`deleteEnabled: false`** and **`DRY_RUN` default** — it only *reports* what it would
  archive until explicitly enabled, and it has **no delete code path at all**.
- A record only becomes **purge-eligible** once `keepUntil < today` **and** no litigation/regulatory hold
  applies. Acting on purge-eligibility (actually destroying a regulated document) is a **separate,
  human-approved, logged** operation — never a scheduled job. Multi-year insurance records + ACPR audit
  risk make silent auto-deletion unacceptable.
- **Revisit trigger** for enabling a purge step: a real audit requirement, a GDPR erasure request at volume,
  or storage pressure — then design it as an approval-gated workflow, not a cron.

## How a document's class + trigger date are resolved (implementation note)

`doc_type` (Paperless custom field) → class directly where set; else inferred from tags / a claim#|policy#
custom field (claim# → `claim`, policy# → `policy`); else `default`. The **trigger date** uses the document's
`created` date as a safe proxy (contract-end / claim-closure dates aren't modelled in the DMS yet — a
future enhancement would read them from the owning domain). Using `created` **over-retains** slightly
(window starts earlier than the true trigger) — the safe direction.

Related: `ktayl-dms/docs/architecture/adr/ADR-001` (DMS = transversal capture/preservation layer),
`bmad-compliance.md` (regulatory layer), the offsite-DR pattern (`cloud-adoption.md` DORA Art. 11–12).
