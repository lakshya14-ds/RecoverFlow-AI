# Payments: live gate, webhooks, settlements (P2 D2)

Razorpay stays test/mock until a human explicitly enables live, and every
provider report that the ledger does not yet reflect lands in a staff
discrepancy queue. No webhook, settlement line, or status poll posts money
on its own — except a fully verified captured payment, exactly as before.

## Live gate (disabled by default)

- `RAZORPAY_LIVE_ENABLED` defaults to false. Link create/cancel/recover
  refuse in live mode unless it is true, and the webhook route returns 503
  for live-mode tenants while it is false.
- Per-tenant mode comes from the `razorpay_mode` tenant setting (`local`
  falls back to `RAZORPAY_MODE`). Every stored event and link records its
  mode, so test and live can never mix silently.
- `GET /payments/razorpay/status` reports one honest state per tenant:
  `not_configured`, `test`, `mock`, `live_disabled`, or `live`, with event
  counts and open discrepancies. Secret values never appear; only the
  (publishable) key ID and booleans.

## Webhook handling

Verified by raw-body HMAC per tenant (401 on bad signature, 413 over 1MB,
422 without an event ID, 409 when an event ID is reused with different
bytes). Retried deliveries are idempotent. Outcomes:

| Event | Result |
|---|---|
| `payment_link.paid` / `partially_paid`, captured, amounts/currency match | Payment posted; link paid/partially_paid |
| Same, but uncaptured / mismatched / unknown link / bad ID | `needs_review`, nothing posted |
| `payment.failed` | `processed` + `payment_failed` audit; link keeps `last_error`; nothing posted |
| `refund.processed` / `payment.refunded` | `needs_review` + `refund_unposted` discrepancy; case suppressed for review |
| `dispute.*` | `needs_review` + `chargeback` discrepancy |
| `payment_link.cancelled` / `expired` | Link status follows |
| `settlement.*` | `needs_review` — parked for staff matching, never auto-applied |
| Anything else | `ignored` |

Out-of-order delivery is safe: a refund that arrives before its payment
queues a discrepancy with no invoice link, and resolving with
`post_reversal` refuses until the original payment is posted.

## Discrepancy queue

`GET /payments/discrepancies` lists open (or resolved) items:
`refund_unposted`, `chargeback`, `settlement_short`,
`settlement_unmatched`, `amount_mismatch`. Resolution is admin-only:

- `post_reversal` — posts a linked reversal of the original Razorpay entry
  (refunds/chargebacks only), restores the outstanding, and closes the
  linked event as `resolved`.
- `dismiss` — closes with a note; the ledger is untouched.

## Settlements

`POST /payments/settlements` takes a provider settlement report
(`settlement_ref` + lines of payment reference, settled amount, fee) and
matches each line against posted entries: `matched`, `short` (settled
less than posted), or `unmatched` (no such payment). Mismatches queue as
discrepancies; re-uploading the same report is a 409. A created payment
link or a received webhook is never treated as settlement — only this
matching step reconciles provider money against the ledger.

## What is NOT verified

No Razorpay sandbox account has been connected in this build: all D2
behavior is proven against synthetic signed payloads and the
`rzp_test_mock` link path. Sandbox verification with duplicates, bad
signatures, stale events, partial settlement, refunds, and
reversal-after-posting still needs test-account access, and any live
charge or live webhook needs explicit authorization plus that account.
Current honest status: **mock-tested, sandbox-pending, live disabled**.
