# RecoverFlow AI

RecoverFlow is a local receivables workbench for teams handling overdue invoices, partial payments, and disputes. It links invoice, purchase order, receipt, and customer-message evidence to a case; calculates the outstanding balance; separates the disputed portion from the amount that can be requested; and prepares a collection message for staff review. Server-side rules control money and actions. Meta's Muse Spark can assist with document extraction, classification, and wording when configured.

**Demo boundary:** All example documents and customers are synthetic. Razorpay payments in the demo are **SIMULATED**. Outbound WhatsApp and email messages are placed in local sandbox outboxes; the demo does not send them to customers.

## What it does

| Area | Available workflow |
| --- | --- |
| Intake | Upload CSV, PDF, JPEG, or PNG files (up to 10 MB each). A SQLite-backed worker tracks extraction, validation, confidence, and items needing staff attention. Staff confirm extracted invoices and receipts before they affect the ledger. |
| Case review | See invoice total, cash received, credits, outstanding, disputed, and undisputed amounts, with source links and an audit trail. Staff choose how each receipt or credit is allocated. Invoice, purchase order, delivery, return, scheme, and message claims can be investigated; conflicting evidence pauses contact for staff review. Each claim carries a trust state (alleged, extracted, verified, accepted, rejected) with decider and reason; see the staff-reconciliation procedure in the foundation notes. |
| Collection drafts | Prepare a request for the undisputed balance only. Staff can edit or reject it; each edit creates a new version, and approval is tied to the exact version. |
| Negotiation | Choose Manual or Delegate mode per case, inspect a sandbox transcript, use co-pilot suggestions, and pause, take over, or stop. Server rules bound offers and block waivers or misstated balances. English, Hindi, and Hinglish drafts are validated before wording, after wording, and at exact-version approval. |
| Multi-agent workflow | A deterministic supervisor queues bounded intake, investigation, reconciliation, resolution, communication, and verification tasks with retries, budgets, and crash recovery. Specialists read through a tool allowlist; nothing posts, approves, waives, or sends except staff-gated paths. One transfer can split across invoices and several transfers can match one invoice; ambiguous matches wait for staff, and promises stay nonfinancial. |
| Owner queue and import | Control shows the next action per case (reason, owner, deadline, amount, uncertainty, approval) plus agent activity. A provider-neutral import adapter previews and confirms `generic_csv` receivables; no vendor format is claimed without a sanitized export. |
| Payment and control | Match verified ledger entries to cases; a payment can leave the disputed amount open as `PARTIALLY_RESOLVED`. Control shows policy, model-slot status, sandbox activity, ledger, audit, and synthetic evaluation results. |

Incoming customer text is treated as evidence, including attempted instructions to cancel an invoice. A promise to pay or an approved message does not close a case. Shopify integration is read-only and requires staff confirmation of imported balances. Injection checks and outbound wording checks are defense layers, not a proof of immunity against every language or encoding.

## Architecture and workflow

```mermaid
flowchart LR
    A["CSV, PDF, or image"] --> B["FastAPI intake"]
    B --> C[("SQLite jobs and case data")]
    C --> D["In-process extraction and matching"]
    M["Muse Spark, when configured"] -.-> D
    D --> E["Evidence-linked case and split balance"]
    E --> A["Deterministic supervisor + specialists"]
    A --> F["Validated draft for undisputed amount"]
    M -.-> F
    F --> G["Staff edit, approve, or reject"]
    G -->|approved message| H["Local sandbox outbox"]
    P["Confirmed receipt or SIMULATED payment"] --> L["Server-verified ledger entry"]
    L --> E
    E --> S["Case status and audit trail"]
```

Only a posted receipt or credit changes the open receivable. Cash received and credit adjustments are reported separately; drafting, approval, and sandbox messages change neither.

## Quick start: offline demo

