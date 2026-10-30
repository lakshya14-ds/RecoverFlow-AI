# Communication policy (P2 D3)

WhatsApp replies, approved templates, per-invoice consent, quiet hours, and
delivery tracking. Live sending stays off per channel until onboarding plus
explicit authorization; everything below is proven in sandbox.

## Threads and the 24h window

Inbound messages arrive signed, deduplicated, and phone-matched
(`meta_whatsapp.receive`). Staff triage each message onto an invoice with a
category; triage records through the shared customer-message path, so a
WhatsApp dispute sets the same flags, checkpoint, and supervisor
reassessment as any other channel — previously it skipped the lifecycle.

Replies to a triaged message inside 24 hours send as free text (staff-typed,
`guard_outbound`-checked, idempotent). After the window expires, only an
approved template may go, on the same triaged thread.

## Templates

`message_templates` holds one approved body per name per tenant, with
language (`en`/`hi`/`hinglish`), category, and Meta-style `{{1}}`
positional variables (validated sequential on create). Lifecycle:
editor creates draft → admin approves → sends reference it; admin can
archive. A send renders variables strictly (missing, empty, over-long, or
extra variables are 409s) and runs the rendered text through
`guard_outbound` again, so a template cannot smuggle a waived or disputed
amount past the server facts.

## Consent and language

`comms_preferences` records per-invoice, per-channel (`whatsapp`/`email`)
opt-in with basis (`explicit`/`implicit`/`contract`) and language.
Template sends require an opted-in row and a template whose language
matches the send language; the invoice-level opt-out is a hard block for
every send. (Party-level consent across merged counterparties is future
work; invoice-level matches where the contact flags already live.)

## Quiet hours

Tenant settings `comms_quiet_start`/`comms_quiet_end` (HH:MM IST, default
21:00–09:00). Template sends inside the window are stored as
`held_quiet_hours` with `held_until` and release explicitly
(`POST /messages/outbound/{id}/release`, which re-checks the window and
contact permission). Direct in-window replies are exempt — answering a
customer who just wrote is conversational, not a broadcast.

## Delivery tracking

Outbound rows carry provider, provider message id, delivered-at, and
failure reason. The Meta webhook's `statuses[]` array updates them:
delivered/read → `delivered`; failed → `failed` with the provider error
code and title; sent → `sent`. Unknown message ids count as ignored, and
every update writes an audit event. `GET /messages/outbound` shows the
per-invoice delivery state. A queued message is not delivered; a delivered
message is not a payment commitment.

## Live gates (all off)

- `whatsapp_enabled` / `email_enabled` tenant toggles, default false.
- WhatsApp live additionally needs the global provider config; otherwise
  the send is refused (nothing half-sent: the row rolls back).
- Non-local tenants get 503 for live WhatsApp: per-number send parameters
  are not wired yet (secrets are per-tenant since A2; the send call still
  uses the pilot number).
- Email has no send endpoint in this milestone and no SMTP library is
  installed: email templates and consent are recorded, delivery stays
  dry-run. SMTP credentials + account onboarding are the blockers.

## Email equivalents

Templates, preferences (channel `email`), quiet hours, and the enable
toggle apply to email identically. The connector (`EMAIL_DRY_RUN=true`)
never delivers until the account exists and the toggle flips.

## Tests

`tests/test_p2_d3_comms.py` (11 tests): template lifecycle + validation,
preferences, triage→lifecycle routing, sandbox reply + idempotency,
expired-window block, template reply after expiry, template guards
(draft/language/waiver/opt-out), quiet hold + release + reply exemption,
live gate (enabled-but-unconfigured refuses, bad toggle 422), delivery
receipts (delivered/failed/unknown) + outbound list, cross-tenant guards.
