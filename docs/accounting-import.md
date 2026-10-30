# Accounting import (P2 D1)

Staff upload a batch of receivables from the business's books; the batch is
previewed, confirmed idempotently, and reconciled against its source. The
import side is read-only: nothing ever writes back to the accounting
system, and no write-back exists to enable.

## Profiles (the honesty boundary)

Only `generic_csv` exists: UTF-8 rows with canonical headers. There is no
Tally, BUSY, or Zoho profile, and unknown profile names are rejected. A
vendor profile gets built only from a sanitized export supplied by the
pilot business, and goes through the same mapping/preview/validation
contract below. Any claim of vendor support without that export would be
fabricated; the API enforces this by rejecting unknown profiles.

## Mapping contract

`app/services/import_adapter.py`:

- `map_row` — pure mapping from foreign headers to the canonical shape
  (`external_id`, `invoice_number`, `customer_name`, `issue_date`,
  `due_date`, `amount`, optional email/currency). No writes.
- `validate_row` — types, dates, positive two-decimal amounts, three-letter
  currency. Raises with the row number; never guesses.
- `preview_import` — maps + validates up to 500 rows, returns mapped rows
  plus errors. The `/imports/preview` endpoint exposes this with no writes.

## Runs, idempotency, conflicts

`POST /imports/runs` starts a run: preview errors (including an external
ID that appears twice with different data) mark the run `invalid` and
block confirmation. A caller-supplied `idempotency_key` makes retries
safe — replaying the key returns the same run; reusing a key with a
different payload is a 409. The SHA-256 `source_hash` records exactly
which bytes a run came from.

`POST /imports/runs/{id}/confirm` imports clean rows and queues the rest:

- Already-imported external IDs with identical data are skipped (re-running
  the same file imports nothing new).
- External IDs that disagree with the ledger become open `ImportConflict`
  rows naming the differing fields and linking the existing invoice. Clean
  rows in the same batch still import; the run reports
  `partially_confirmed`.
- Re-confirming is safe: no duplicate invoices, no duplicate conflicts.
- Resolutions are `keep_existing` or `source_will_fix`; the queued row
  stays unimported either way until the source is fixed and a new run
  arrives. Staff confirmation is required before anything touches
  receivables.

The strict all-or-nothing `/imports/confirm` path is unchanged for callers
that want it.

## Provenance, cursor, reconciliation

Every invoice keeps `source_system` + `source_record_id`. Every run keeps
its mapped payload, a cursor (`last_row` + sorted external IDs, the
checkpoint a future incremental pull resumes from), and a reconciliation
report: per-currency source/imported/skipped/conflicted/invalid totals
that must add up (`imported + skipped + conflicted + invalid == source`).
`GET /imports/runs/{id}` returns the run with its report and conflicts;
`GET /imports/conflicts` is the staff queue.

## Tests

`tests/test_p2_d1_import_runs.py` (12 tests): happy-path reconciliation,
idempotent replay, key-reuse-with-different-payload 409, same-file-twice
skip, conflict queueing with clean rows importing, invalid-blocked confirm,
identical-duplicate dedupe, totals arithmetic, strict-path regression pin,
cross-tenant 404s, unauthenticated 401, unknown-profile rejection.
