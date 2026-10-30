# Customer portal (P2 C1)

One authorized invoice per link. Staff issue a short-lived token (the link
is `portal.html?token=...`); the customer sees their own bill, raises a
dispute, attaches evidence, or reports a payment they made. Every
submission enters staff review. Nothing the portal accepts moves money.

## Access model

- `PortalToken` (migration `20261107_portal_v12`): bound to one tenant + one
  invoice, fixed capability set, `PORTAL_TOKEN_EXPIRE_HOURS` (72h) default
  expiry, revocable with reason. Only the SHA-256 hash is stored; the raw
  token is shown once at issue time.
- The token travels as `X-PORTAL-TOKEN` or `?token=`. Unknown tokens get a
  plain 403 that does not say which half failed.
- Expiry is explicit: expired links return 410 with "ask the business for a
  new one". Revoked links return 403.
- Rate limits (15-minute window): 60 requests per token, 200 per IP, and 20
  invalid-token guesses per IP before 429. Attempts are logged in
  `portal_attempts` (pruned after 24h, never exported).
- Staff token endpoints live under `/cases/{id}/portal-tokens` (admin-only
  issue/revoke, list shows metadata only). The portal token is not staff
  auth: presenting it as `X-RECOVERFLOW-API-KEY` returns 401.

## Safe summary

`GET /portal/case` returns only the customer's own bill: invoice number,
counterparty name, dates, currency, total/received/outstanding/disputed/
undisputed, a coarse status (open/disputed/partially_paid/paid/adjusted),
link expiry, and the customer's own portal submissions with a review flag.
Internal notes, staff identities, other invoices, drafts, audit history,
and provider secrets are never included.

## Submissions

| Action | Effect |
|---|---|
| `POST /portal/disputes` | Same recording path as staff (`record_customer_message`): sets `dispute_open`, pauses contact, checkpoints, triggers supervisor reassessment. An amount creates an **alleged** evidence row. Always sets `requires_human_review`. |
| `POST /portal/evidence` | Raw-body upload (`X-Filename`, `X-Note`), stored via the private document store as `pending` (staff must release). Creates an **alleged** evidence row, triggers reassessment. |
| `POST /portal/payment-references` | Records a `paid_claim` message. The reference is a **claim until independently verified**; the ledger is untouched. |
| `GET /portal/evidence` + `/file` | The customer can list and re-download only files uploaded with the same token. |

Injection screening applies to portal text exactly as to staff-recorded
replies: an override attempt is stored as `untrusted_evidence` with contact
suppressed, and never flips dispute state.

## Page

`frontend/portal.html` + `frontend/portal.js`: single-column, mobile-width
layout reusing the app stylesheet. Handles missing/expired/revoked/
rate-limited states in plain language. Staff review the submissions in the
existing case view; the portal shows only "received / under review".

## Tests

`tests/test_p2_c1_portal.py` (12 tests): issue/list/revoke + editor block,
summary safety (planted secret strings absent), token states (missing/
tampered/expired/revoked), per-token and guess rate limits, dispute →
staff review with ledger untouched, payref as unverified claim, evidence
round-trip + per-token isolation, dangerous-upload rejection, injection
containment, portal-token-is-not-staff-auth, cross-tenant 404s.
