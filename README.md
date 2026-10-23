# RecoverFlow — Release 1 assisted collections

RecoverFlow is a local, English-language prototype for retailers with invoiced or credit-term receivables. It imports receivables, tracks balances and customer replies, prepares collection drafts for staff review, and records confirmed payments. It is an **assisted** workflow: no external accounting, payment, or inbound messaging provider is configured, and no collection message is sent automatically.

## What works

| Area | Current behavior |
| --- | --- |
| Retail receivables | Import UTF-8 CSV records with stable external IDs, or create an AR invoice manually. Reimporting identical records skips them; conflicts are rejected. |
| PDF invoices | Upload AP or AR PDFs into a database-backed processing queue. Run a separate worker to process them. Extracted AR invoices require staff confirmation before collection. OCR requires Tesseract, Poppler, `pdf2image`, and `pytesseract`. |
| Balances | New invoices store an opening amount in integer cents. Immutable payment, credit, and reversal entries update the outstanding balance. Existing floating-point amounts remain readable through a rounded legacy fallback. |
| Cases | Staff can inspect a receivable balance and history, record payments or customer replies, and pause contact for disputes, paid claims, or opt-outs. An admin must document a reason before resuming; opt-outs also require confirmation that contact permission was restored. |
| Reconciliation | Human approval of an AFIS match records an AR payment; an AFIS transaction cannot be approved for a second invoice in the same tenant. |
| Collections | Drafts use conservative templates and the current outstanding balance. Staff can edit, refresh, and approve a draft, then record contact made through their own email or phone system. API sending additionally requires configured SMTP, dry run disabled, an eligible case, an unchanged balance, and the contact cooldown to have elapsed. |
| Reporting | AR aging uses current balances. The worker stores a daily invoice-based DSO estimate when there are recent AR invoices; forecasting still requires at least 30 snapshots. |
| Access | API keys identify an actor, tenant, and basic role. Data routes are tenant scoped; viewer keys cannot write. Audit events record important staff actions. |

The active LangGraph path performs OCR, duplicate and amount-anomaly checks, candidate payment matching, and deterministic review routing. The amount-anomaly model uses only invoice amount and should not be interpreted as a fraud determination. Collection drafts currently use offline templates; the LLM client and CFO prototype are not part of the Release 1 decision path.

See [the current architecture](docs/architecture.md) for the workflow and the status of older diagrams.

## Local setup

Use Python 3.11+, install `requirements.txt`, and copy `.env.example` to `.env`. Set a long `RECOVERFLOW_API_KEY` and review the paths for Tesseract and AFIS. To process PDF invoices, install the Tesseract executable and Poppler utilities on this machine. CSV import and manual entry do not need them.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```

In a second terminal, start the durable local worker:

```powershell
python -m app.worker
```

`python -m app.worker --once` claims at most one job and refreshes today's DSO snapshot. The API only queues PDFs; a stopped worker leaves them queued. After a crash, an expired processing lease can be claimed again. Failed jobs without an invoice can be retried through the API or dashboard.

Open `http://127.0.0.1:8002` and enter the configured API key. The health endpoint is public at `/api/v1/system/health`. Data requests use `X-RECOVERFLOW-API-KEY`.

## Retail CSV format

Use the **Invoices → Import Retail Receivables** form or POST raw `text/csv` to `/api/v1/imports/receivables/csv`. Required headers are `external_id,invoice_number,customer_name,issue_date,due_date,amount`. Optional headers are `customer_email,currency`. Dates use `YYYY-MM-DD`; amount has at most two decimal places. The default currency is USD. Each file may contain up to 500 records.

```csv
external_id,invoice_number,customer_name,customer_email,issue_date,due_date,amount,currency
sale-001,INV-001,Example Customer,customer@example.com,2026-10-01,2026-10-15,125.50,USD
```

## Staff workflow

1. Import AR balances, create them manually, or upload a PDF as **Receivable (AR)**.
2. If a PDF produces a review record, confirm or correct its fields under **Invoices Awaiting Review**. A PDF with missing required fields can be retried or entered manually.
3. Open **Cases** to verify the balance and record receipts, credits, or customer replies. Use a unique receipt reference for each balance entry.
4. For an overdue open case, create a collection draft. Check and approve the text under **Collections**. If the balance changes, refresh and approve it again.
5. Contact the customer through your existing channel and record the manual contact. Only after SMTP configuration and an explicit send call can RecoverFlow deliver an approved email. Dry run is enabled by default. An opt-out, dispute, paid claim, paid balance, or active cooldown blocks contact.

## Limits and next release

This is a local assisted release, not a production autonomous collections agent. Payment, accounting, and inbound messaging routes still return 503 until real providers are selected. No customer portal, automated outreach schedule, external payment verification, advanced fraud model, or jurisdiction-specific contact policy is included. Before real outreach, the retailer must approve templates and contact rules for its customers and location. Use a production database, stronger user identity, backups, monitoring, and a supervised provider integration before multi-user deployment.

Run tests with `python -m pytest -q`. Legacy APEX environment variables, API header, and database table names remain supported for existing installations.
