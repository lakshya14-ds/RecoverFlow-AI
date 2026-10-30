# Operator runbook (P2 E)

RecoverFlow has atomic job claims and lease recovery, tested with competing
SQLite workers on synthetic jobs. This is not a general distributed
exactly-once or production scaling guarantee. A crashed worker's lease
expires and a subsequent worker pass can claim it. The operator actions
below use API calls.

All ops endpoints are tenant-scoped to the caller's tenant. Reads
(`GET /system/jobs`, `/metrics`, `/alerts`) need staff; replay actions
need admin.

## Everyday checks

- `GET /system/alerts` — every rule with state, owner, severity, detail,
  and first response. Start here on every shift.
- `GET /system/metrics` — queue depth/age, provider events, model
  calls/latency, delivery outcomes, open discrepancies, dead letters.
  Counts and ages only; no customer data by construction.
- `GET /system/jobs?scope=intake&status=queued` — the live queues.
  `error_category` is the exception family; open
  `GET /system/jobs/{scope}/{id}` (audited) for the full error.

## Alert catalog

| Alert | Severity | Owner | Meaning | First response |
|---|---|---|---|---|
| intake_queue_stalled | high | oncall | Oldest queued upload older than `OPS_QUEUE_STALL_MINUTES` (30) | Check the oldest queued row, then the worker process and its logs |
| supervisor_queue_stalled | high | oncall | Same for specialist tasks | Same for the supervisor scope |
| dead_letters_present | high | operator | Poison jobs parked | Inspect each dead row, fix the cause, requeue or dismiss |
| provider_review_backlog | medium | collections_staff | `needs_review` provider events/24h over `OPS_PROVIDER_REVIEW_THRESHOLD` (5) | Work the review queues oldest first; repeated signature failures escalate to oncall |
| model_latency_high | medium | oncall | Average specialist latency/24h over `OPS_MODEL_LATENCY_MS` (120s) | Check provider status and error categories; consider lowering model budgets |
| delivery_failures | medium | operator | Failed outbound in 24h | Open failed rows for provider codes; fix numbers/consent; staff resends |
| unreconciled_settlements | high | collections_staff | Open settlement discrepancies | Work the discrepancy queue; match the next provider report |
| allocation_backlog | medium | collections_staff | Open allocation proposals over `OPS_ALLOCATION_BACKLOG` (10) | Review scored candidates oldest first; ambiguous stays parked |

## Replaying failed work

- Retry one job: `POST /system/jobs/retry {"scope", "id"}`. Works on
  `failed`, `dead_letter`, and `needs_attention`; resets the attempt
  budget with an audit record. Supervisor retries keep using the existing
  `/supervisor/tasks/{id}/retry` too (failed + dead-letter now).
- Resolve a dead letter: `POST /system/jobs/dead-letter/resolve
  {"scope", "id", "decision": "requeue"|"dismiss", "note"}`. Dismiss
  records the operator decision; history stays visible.
- Intake rows in `needs_attention` mean the document needs staff eyes
  first (unreadable file, provider outage text, bad CSV). Fix or replace
  the source, then retry.

## Crashes, leases, and restarts

- A worker that dies mid-job leaves `processing`/`running` with an
  expired lease; any live worker steals it on the next pass (audit
  `job_lease_stolen`). Nothing to do unless it dead-letters.
- On process start, `recover_interrupted_jobs/tasks` requeues legacy rows
  without leases only. It preserves leases held by other processes. Leased
  jobs wait for expiry and are recovered by normal atomic pickup, including
  supervisor jobs still marked `running`.
- Backoff is deterministic exponential (2/4/8… capped 120 minutes).
  `run_due` skips backed-off jobs; the detail view shows `not_before`.
  Retry clears it.
- Duplicate deliveries (webhooks, queue redrives) converge on idempotency
  keys and event IDs: the second delivery returns the existing outcome
  instead of double-posting. If two money rows ever share a reference,
  stop the workers and escalate — that invariant must never break.

## What is not here yet

- Model cost tracking: calls and latency are measured; spend needs a
  pricing table (see milestone F economics).
- Push paging: alerts are pull (`GET /system/alerts`). Wire your
  pager to poll it until push exists.
- Multi-tenant ops console: operators see one tenant at a time.
