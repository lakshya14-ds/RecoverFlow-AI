# Installment schedules (P2 B3)

Promises say "I will pay". Schedules say "in these dated parts". Both are
**nonfinancial records**: they never create ledger entries, and a promise or an
active schedule can never close an invoice. Only verified payments, credits and
reversals posted through `app/services/receivables.py` move money.

## Model

- `InstallmentSchedule` (`installment_schedules`, migration `20261106_installments_v11`):
  tenant + invoice link, optional `promise_id`, free-text terms, status
  `proposed → active → completed`, or `cancelled`. `created_by` /
  `approved_by` / `approved_at` keep the approval history.
- `InstallmentLeg` (`installment_legs`): one dated part — `seq`, `due_date`,
  `amount_cents` (integer minor units), cached `paid_cents`, status
  `pending → partial → paid`, or `rescheduled` / `cancelled`.
  Rescheduling never edits a leg: the old leg is marked `rescheduled` and a
  fresh `pending` leg points back via `supersedes_id`.
- `InstallmentApplication` (`installment_applications`): the money trail —
  which payment entry paid how much of which leg. Reversals flip `reversed`
  to true; rows are never deleted.

A schedule's legs may not exceed the invoice's current outstanding amount at
creation time. Every row carries `tenant_id` and every lookup filters by it.

## Money rules

- Payments waterfall across the invoice's **active** schedules (oldest schedule
  first), and within a schedule across **pending/partial** legs ordered by
  `(due_date, seq)`. Overpayments leave the residual unapplied — it stays on
  the ledger, never on the schedule.
- Credits and debits never apply to legs. Application is idempotent: re-applying
  an entry returns no new rows.
- A reversal un-applies the original payment's rows, restores leg statuses from
  the surviving applications, and reopens a derived `completed` schedule to
  `active`. An explicitly `cancelled` schedule stays cancelled.
- Late vs missed is computed at read time, never stored: `late` = past due and
  still open; `missed` = past due by more than `MISSED_AFTER_DAYS` (30) and
  still open.

## Approvals

Creating a schedule needs an admin identity; approval needs a **different**
admin (separation of duties via `team_ops.sod_allows`, same rule as A4, with
the lone-operator exception). The creator gets 409 on self-approval.

## API (`/api/v1/cases/{invoice_id}`)

| Method | Path | Effect |
|---|---|---|
| POST | `/schedules` | Create a `proposed` schedule (admin). Legs: `due_date` + positive `amount_cents`; optional `terms`, `promise_id` (must belong to the same invoice). |
| GET | `/schedules` | List the invoice's schedules with legs and computed flags. |
| GET | `/schedules/{id}` | One schedule: totals, paid/remaining, leg views. |
| POST | `/schedules/{id}/approve` | `proposed → active` (second admin). |
| POST | `/schedules/{id}/cancel` | Cancel a proposed/active schedule; paid legs keep their status, open legs become `cancelled`. |
| POST | `/schedules/{id}/legs/{leg_id}/reschedule` | Move a `pending` leg to a new due date via supersede; 409 on paid/partial/cancelled legs. |

Each view returns `total_cents` (live legs only), `paid_cents`,
`remaining_cents`, and per-leg `late`/`missed` flags next to the authoritative
ledger split from `split_balance` — the schedule and the ledger are shown
side by side, never merged.

## Audit

Creation, approval, cancellation, reschedule, completion and
reversal-reopen each write an `AuditEvent` with actor and schedule/leg ids.

## Tests

`tests/test_p2_b3_installments.py` (12 tests): create/approve + SoD block,
promise link (+ cross-invoice 404), oldest-first waterfall, full-pay
completion with ledger-owned closure, overpay residual, reversal reopen with
history preserved, reschedule/cancel statuses, late/missed flags, credit
non-application, idempotent apply, cross-schedule waterfall without double
count, cross-tenant 404s.
