# Unit economics (F3)

`GET /api/v1/system/economics?period_days=30` (admin-only) reports what
one business costs to run on RecoverFlow. The report has three sections
that must never be mixed:

- **measured** — counts from this tenant's rows over the trailing
  window: supervisor model calls + latency, outbound messages by
  status, posted payments (count, volume per currency, reversals),
  live stored bytes (documents + intake uploads), cases with tasks.
- **assumptions** — unit prices from tenant settings
  (`PUT /api/v1/integrations/settings`), each tagged with its source:
  `tenant_setting`, `global_setting`, or `default`. Every default is
  zero, so an unpriced report totals zero and says why under pending
  instead of inventing costs.
- **computed** — measured x assumptions: six cost lines, total,
  per-case (total / cases with tasks, null when zero), per-business
  (equals total; the report is single-tenant), and a sensitivity band
  that scales variable lines ±20% while infra/support stay fixed.

## Setting prices

| Setting | Meaning | Where the number comes from |
|---|---|---|
| `cost_currency` | reporting currency (default INR) | operator choice |
| `cost_per_1k_model_calls` | per 1000 supervisor model calls | Meta provider invoice |
| `cost_per_outbound_msg` | per outbound message, any channel | WhatsApp/provider tariff |
| `cost_payment_fee_pct` / `cost_payment_fee_flat` | gateway take on reporting-currency volume | gateway statement |
| `cost_per_gb_month_storage` | per GB-month of live bytes | hosting bill |
| `cost_monthly_infra` / `cost_monthly_support` | fixed 30-day costs, prorated | operator books |

## Honesty rules

- Gateway fees apply to reporting-currency volume only. Other
  currencies are listed under `pending`, never converted silently.
- Gross payment volume is the negation of signed payment ledger entries:
  a receipt reduces receivables but contributes positive collected volume.
  Credit notes are excluded. Reversals are counted separately rather than
  assumed to earn fee refunds.
- Soft-deleted document bytes are excluded from storage; holds stay.
- `model_calls` covers supervisor specialist tasks only. Intake/vision
  extraction calls are not instrumented yet — the report says so under
  `pending` rather than undercounting quietly.
- Willingness to pay is always pending: it needs F2 pilot interviews,
  never a guess. No price or market claim leaves this repo without
  that evidence.
- Reversals are counted in measured but excluded from fee math (fee
  credits vary by gateway; the statement, not the code, decides).
