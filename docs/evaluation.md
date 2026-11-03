# Synthetic evaluation — 2026-11-03

Run with `python scripts/run_evaluation.py`. All cases, documents, and payments are synthetic. No provider or customer was contacted.

## Model suite under test

RecoverFlow runs on the Meta AI suite with a deterministic offline fallback:

- **Meta Muse Spark 1.3** (`muse-spark-1.3`) — executive reasoning, wording, and text classification.
- **Meta SAM 3.1** (`sam-3.1`) — document perception and visual evidence segmentation.
- **Meta Muse Voice** (`muse-voice-transcribe`) — audio transcription for voice notes and calls.
- **Deterministic rules fallback** — offline execution when no Meta model key is configured; server rules choose actions and do all money math.

No fake Meta response is used in this run. Model-dependent extraction steps fall back to deterministic rules or staff review.

## Thirty case accounting and policy check

| Measure | Simple full-balance baseline | RecoverFlow |
| --- | ---: | ---: |
| Correct outstanding split | 25/30 | 30/30 |
| Correct dispute flag | 25/30 | 30/30 |
| Unsupported disputed-balance demands | 5 | 0 |
| Policy violations under the defined synthetic policies | 10 | 0 |

The test supplies **verified dispute amounts** to the ledger, then calls the real `split_balance`, `post_entry`, injection detector and outbound guard. The dispute-flag score measures handling of that supplied flag; it does **not** measure discovery from raw documents. The baseline always demands the full outstanding balance and has no injection check. Both methods tie on ordinary payment cases. Counts describe behavior under these synthetic policies, not real customer-facing sends or recovery outcomes.

## Ten actual upload and pipeline trials, offline

The runner generates three CSVs, five text PDFs, one PNG and one JPEG, sends them through the upload endpoint, runs the DB worker and reads the tracker. Tagged synthetic PDFs use a narrow offline parser. Ordinary PDFs and images require Meta or staff review. No fake Meta response is used in this run.

- Correct Review/Needs attention routing: **10/10**.
- Reached Review without human data entry: **5/10 (50%)**.
- Image extraction reaching Review offline: **0/2**.

| Synthetic file | Observed route | Reason |
| --- | --- | --- |
| good-one.csv | Review | accepted |
| good-two.csv | Review | accepted |
| bad-columns.csv | Needs attention | CSV is missing required columns: amount, customer_name, due_date, external_id, invoice_number, issue_date |
| invoice-2.pdf | Review | accepted |
| invoice-3.pdf | Review | accepted |
| invoice-4.pdf | Review | accepted |
| bad-total.pdf | Needs attention | Extracted line amounts do not reconcile to invoice total |
| unmatched-receipt.pdf | Needs attention | Document invoice reference has no unique match |
| receipt.png | Needs attention | Meta unavailable; rules fallback requires staff review |
| receipt.jpg | Needs attention | Meta unavailable; rules fallback requires staff review |

Limits: ten generated files are not a representative document sample. The fallback only recognizes tagged synthetic PDFs. Meta PDF/image extraction has separate stubbed-client tests; live accuracy was not measured. Staff still confirm uploaded invoices and receipts before ledger posting or automatic sandbox send.
