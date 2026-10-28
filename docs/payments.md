# P1 payment allocation and promises (Milestone 3)

## Transfer allocation

One verified AFIS transfer can split across several invoices, and several
transfers can apply to one invoice, through `allocation_proposals` with
`allocation_legs` (migration `20261031_allocation_v5`). Scoring in
`app/services/allocation.py` is deterministic and explainable: invoice
reference, payer name or staff-approved alias, exact/partial/excess amount,
and date proximity each add stated reasons; missing references, unknown
payers, repeated amounts, and date differences are recorded as uncertainty.

- Candidates at or above 0.5 draft legs greedily, capped by the transfer.
  A proposal is `proposed` with one clear winner or several referenced
  invoices, else `ambiguous` — and ambiguous proposals require staff-chosen
  explicit legs at approval.
- Approval validates tenant, currency, positive amounts, residual cover, and
  current outstanding per leg, then posts each leg through the existing
  `post_entry` path (`allocated_transfer`). Nothing else moves the ledger.
- Residuals stay visible (`partially_applied`); proposals and approvals are
  idempotent; reversals keep legs as applied history and restore balances
  through the normal reversal path.
- AFIS transfers carry no tenant or currency of their own, so each proposal
  records both explicitly and legs can never cross them. Multi-tenant
  deployments need per-tenant AFIS files (future work).

## Promises

`promises_to_pay` rows are nonfinancial: promised amount, date, source
message, extraction confidence, staff confirmation, reminders, and
broken/kept status. Recording, confirming, or reminding never changes cash,
balances, or stages. Refresh runs on every posting: covering verified
payments mark kept, past-due uncovered promises mark broken. Razorpay stays
**SIMULATED**; no live payment path was added.
