# Frontend control and endpoint inventory

This inventory maps the staff dashboard in `frontend/` to the running FastAPI OpenAPI schema and `app/api/` route code as checked on 2026-10-24. All `/api/v1` requests use the existing `X-RECOVERFLOW-API-KEY` header. The middleware rejects unknown keys (401), missing server configuration (503), and every viewer write (403). “Staff” below means an authenticated non-viewer role; admin checks are listed separately. Webhooks are provider-only and have no dashboard control.

The common UI pattern is: the view shows loading text while a read is pending, an empty message for an empty collection, the server error text on failure, and refreshed records after a successful write. A control's returned object or count is used only after the API succeeds. Some older write controls still use a browser alert for errors or completion; this is a remaining UX limitation.

| Area / control | Request and body | Response used | Permission | UI states |
| --- | --- | --- | --- | --- |
| Connect / Forget key | GET `/reports/summary`; key kept in session storage, Forget clears it | DSO, pending reconciliations, alerts | Authenticated read | Connected/error/forgotten |
| Overview queue and activity | GET `/cases`, then GET `/cases/{id}` for first three activity files | Authoritative balance, ledger entries, customer messages | Authenticated read | Loading/empty/error/rows |
| Import CSV | POST `/imports/receivables/csv`, raw UTF-8 CSV | Imported and skipped counts | Staff | Importing/error/counts |
| Upload PDF | POST `/invoices/upload?invoice_type=AR\|AP`, raw PDF | Job ID | Staff | Uploading/error/queued |
| Poll or retry PDF job | GET `/invoices/jobs/{id}`; POST `/invoices/jobs/{id}/retry` | Status, invoice ID, error | Read / staff retry | Queued/processing/failed/retry |
| Manual receivable | POST `/invoices/manual`, invoice fields from form | Created invoice ID | Staff | Error/saved |
| Review extracted invoice | GET `/invoices/?status=pending_review`; PUT `/invoices/{id}/review`, edited invoice fields | Queue and confirmed record | Read / staff confirm | Loading/empty/error/refreshed |
| Case search / open | GET `/cases`; GET `/cases/{id}` | Case summary, evidence, ledger, messages, drafts, notes | Authenticated read | Loading/empty/error/case file |
| Record payment or credit | POST `/cases/{id}/entries`, kind, amount, reference | Ledger entry; refreshed case | Staff | Error/success/updated balance |
| Reverse ledger entry | POST `/cases/{id}/entries/{entry}/reverse`, reason | Reversal; refreshed case | Admin | Prompt/error/updated balance |
| Record customer reply | POST `/cases/{id}/replies`, category, body | Message and policy classification | Staff | Error/success/blocked injection |
| Resume contact | POST `/cases/{id}/resume`, reason and consent flag | Case state | Admin | Hidden unless paused/error/resumed |
| Confirm Shopify case | POST `/sync/shopify/cases/{id}/confirm`, reason and due-date flag | Case state | Admin | Hidden unless review needed/error/confirmed |
| Create payment link | POST `/payments/links`, invoice ID and idempotency UUID | Link status and provider ID | Staff | Disabled if ineligible/error/SIMULATED link |
| Reconciliation queue / approve | GET `/reconciliation/pending`; POST `/reconciliation/{id}/approve` | Matches; posted result | Read / staff approve | Loading/empty/error/refreshed |
| Create collection draft | POST `/dunning/trigger-stage`, invoice ID and stage query | Draft | Staff | Error/draft created, no send |
| Collection list | GET `/dunning/campaigns` | Draft text, stage, status | Authenticated read | Loading/empty/error/table |
| Edit / approve / refresh draft | PUT `/dunning/campaigns/{id}`, subject and body; POST `/{id}/approve`; POST `/{id}/refresh` | Updated campaign | Staff | Error/refreshed draft |
| Record contact | POST `/dunning/campaigns/{id}/record-contact`, channel and reference | Contact record | Staff | Error/refreshed campaign |
| Provider status | GET `/integrations/status` | Configured status and simulator mode | Authenticated read | Loading/error/provider labels |
| Shopify read-only sync | POST `/sync/shopify` | Imported, unchanged, review, skipped counts | Staff | Disabled if unconfigured/error/counts |
| Draft schedule | GET / PUT `/policies/collection`, enabled, timezone, run hour, stage days | Saved schedule | Read / admin save | Loading/error/saved |
| Payment links list / cancel / recover | GET `/payments/links`; POST `/payments/links/{id}/cancel` or `/recover` | Link list and state | Read / admin actions | Loading/empty/error/refreshed |
| WhatsApp inbox / triage / reply | GET `/messages/inbox`; POST `/messages/{id}/triage`, case ID and category; POST `/messages/{id}/reply`, body and idempotency UUID | Inbox status | Read / staff actions | Loading/empty/error/refreshed; provider setup applies |
| Provider review events | GET `/integrations/events`; POST `/integrations/events/{id}/resolve`, reason | Review events | Read / admin resolve | Loading/empty/error/refreshed |
| Agent status and policy | GET `/agent/status`; PUT `/agent/policy`, enabled and limits | Policy, model/rate-limit status | Read / admin save | Loading/error/saved |
| Assess a case | POST `/agent/cases/{id}/assess` | Proposal action and engine | Staff | Assessing/error/proposal ID |
| Proposal list and versions | GET `/agent/proposals`; GET `/agent/proposals/{id}/versions`; GET `/cases` for current balance | Proposal, risk flags, version hash/status | Authenticated read | Loading/empty/error/stale balance |
| Internal note / collection draft | POST `/agent/proposals/{id}/internal/case_note` or `/collection_draft` | Execution record | Staff, policy bounded | Error/refreshed proposal |
| Reject proposal | POST `/agent/proposals/{id}/reject`, reason | Rejected proposal | Staff | Prompt/error/refreshed |
| Edit proposal draft | POST `/agent/proposals/{id}/edit-draft`, body and change reason | New immutable version | Staff | Error/new version/hash |
| Approve exact draft | POST `/agent/proposals/{id}/approve`, version number and hash | Approval record | Staff | Disabled if current undisputed is zero/error/approved |
| Reviewed reply | POST `/agent/proposals/{id}/send-reply`, body | Provider result | Staff and server policy | Explicit confirmation/error/result; not exercised in offline QA |
| Review alerts | GET `/fraud/alerts?status=open`; POST `/fraud/{id}/resolve?resolution=false_positive` | Alert list and resolution | Read / staff resolve | Loading/empty/error/refreshed |

The **SIMULATED payment completion** is intentionally not a staff button: `scripts/simulate_payment.py` posts a signed event to the provider webhook. The dashboard then refreshes `/cases/{id}` to show `PARTIALLY_RESOLVED`. Shopify is read-only; provider status does not imply a live send or real payment. Backend tests cover route authorization and safety; browser QA of provider-backed paths requires configured sandbox accounts and was not attempted here.

The seeded invoice and purchase-order references open their bundled local PDF copies from `frontend/evidence/`. Other source references remain evidence identifiers and snippets; the UI does not imply that every provider document is downloadable.