Use Python 3.11 or 3.12. From the repository root, create an environment and install the pinned dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/demo_hero.py
```

On macOS or Linux, activate with `source .venv/bin/activate` instead. The demo needs no API key or internet after dependencies are installed. It uses a temporary database and generated documents, then runs intake, evidence review, a versioned draft approval, both negotiation modes, an injection check, and a **SIMULATED** payment. The example invoice is ₹2,40,000: ₹1,50,000 received, ₹90,000 outstanding, ₹30,000 disputed, and ₹60,000 undisputed. After the simulated ₹60,000 payment, the case is `PARTIALLY_RESOLVED` with ₹30,000 still disputed. The script also refreshes [the synthetic evaluation report](docs/evaluation.md).

For the multi-agent story, run `python scripts/demo_p1_showcase.py`: a Hinglish short-supply claim, conflicting explanations, an ambiguous payment held for staff, a targeted clarification, an invalidated draft, an approved exact message, and a **SIMULATED** payment with an open dispute left. See the [showcase walkthrough](docs/showcase-walkthrough.md). The showcase prints and asserts each beat and writes no files.

## Run the web app

For a hosted pilot, follow the [Vercel deployment guide](docs/vercel-deployment.md). Vercel serves the frontend; the API and workers need a persistent Python host.

1. Copy `.env.example` to `.env` (`Copy-Item .env.example .env` in PowerShell, or `cp .env.example .env` on macOS/Linux). Replace `RECOVERFLOW_API_KEY` with a long, private local key. Optionally set `APEX_DB_PATH=recoverflow-local.db` to keep this run in a separate SQLite database. Do not commit `.env`.
2. Seed the example case if you want data immediately: `python scripts/seed_hero_case.py`. This reseeds the example invoice if it already exists in the selected database.
3. Start the server: `python run.py`. Open [http://127.0.0.1:8002](http://127.0.0.1:8002), enter the same staff key, and use **Intake**, **Review and Negotiate**, and **Control**. The API health check is at `/api/v1/system/health`; interactive API documentation is at `/docs`.

The server creates the local database and runs the intake worker in process. The offline parser handles tagged demo PDFs and text PDFs with explicit invoice, purchase-order, or receipt labels whose totals reconcile; staff still confirm extracted invoices and receipts. Scanned images and unrecognized PDFs need Meta extraction or staff review. Optional Meta configuration uses `META_API_KEY_1`, `_2`, and `_3` for intake, investigation/drafting, and negotiation, respectively, with rules fallback when unavailable. The configured model is `muse-spark-1.3` via the Meta Model API (`https://api.meta.ai/v1`), with client limits of 15 requests/minute and 1,500/day per slot. Restart the server after adding or changing `.env`.

## Verify and learn more

Run `python -m pytest -q` for the test suite, `node --check frontend/app.js` for JavaScript syntax, and `python scripts/run_evaluation.py` to regenerate the synthetic evaluation. The evaluation reports 30 accounting/policy cases and ten generated upload trials; it does not measure real-world recovery or live document accuracy. `python scripts/run_p1_evaluation.py` compares rules-only, single-agent, and specialist workflow on 38 held-out and adversarial synthetic cases with fixed seeds; see [the P1 report](docs/p1-evaluation.md) for method, uncertainty, failures, and limits. Scores are computed at run time, never hard-coded.

The backend is FastAPI with SQLAlchemy and SQLite by default; the frontend is served from `frontend/`. Monetary database fields use exact decimal storage; the receivables ledger stores signed adjustments and their dispute allocations. It is **not** a double-entry general ledger. Startup runs a versioned SQLite schema upgrade for older installations; back up an existing database before upgrading. A PostgreSQL migration path exists but has not been exercised against a live PostgreSQL server in this run. "AXIS" is a local database reader with tax classification fields, not a bank integration. See the [architecture](docs/architecture.md), [foundation repair notes](docs/foundations-2026-10-27.md), [endpoint inventory](docs/frontend-endpoint-inventory.md), [evaluation method and limits](docs/evaluation.md), [P1 evaluation](docs/p1-evaluation.md), [supervisor](docs/supervisor.md), [investigation](docs/investigation.md), [payments](docs/payments.md), [communication](docs/communication.md), [import adapter](docs/import-adapter.md), [connected-provider guide](docs/release2-connected-recovery.md), and [controlled-agent guide](docs/release3-controlled-agent.md). Local API keys, database-backed users, and roles are implemented, but production identity, backups, monitoring, and real provider validation require further work.
