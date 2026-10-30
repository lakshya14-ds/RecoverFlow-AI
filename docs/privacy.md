# Privacy readiness (F1)

RecoverFlow holds personal data about two groups: the distributor's
**customers** (counterparties and their contacts) and the distributor's
**staff**. This document inventories that data, defines the request
workflows, and records the incident procedure. It is an operational
procedure, **not a compliance claim**: DPDP applicability, retention
periods, and every deletion decision below need review by counsel before
anyone promises compliance to a customer.

## 1. Regulatory status (checked 2026-10-30)

- The Digital Personal Data Protection Act, 2023 and the DPDP Rules, 2025
  were notified in November 2025 (Gazette G.S.R. 843(E) / 846(E) of
  13 November 2025, per secondary summaries; the MeitY rules page itself
  renders no readable text and the Gazette copy still needs direct
  verification by counsel).
- Commencement is phased: Board/administrative provisions first, the
  consent-manager framework about a year later, and the substantive
  Data Fiduciary duties (security safeguards, breach notification,
  principal rights) about 18 months after notification — roughly
  **May 2027**.
- CERT-In's incident-reporting directions (6-hour reporting for
  specified incident types) already apply to service providers and are
  the binding incident clock today.

Nothing in this file claims DPDP compliance. The workflows exist so the
business is ready when the substantive duties commence.

## 2. Personal-data inventory

All rows are tenant-scoped; nothing below crosses tenants.

| Store | Personal data | Purpose | Access |
|---|---|---|---|
| `counterparties` | contact name, email, phone, addresses, GSTIN | billing, collection | staff of the tenant |
| `counterparty_branches` | branch addresses | shipping/billing | staff of the tenant |
| `counterparty_external_ids` | foreign-system IDs | import matching | staff of the tenant |
| `invoices` | counterparty name/email/phone snapshot, OCR text | books of account | staff; safe subset on portal |
| `customer_messages` | message bodies (free text) | dispute handling | staff of the tenant |
| `inbound_messages` | sender phone, body | reply handling | staff of the tenant |
| `outbound_messages` | recipient phone, body | collection follow-up | staff of the tenant |
| `case_evidence` | snippets, descriptions | investigation | staff of the tenant |
| `promises_to_pay` | source text naming people | promise tracking | staff of the tenant |
| `stored_documents` | file bytes (challans, receipts, photos) | evidence | authorized reads, logged |
| `portal_tokens` | prefix, usage (hash only, never the token) | customer access | staff of the tenant |
| `portal_attempts` | IP addresses | rate limiting, abuse | staff; pruned, never exported |
| `comms_preferences` | consent + language per invoice | lawful contact | staff of the tenant |
| `users` | staff name, email (login) | authentication | admins; self |
| `user_api_keys`, `user_sessions`, `user_recovery_tokens` | hashes + metadata | authentication | admins; self |
| `audit_events` | staff actor strings, action details | accountability | staff of the tenant |
| `privacy_requests` | request + resolution text | rights handling | admins |
| AFIS / AXIS sidecars | read-only external transfers | matching | staff; **out of erasure scope** (source-owned) |
| Server logs | IPs, request paths | operations | operators |

Secrets (password hashes, key/token hashes, provider credentials) are
never exported, never logged, and never returned by any API.

## 3. Subject-request workflows

Admin-only API under `/api/v1/privacy`. Every step writes an audit row.

- **Open:** `POST /privacy/requests` with `kind` (access/export/
  correction/deletion), `subject_type` (counterparty/staff_user),
  `subject_ref` id, and `details`. Staff first verify the requester is
  the principal or their authorized contact and record how in `details`.
- **Triage:** `POST /privacy/requests/{id}/review` marks in-review;
  `POST .../reject` refuses with a recorded reason (e.g. unverified
  requester). Rejected and fulfilled states are terminal.
- **Access/export:** `POST .../fulfill` returns the bundle assembled by
  `collect_subject_data` (see `app/services/privacy.py`). File bytes
  stay in private storage; the bundle references document ids for
  refetch through the authorized documents API.
- **Correction:** `details` names `entity` + `fields`. Only contact
  fields are correctable (counterparty email/phone/addresses/
  display name, branch addresses, staff name). Names on the books,
  GSTINs, amounts, and login emails are rejected — they change books
  or authentication, and go through the normal staff flows instead.
- **Deletion preview:** `GET /privacy/deletion-check` lists blocks
  without changing anything.

### Deletion rules

Blocked while the counterparty has any invoice outside `paid`/`adjusted`,
or any linked document on retention hold. Staff deletion is blocked for
one's own login and for the tenant's last active admin.

On execution the service erases contact fields (counterparty + branch +
invoice snapshots), redacts message bodies and sender/recipient channels,
clears evidence snippets and promise source text, removes stored file
bytes (rows stay as tombstones), and revokes portal tokens.

**Kept by design:** invoices, ledger entries, names on the books, GSTINs,
consent records, and the audit trail — books-of-account and accountability
records the business must retain. The fulfillment resolution states this
explicitly. Counsel confirms the retention basis per deployment.

## 4. Retention and holds

- Stored documents carry `retention_expires_at`; the purge endpoint
  removes expired bytes but never rows on `hold` (see
  `docs/document-security.md`).
- A deletion request never overrides a hold. Holds are set for tax
  audit, litigation, or an open dispute, with a recorded reason, and
  cleared by an admin when the reason lapses.
- Portal attempt logs are pruned regularly and never exported.

## 5. Notices (templates — counsel to approve before use)

**Customer notice (portal + first message):** what is collected (bill
details, contact details, messages, uploaded evidence), why (credit
collection for the named distributor), who sees it (the distributor's
staff only), how long it is kept (accounting retention + dispute
limitation), and how to ask for access/correction/deletion (reply to
the distributor, who raises a request in RecoverFlow).

**Staff notice (onboarding):** login identity, action logging
(non-erasable while employed and for the audit retention after),
and the offboarding erasure flow (login deactivated, sessions/keys
revoked, audit actor strings kept).

## 6. Incident response

1. **Detect:** unusual access-log entries, alert spikes, provider
   failure bursts, or a staff/customer report. Record who saw what
   and when in an audit note; do not delete logs.
2. **Contain:** revoke the affected keys/tokens/sessions, rotate
   provider credentials from the vault, quarantine affected documents.
   Money-affecting paths stay staff-approved — there is no remote
   kill-switch that posts ledger entries.
3. **Assess:** which tenants, which subjects, which data classes
   (inventory §2), and whether money or credentials were touched.
   Preserve evidence: export the relevant audit slice before any
   repair migration.
4. **Notify:** CERT-In reporting within 6 hours for covered incident
   types; affected distributors immediately; affected principals
   without delay once scope is known. DPDP breach notification to
   the Board (when those duties commence, ~May 2027) follows
   counsel's call.
5. **Recover and learn:** close the cause, rotate again after the fix,
   run the restore drill if data was touched, and append a dated
   entry to `.codex/handoff.md` with cause, scope, and fix.

## 7. Known limits

- No automated PII redaction in free-text fields; erasure is by
  recorded request, not by scanning.
- OCR text on invoices is kept as a books record even after erasure.
- AFIS/AXIS sidecars are read-only sources; erasure there belongs to
  the source system.
- No Data Protection Board registration or consent-manager
  integration — not yet in force; revisit before May 2027 with
  counsel.
