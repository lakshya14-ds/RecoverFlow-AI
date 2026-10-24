# RecoverFlow AI

RecoverFlow prepares evidence-linked receivables cases for Indian MSME teams. It separates disputed from undisputed balances, drafts a request for the undisputed amount, and lets staff approve the exact message version. Payments in this demo are **SIMULATED**; WhatsApp and email go to sandbox outboxes only.

## Run the offline demo

Use Python 3.11 or 3.12 with the pinned dependencies from the repository root:

```bash
python -m pip install -r requirements.txt
python scripts/demo_hero.py
```

The script uses a fresh temporary database and synthetic CSV/PDF files. It uploads them through the actual intake API, shows the ₹2,40,000 invoice, ₹1,50,000 received, ₹90,000 outstanding, ₹30,000 disputed and ₹60,000 undisputed; approves an edited draft; runs Manual and Delegate negotiation against a SIMULATED customer; rejects an injection attempt; and posts a SIMULATED ₹60,000 payment. The case becomes `PARTIALLY_RESOLVED`, leaving ₹30,000 disputed. No internet or API key is needed. It runs the measured evaluation and writes [docs/evaluation.md](docs/evaluation.md).

## Run the three-page app

Copy `.env.example` to `.env`, set a local `RECOVERFLOW_API_KEY`, then run:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8002
```

Open `http://127.0.0.1:8002`, enter the staff API key, and use **Intake**, **Review and Negotiate**, or **Control**. Intake accepts CSV, PDF, JPEG and PNG; it validates type and size and queues files in SQLite. Source-linked claims, extraction confidence, versioned drafts, per-case mode and transcript appear in Review. Control shows policy, quota slot status, sandbox activity, ledger and audit. Staff confirm invoice extraction and receipts before ledger posting. Scanned images need Gemini; without it they are marked **Needs attention**. The offline parser accepts only explicitly tagged synthetic demo PDFs.

## Model and safety boundaries

`GEMINI_API_KEY_1` serves intake, `_2` investigation/drafting/co-pilot, `_3` negotiation/intent. Co-pilot and customer-intent classification use their assigned slots when available; deterministic policy remains authoritative. Each slot has a 15 RPM, 1,500 RPD client limit and failover; Key 3 reserves headroom for conversation. Independent provider quotas require keys from **three separate Google Cloud projects**. `GEMINI_ROLE_MAP_JSON` can override role assignments. The legacy `GEMINI_API_KEY` is a final fallback. Model: `gemini-3.6-flash`; if unavailable, rules continue and unsupported documents go to staff review.

Server rules use fixed cents and `Decimal` for balances, offers and policy checks. The model may extract, classify or phrase; it cannot change ledger amounts. Uploads and customer text are untrusted. The agent cannot post payments, issue write-offs, waive disputes or send live messages. Promises never close cases. Shopify remains read-only. Production identity, database migrations, live providers and observability remain future work.

## Verify and inspect

```bash
python -m pytest -q
node --check frontend/app.js
python scripts/run_evaluation.py
```

The evaluation uses 30 synthetic accounting/policy cases plus ten real upload/pipeline trials and reports failures and limits. See [frontend endpoint inventory](docs/frontend-endpoint-inventory.md), [Release 2 provider guide](docs/release2-connected-recovery.md), and [agent handoff](.codex/handoff.md).
