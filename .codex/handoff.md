# RecoverFlow agent handoff

Shared by Codex and Antigravity. Read `.codex/prompt.md` first. Update this file after every meaningful iteration; re-read it immediately before writing so another agent's entry is preserved. Do not add secrets or customer data.

## Current state

- **Two-minute live demo script (2026-10-24):** Updated `docs/RecoverFlow_Demo_Video_Script.docx` from the supplied Downloads copy for the currently running port 8018 app. It has seven shots ending at 2:00 and 155 spoken words. Off-camera setup prepares Case 1's controlled-agent draft; the on-camera flow covers Intake, the hero balance, evidence, versioned approval, simulated injection, SIMULATED payment, and Control. The original Downloads file was not overwritten. DOCX package/text checks passed; rendered page QA remains unavailable because the bundled renderer cannot find LibreOffice on this host.

- **GitHub-to-Vercel handoff (2026-10-24):** `vercel.json` now skips package installation and builds the static frontend from the repository root. `docs/vercel-deployment.md` gives exact GitHub import fields and a Vercel/backend environment-variable matrix. Only `RECOVERFLOW_BACKEND_URL` is set on Vercel; private staff/model/provider keys remain on the persistent backend. No changes were pushed or deployed.

- **PDF intake repair (2026-10-24):** Port 8018 now serves the isolated final-QA database from Python process 49988. The newly added ignored `.env` loads three configured Gemini slots; local network restrictions prevented a live provider check. A conservative text-PDF parser extracted both invoice uploads, the purchase order, and the SIMULATED receipt offline. The receipt remains matched but awaits staff confirmation before ledger posting. An identical invoice retry is marked already imported without a second case. Browser Intake shows 5 processed files, 2 cases created, 1 item awaiting staff review, and no console errors. Full suite passes 69/69.

- **Vercel preparation (2026-10-24):** Static frontend build, configurable HTTPS backend origin, exact-origin CORS, configurable durable file paths, and safe optional admin bootstrap are implemented. Vercel will serve the UI while a persistent Python host runs FastAPI and both workers. No remote deployment was performed; no backend URL or Vercel account is configured. The guide is `docs/vercel-deployment.md`.

- **Hackathon pitch (2026-10-24):** Created a 12-slide PowerPoint at `output/presentation/RecoverFlow-Hackathon-Pitch-v3.pptx` from repository facts and real screenshots of a separate local seeded app on port 8012. The offline hero demo passed in this checkout. The deck covers the problem, full workflow, features, all five judging criteria, synthetic evaluation and production limits. Presentation package, layout and first-party import checks passed. No application source was changed for the pitch.

- **Final local QA (2026-10-24):** Isolated localhost app is serving `http://127.0.0.1:8018` from Python process 27700 with ignored SQLite `recoverflow-final-qa.db`. It has the seeded synthetic hero case and three newly generated PDF upload jobs. Local API authentication is configured only in that process; no credential was written to this handoff. All 66 tests passed, the offline hero demo completed, and browser checks found no console errors or global overflow at 390 px. Ordinary generated PDFs require staff review without Gemini; the tagged offline synthetic PDFs completed the full flow. Port 8002 belongs to a separate existing server and was left alone.

- **Latest synthetic PDF QA (2026-10-24):** The app is serving http://127.0.0.1:8002 from Uvicorn process 5916 on ignored SQLite recoverflow-release4-fresh.db. A second synthetic case was created from generated invoice, purchase order and SIMULATED receipt PDFs. Live vision extraction, source links, review, negotiation and signed SIMULATED payment were verified. The case is PARTIALLY_RESOLVED with only the INR 2,000 dispute open. Full suite passes 66/66. This entry supersedes older process, case-count and test-count statements below. Keys remain in ignored .env.

- **Release 4 local run (2026-10-24):** The current checkout is serving `http://127.0.0.1:8002` from Uvicorn process 17988. It uses a newly created ignored SQLite database at `C:\Users\Samit Reddy\Documents\GitHub\RecoverFlow-AI\recoverflow-release4-fresh.db`, with one synthetic hero invoice, one admin user, and five evidence records. The staff API key and Gemini keys remain in ignored `.env`; do not copy them into handoff. The older `14a2dff` detached worktree is separate; its prior port 8017 was unavailable at this task's start.
- **Release 4 amendment (2026-10-24):** The user explicitly allows three role-assigned Gemini slots, an in-process database-backed upload queue, PDF/image vision extraction, three frontend pages, and per-case Manual/Delegate negotiation. Razorpay remains SIMULATED, outbound WhatsApp/email remains sandbox only, and the remaining boundaries in `.codex/prompt.md` stay in force.
- **Release 4 current implementation:** Three local Gemini slots are configured in ignored `.env`; slot 1 returned HTTP 429 and slots 2/3 HTTP 200 on a minimal `gemini-3.6-flash` check. Key routing, secure upload queue, CSV/vision extraction, deterministic matching/investigation, source-linked drafts, three-page UI, Manual/Delegate negotiation, autonomy controls, offline synthetic PDF rules fallback, ten-file intake evaluation, and one-command isolated demo are implemented. Co-pilot and simulated-customer intent classification now use assigned Key 2/3 when available, with deterministic escalation authoritative. Full suite passes 63/63 in an ignored Python 3.14 environment. Live image extraction accuracy and separate Google-project quota ownership remain unverified.
- **Project:** RecoverFlow in `APEX-main`; Releases 1–3 are implemented as a controlled local pilot. The root `README.md` is the full project guide. Release-specific behavior is in `docs/release2-connected-recovery.md` and `docs/release3-controlled-agent.md`. Comprehensive file-by-file architecture and implementation status is documented in `docs/PROJECT_ANALYSIS_AND_SYSTEM_STATE.md`.
- **Release 3 boundary:** Server rules choose actions. Gemini supplies wording when available. Automatic execution is limited to policy-bounded internal notes and unsent collection drafts. Customer replies require staff action; payment posting and Shopify writes are outside the agent's authority.
- **Model and rate limits:** Standardized on `gemini-3.6-flash` with client-side sliding window 15 RPM and 1,500 RPD (resetting at midnight Pacific Time) rate limiting and automatic rules fallback on 429/limits.
- **Provider status last checked:** Shopify test-store connection was reported and verified in prior Release 2 work. Razorpay's configured path is a mock simulator, verified with `scripts/simulate_payment.py`. WhatsApp is unconfigured. Local Gemini API key was verified against Google's API endpoint with rate limiter and structured output parsing in place.
- **Verification last completed:** On 2026-10-24, `python -m pytest -q --disable-warnings` passed 63 tests; `node --check frontend/app.js` and `git diff --check` passed. Synthetic live intent requests through Key 2 and Key 3 returned `haggling` on `gemini-3.6-flash`; Key 1 remains quota-limited from the earlier check. The offline Release 4 demo passed twice from a fresh source export using the preinstalled virtual environment; each run used a new temporary database, and passed again after model classification integration. The ten-file upload run routed 10/10 correctly and 5/10 reached Review without data entry; two images required review offline. Browser QA found no page errors or overflow across 1440/1280/768/390 widths, displayed PDF field confidence, and showed the generated evaluation summary on Control at 390 pixels.
- **Working tree:** Release 4 implementation, evaluation and demo changes are uncommitted and unpushed in this checkout. The older detached worktree run on port 8017 is separate.

## Open items

1. Connect and test real Razorpay and Meta WhatsApp accounts when user makes live production or sandbox keys available. Keep simulator clearly labelled until then.
2. For a production rollout, replace local pilot identity and SQLite storage with managed tenant credentials, PostgreSQL, database migrations (e.g. Alembic), automated backups, monitoring, and provider-specific operational tests. See `docs/PROJECT_ANALYSIS_AND_SYSTEM_STATE.md` for details.

## Iteration log

### 2026-10-24 — Antigravity — Full working tree verification, clean db untrack, and push

- **Objective:** Verify test suite and code integrity, remove tracked SQLite shared memory artifact from git cache, stage all implementation, deployment, presentation, and doc assets, commit with co-authorship, and push master branch to GitHub.
- **Changed:** Untracked `apex_ar.db-shm` from git tracking while retaining local file; staged all Release 4 & Vercel deployment assets (`vercel.json`, `.vercelignore`, `scripts/build_vercel_frontend.mjs`, `frontend/config.js`, `docs/vercel-deployment.md`), presentation assets (`output/presentation/RecoverFlow-Hackathon-Pitch-v3.pptx`, `output/pitch-build/`, `.codex/pitch-build/capture.mjs`), video script (`docs/RecoverFlow_Demo_Video_Script.docx`), synthetic QA PDFs (`output/pdf/final-qa-*.pdf`), and modified core/test files (`app/`, `frontend/`, `tests/`, `README.md`, `.gitignore`, `.env.example`).
- **Verification:** Ran `py -3.12 -m pytest -q --disable-warnings` (69 passed, 0 failures in 24.35s); `node --check frontend/app.js` passed; `git diff --check` passed.
- **Limits / next:** Working tree synchronized with remote `origin/master`. Secrets and local `.env` remain untouched and untracked.

### 2026-10-24 — Codex — Two-minute script for live port 8018

- **Objective:** Edit the supplied demo video Word script to fit two minutes and match the current localhost application.
- **Changed:** Replaced the 2:30 narration and shot list in `docs/RecoverFlow_Demo_Video_Script.docx` with seven shots totaling 2:00; added off-camera preparation for the currently unprepared hero draft and correct port/key setup for the simulator. Kept the user's Downloads original intact. No app source or database state changed.
- **Verification:** Read the source DOCX and inspected the running Intake, Review and Negotiate, and Control screens plus read-only case/proposal APIs. Reopened the final DOCX: valid ZIP package, 25 paragraphs, seven timed headings, 155 spoken words, localhost URL present, old 2:30 timing absent. The document renderer was attempted on source and final files but failed before page creation because bundled LibreOffice `soffice.exe` is unavailable; page layout was not visually verified. App tests were not run for this documentation-only edit.
- **Limits / next:** Visually inspect the Word pages in an environment with LibreOffice or Word before recording. The local demo case must be prepared off camera, and the payment simulator terminal must use the same staff key as the port 8018 server. Keep all payment and customer-reply footage explicitly SIMULATED.

### 2026-10-24 — Codex — Text-PDF intake repair after env addition

- **Objective:** Resolve the failed PDF upload tracker rows on the isolated localhost app after the user added `.env`.
- **Changed:** Added conservative text-layer extraction and reconciliation for explicitly labelled invoices, purchase orders and receipts in `app/services/vision_extraction.py`; made connection failures actionable and exact duplicate invoice retries idempotent in `app/services/intake_pipeline.py`; clarified receipt review in `frontend/app.js`; isolated auth tests from existing databases; added focused extraction/duplicate tests; updated `README.md` and this handoff. Restarted port 8018 against the existing isolated DB and retried the four displayed uploads.
- **Verification:** 69/69 pytest tests passed; `node --check frontend/app.js` and `git diff --check` passed. Both invoices and the PO now show Ready for review; the exact duplicate invoice shows Already imported → Ready for review. The SIMULATED receipt extracted and matched but remains Needs attention for staff confirmation before posting. Browser showed 5 processed files, 2 cases, 1 staff review item, and no console errors. Health and authenticated API remained HTTP 200.
- **Limits / next:** The new `.env` has configured Gemini slots, but a local Gemini request failed at socket connect because this execution environment blocks outbound access. Automatic approval review rejected an unsandboxed live request because sending the full synthetic invoice PDF plus API key to Gemini was not explicitly authorized. No live Gemini accuracy or quota claim is made. Staff should inspect the matched receipt before confirming it; real scanned/unrecognized PDFs still need approved provider access or manual review. No keys or uploaded customer data were written to shared notes.

### 2026-10-24 — Codex — Demo video Word script

- **Objective:** Deliver the requested 2.5-minute MVP demo narration and page-by-page screen directions as a Word document.
- **Changed:** Added `docs/RecoverFlow_Demo_Video_Script.docx` with preparation steps, seven timed shots, narration, and explicit SIMULATED payment and sandbox boundaries. No application source changed.
- **Verification:** Opened the DOCX with the bundled Python document library; its ZIP package is valid, all seven timed scenes are present, and the final 2:30 mark and SIMULATED label are included. Attempted the required DOCX render, but the packaged renderer could not find LibreOffice on this host; Word COM was also unavailable, so page-image layout verification was not possible. Tests were not run for this document-only change.
- **Limits / next:** Visually inspect the Word pages on a host with a DOCX renderer before recording. Use a fresh seeded database and the matching server port for the payment simulator.

### 2026-10-24 — Codex — Hackathon presentation

- **Objective:** Produce a judge-ready PPTX with an accurate problem statement, workflow, features, judging criteria and screenshots from the running project.
- **Changed:** Added the final 12-slide deck under `output/presentation/`, screenshots and authoring files under `output/pitch-build/`, and a temporary capture script under `.codex/pitch-build/`. Used a separate ignored seeded demo database. Did not change app code or credentials.
- **Verification:** `python scripts/demo_hero.py` passed, including source-linked balance, edited draft approval, sandbox negotiation, injection escalation, SIMULATED ₹60,000 payment and synthetic evaluation. Seeded local app on `127.0.0.1:8012`; Playwright captured genuine UI screenshots with no page errors. Rendered and visually reviewed all 12 slides. PPTX package integrity, layout and Artifact Tool import checks passed. Full pytest was not rerun for this presentation-only iteration.
- **Limits / next:** Numbers and documents in the deck are synthetic. ROI is a proposed pilot measurement, not a recovery claim. Live messaging and payment remain out of scope. Use the PPTX for the hackathon; run the offline demo alongside it.

### 2026-10-24 — Codex — Final synthetic PDF and localhost QA

- **Objective:** Recheck the project with freshly generated PDFs and leave an isolated localhost instance for user testing.
- **Changed:** Generated `output/pdf/final-qa-invoice.pdf`, `final-qa-purchase-order.pdf`, and `final-qa-simulated-receipt.pdf`; seeded ignored `recoverflow-final-qa.db`; started localhost port 8018. No application source changed. Existing pitch work and port 8002 were left untouched.
- **Verification:** `python -m pytest -q --disable-warnings` passed 66/66 (one existing warning); `node --check frontend/app.js` and `git diff --check` passed. `scripts/demo_hero.py` completed intake, source-linked split, exact-version approval, Manual/Delegate negotiation, injection escalation, SIMULATED payment to `PARTIALLY_RESOLVED`, and evaluation (30/30 split, 10/10 triage, 5/10 ready without entry). Generated PDFs were parsed as one-page files and visually rendered. On port 8018, all three uploaded with HTTP 202 and retrieved byte-identical source files; without Gemini they correctly entered Needs attention with no case creation. Browser showed the seeded case's five balance figures and evidence, no console warnings/errors, and no global overflow at 390 px. Health, UI assets and authenticated cases returned HTTP 200.
- **Limits / next:** Live Gemini/vision and real provider calls were not exercised because this isolated run has no provider keys. Python Playwright failed at driver startup under filesystem restrictions; the Codex in-app browser was used for UI checks. The seeded hero case remains open for manual user testing; payments and outbound messages remain simulated/sandboxed.

### 2026-10-24 — Codex — README workflow diagram

- **Objective:** Add the requested architecture/workflow diagram to the root README.
- **Changed:** Added a GitHub-renderable Mermaid flowchart to `README.md` covering intake, SQLite-backed processing, optional Gemini assistance, evidence-linked balance review, staff approval, sandbox messaging, and the separate confirmed-receipt/SIMULATED-payment ledger path.
- **Verification:** Checked diagram relationships against the current API, intake worker, draft and ledger code; `git diff --check` passed. Tests were not run for this documentation-only change; the previous local test attempt remains blocked by missing `pypdf` in that Python environment.
- **Limits / next:** The diagram describes the local pilot workflow. No provider calls or application behavior changed. An unrelated untracked `.codex/pitch-build/` directory was present and left untouched.

### 2026-10-24 — Codex — README project guide

- **Objective:** Rewrite the root README so a new contributor can understand RecoverFlow's features, run the offline demo and web app, and see the pilot boundaries without a license section or emojis.
- **Changed:** Updated `README.md` with a feature overview, Python environment setup, persistent local database and seed instructions, web UI/API entry points, optional Gemini behavior, verification commands, and links to detailed guides. No application source or credentials changed.
- **Verification:** Checked commands and feature descriptions against the current scripts, config, routes, frontend, and evaluation report; all README documentation links exist; `git diff --check` passed. A full pytest attempt on the current Python 3.12 environment stopped during collection because `pypdf` is not installed, so this iteration does not claim a passing test run. The previous 66/66 result above remains from the earlier configured environment.
- **Limits / next:** Install the pinned requirements in a clean environment before rerunning tests or the demo locally. Provider behavior and real document accuracy were not retested for this documentation-only change.

### 2026-10-24 — Codex — Generated invoice PDF and end-to-end QA

- **Objective:** Create an original example invoice PDF and test the running backend, database and UI through the full synthetic case flow.
- **Changed:** Added scripts/generate_example_invoice.py and three one-page synthetic PDFs under output/pdf/ (invoice, PO and SIMULATED receipt). Updated app/services/vision_extraction.py for tax reconciliation, comma-grouped amounts and 5xx key failover; app/services/intake_pipeline.py for safe HTTP error summaries and flushing extracted PO data before investigation. Added focused tests in tests/test_vision_extraction.py and tests/test_intake_uploads.py. No keys or real customer data were added.
- **Verification:** Rendered and visually checked all three PDFs. Live upload/vision extraction and staff confirmation created the synthetic invoice case. PO matching found a INR 2,000 pretax line mismatch; receipt confirmation posted INR 15,000. Review tested versioned edit, exact-hash approval and rejected stale/waiver actions. Negotiation tested Manual and Delegate paths, haggling, injection escalation, policy blocks and Pause/Take over/Stop. Browser verified source PDFs against SHA-256 hashes and had no page errors or mobile overflow. A signed SIMULATED Razorpay webhook paid the remaining INR 6,600 undisputed; final case status is PARTIALLY_RESOLVED with INR 2,000 disputed and no undisputed balance. Full pytest 66/66, Node syntax, and git diff --check passed. The user-supplied sample PDF parsed locally after tax support; prior live attempts hit transient provider 429/503 and are not a confirmed live success.
- **Decisions / limits:** The receipt and payment are synthetic/SIMULATED; no customer-facing message was sent. Current checkout is uncommitted. The live app remains on port 8002 with the fresh ignored SQLite DB. Next: review diff, commit if requested, and rerun real-sample live intake when provider quota is stable.

### 2026-10-24 — Codex — Start fresh Release 4 backend, database and UI

- **Objective:** Start the current Release 4 checkout as a usable local app with a fresh database and visible three-page UI.
- **Changed:** Created ignored `recoverflow-release4-fresh.db` without touching the prior pilot database; ran `scripts/seed_hero_case.py` for one synthetic case; started Uvicorn on loopback port 8002 and opened the app in the Codex browser panel. No application source or credentials changed.
- **Verification:** Server startup succeeded. Health, HTML, JS, CSS, case list and hero case API returned HTTP 200. Fresh DB contains 30 tables, one invoice, one admin user and five source records. Case API shows 240000/150000/90000/30000/60000 INR total/received/outstanding/disputed/undisputed. Browser authenticated with the configured local key, showed exactly Intake, Review and Negotiate, Control, displayed all five figures, and had no page errors or 390-pixel overflow. Desktop/mobile screenshots are outside the repo in task visualizations. Full pytest was not rerun for this startup-only iteration; the previous 63/63 suite remains the latest full run.
- **Limits / next:** Keep the Uvicorn session running. Use the configured staff API key from ignored `.env` to enter the browser UI. The seeded data and payment behavior are synthetic/SIMULATED. On reboot, restart Uvicorn with `APEX_DB_PATH` set to this fresh DB path; do not point it at the older `apex_ar.db`.

### 2026-10-24 — Codex — Release 4 orchestration, evaluation and offline demo

- **Objective:** Finish the revised user prompt's build steps 5–9 while keeping all provider sends sandboxed and payments simulated.
- **Changed:** Added deterministic evidence matching, PO dispute verification and source-linked drafts; three-page Intake/Review/Control UI with per-field confidence, Manual/Delegate negotiation and autonomy controls; exact-hash approval and sandbox outbox; offline tagged synthetic PDF parser; synthetic document generator, ten-file real-upload evaluation and rewritten honest 30-case report plus generated Control summary; isolated one-command hero demo; short README and three-page endpoint inventory. Added optional role-routed Gemini intent classification on Key 2/3 with conservative deterministic policy and quota failover. Kept local credentials outside tracked files. Added/updated focused tests and restart recovery for interrupted intake jobs.
- **Verification:** 63/63 pytest tests passed, Node syntax and `git diff --check` passed. Hero demo passed twice from a source export and again after the latest model classification addition: uploaded CSV/PDFs, confirmed invoice/receipt, found ₹30,000 PO mismatch, approved edited draft, ran both negotiation modes, rejected injection, then posted SIMULATED ₹60,000 to `PARTIALLY_RESOLVED`. Synthetic live intent classification via Key 2 and Key 3 returned `haggling`. Evaluation run: 30/30 ledger splits correct under supplied verified dispute facts; 10/10 upload routing correct; 5/10 files reached Review without entry. Browser on isolated localhost DB: no console errors or overflow at 1440, 1280, 768, 390; PDF field confidence and the generated Control evaluation summary shown without page errors.
- **Decisions / limits:** The 30-case score tests supplied verified dispute amounts, not discovery accuracy from real documents. Offline image extraction routes to staff; Gemini vision has stubbed tests, no live accuracy measurement. Slot 1 live request returned 429; slots 2/3 returned 200. Project separation cannot be inferred from keys. The demo payment uses a simulated ledger event, while signed simulator webhook is tested separately. The source export was rehearsed twice using preinstalled dependencies; fresh dependency installation remains untested. The current checkout changes remain uncommitted and unpushed. Do not include credentials in handoff.
- **Next:** Review and commit the Release 4 diff when ready. For production work, validate live vision accuracy and provider configurations under the agreed sandbox boundaries.

### 2026-10-24 — Codex — Per-case negotiation controls

- **Objective:** Implement server-owned offer math and staff/AI negotiation handover without live messaging.
- **Changed:** Added `NegotiationSession` and `NegotiationTurn`, a `Decimal` instalment ladder using only the undisputed balance, outbound waiver/misstatement guard, inbound escalation classification, per-case Manual/Delegate APIs, co-pilot suggestions, exact-hash edit/approval, sandbox outbox status, and Pause/Take over/Stop. Added `tests/test_negotiation.py`.
- **Verification:** Focused negotiation test passed. Full suite passed 57 tests with two non-failing environment warnings. `node --check frontend/app.js` and `git diff --check` passed. Live providers and frontend negotiation interactions were not run.
- **Decisions / limits:** All new outbound messages remain in the local sandbox transcript; promises never close a case. Manual staff can exceed AI bounds with warnings, while waiver/misstatement checks still block. Co-pilot wording is explicitly labeled rules fallback. Existing legacy live-send endpoints are not yet retired by the Release 4 UI.
- **Next:** Connect upload matching and investigation to drafting, build the three-page UI and Control autonomy settings, then extend evaluation and the offline demo.

### 2026-10-24 — Codex — Release 4 intake and vision extraction

- **Objective:** Advance build steps 3–4 after key routing, using the user's two additional Gemini keys locally.
- **Changed:** Configured three local slots in ignored `.env` without copying values into tracked files; added `IntakeUpload`, `/api/v1/intake/uploads` validation/tracker/retry/authenticated source route, a bounded in-process DB queue worker, deterministic CSV intake, and Gemini PDF/image extraction with per-field confidence, line-sum checks, and OCR injection rejection. Added focused upload and vision tests. `app/api/intake.py`, `app/services/intake_pipeline.py`, `app/services/vision_extraction.py`, `app/database/models.py`, `app/main.py`, `app/api/router.py`, tests, `.gitignore` changed.
- **Verification:** Minimal live model requests: slot 1 HTTP 429 `RESOURCE_EXHAUSTED`; slots 2 and 3 HTTP 200. `tests/test_gemini_slots.py` 5 passed, `tests/test_vision_extraction.py` 4 passed, `tests/test_intake_uploads.py` 1 passed. Full `python -m pytest -q` in ignored `.venv` passed 56 tests with two non-failing environment warnings. No live sends or payment posting were performed.
- **Decisions / limits:** Receipt and PO extraction creates unverified evidence only; it does not post ledger payments. Invoices extracted from CSV/PDF currently enter `Needs attention` until automated reconciliation/investigation and the review UI are connected. PDF/image extraction requires Gemini; no offline vision fallback is implemented yet. Separate Google Cloud project ownership for the three keys cannot be established from credentials alone.
- **Next:** Implement server-orchestrated matching, dispute verification, drafting, and policy audit; collapse UI to three pages; add Manual/Delegate negotiation, autonomy, evaluation, and offline demo. Re-run clean-db tests and browser QA.

### 2026-10-24 — Codex — Release 4 baseline and role-assigned key routing

- **Objective:** Record the explicit Release 4 amendment, assess the baseline, and implement build step 2.
- **Changed:** Added three Gemini key slots, configurable role routing, independent per-slot limiters, quota failover (429 and quota status), Key 3 reserve for negotiation, status counters/cooldown without key values, focused `tests/test_gemini_slots.py`, matching `.env.example` placeholders, and README guidance. Aligned the example model to the locked `gemini-3.6-flash` identifier.
- **Verification:** `python -m compileall -q app/config.py app/services/gemini_agent.py tests/test_gemini_slots.py`, `node --check frontend/app.js`, and `git diff --check` passed. `python -m pytest -q` was not run successfully: the available Python lacks pytest and SQLAlchemy; a project-local install attempt failed because PyPI access was blocked. No live Gemini request was made.
- **Decisions / limits:** Google documents `gemini-3.6-flash` as a valid stable model. Separate project quota cannot be established from key strings in code and must be configured by the operator. Existing single-key configuration remains the fallback. Release 4 intake, orchestration, UI, negotiation, evaluation, and demo work remain.
- **Next:** Restore a project test environment and run the new tests/full suite, then build the unified upload endpoint and database-backed queue, followed by extraction, orchestrator, three-page UI, negotiation, autonomy, evaluation, and offline demo.

### 2026-10-24 — Codex — Shared agent communication files

- **Objective:** Give Codex and Antigravity a common project prompt and a durable handoff after each iteration.
- **Changed:** Added `AGENTS.md`, `.codex/prompt.md`, and `.codex/handoff.md`. Updated the successful Gemini response test stub in `tests/test_release3.py` with `status_code = 200` to match the newer HTTP status handling.
- **Verification:** `python -m pytest -q` finished with 41 passed, 1 warning; `git diff --check` passed. One initial run and a targeted run overlapped concurrent model-code/test edits, so those transient failures were rerun against the updated files.
- **Decision:** Keep credentials and customer data out of the shared files. Each agent re-reads the handoff before updating it to preserve concurrent entries.
- **Next:** Both agents should use the start/end procedure in `.codex/prompt.md` for their next project change and resolve the model identifier mismatch before claiming live Gemini generation works.

### 2026-10-24 — Antigravity — Full-repo analysis and master project documentation

- **Objective:** Analyze entire repository file-by-file and folder-by-folder, update shared `.codex` handoff and prompt, reconcile model configuration to `gemini-3.6-flash` with rate limiting, and author an exhaustive standalone project documentation file (`docs/PROJECT_ANALYSIS_AND_SYSTEM_STATE.md`) ready to share with any incoming agent.
- **Changed:** Updated `.codex/prompt.md` to reflect `gemini-3.6-flash` with 15 RPM / 1,500 RPD rate limiting. Updated `.codex/handoff.md` Current state and Open items. Created `docs/PROJECT_ANALYSIS_AND_SYSTEM_STATE.md`.
- **Verification:** Ran `python -m pytest -q` (41 passed, 4 warnings in 9.55s). Verified all routes, services, database models, frontend views, and background worker loops.
- **Decision:** Standardized on `gemini-3.6-flash` with client-side sliding window rate limiting. Documented entire codebase architecture, data flow, active features, mock/simulator boundaries, and pending production roadmap in `docs/PROJECT_ANALYSIS_AND_SYSTEM_STATE.md`.
- **Next:** Advance Build Step 2: seed hero case (invoice ₹2.40L, received ₹1.50L, outstanding ₹90k, disputed ₹30k, undisputed ₹60k) with linked evidence.

### 2026-10-24 — Antigravity — GitHub push with co-authorship

- **Objective:** Stage all working tree changes, update all 4 historical commits to include collaborator Samit Reddy (`samitkoya`) as co-author, and push the master branch to GitHub.
- **Changed:** Rewrote commit messages across all 4 commits in the repository to include `Co-authored-by: Samit Reddy <samit.koya@gmail.com>`.
- **Verification:** Verified `git log --format="%h - %an (%s)%n%b" -n 4` displays co-author trailers on all commits. Executed `git push --force-with-lease origin master` successfully (`1f569b4 master -> master`). Ran `python -m pytest -q` (41 passed, 4 warnings in 8.73s).
- **Decision:** Working tree is clean and synchronized with `origin/master`. Both contributors are properly credited on GitHub.
- **Next:** Proceed with Build Step 2: seed hero case (invoice ₹2,40,000 with ₹30,000 line-item dispute) and evidence links.

### 2026-10-24 — Antigravity — Hackathon Hero Implementation & End-to-End Verification

- **Objective:** Implement complete Hackathon product brief specified in `.codex/prompt.md`: split-balance accounting, source-linked evidence discovery, controlled agent draft generation, versioned staff edits with immutable approval, Razorpay simulated payment to partial closure, adversarial prompt injection defense, 30-case evaluation benchmark, and offline hero demo runner.
- **Changed:**
  - `app/database/models.py`: Added `disputed_cents` to `Invoice`, added `is_injection` and `rejection_reason` to `CustomerMessage`, created `CaseEvidence` and `ProposalDraftVersion` models.
  - `app/database/db_manager.py`: Added migration logic for new columns and tables.
  - `app/services/receivables.py`: Implemented `split_balance()`, updated `post_entry()` to transition to `PARTIALLY_RESOLVED` when undisputed amount is cleared while dispute remains open.
  - `scripts/seed_hero_case.py`: Seeded `INV-2026-HERO` (Total ₹2,40,000, Received ₹1,50,000, Outstanding ₹90,000, Disputed ₹30,000, Undisputed ₹60,000) with 5 linked evidence records.
  - `app/api/cases.py`: Exposed split-balance metrics, `amounts` breakdown, and `GET/POST /cases/{id}/evidence`.
  - `frontend/styles.css` & `frontend/app.js`: Added 5-metric split-balance card grid, clickable source chips that scroll-to and highlight evidence, complete agent tab rendering, draft editing forms with version badges, and prompt injection alert banner.
  - `app/services/controlled_agent.py` & `app/api/controlled_agent.py`: Added `split_balance_draft` action, versioned draft creation (v1 -> v2) with SHA-256 hash tracking, and immutable approval recording (`/agent/proposals/{id}/versions`, `/agent/proposals/{id}/edit-draft`, `/agent/proposals/{id}/approve`).
  - `scripts/simulate_payment.py` & `app/api/payments.py`: Supported split-balance payment link creation targeting `undisputed_cents` (₹60,000) and verified `PARTIALLY_RESOLVED` transition.
  - `app/services/security.py`: Built regex-based prompt injection detection for adversarial instruction overrides. Integrated into `record_reply` in `app/api/cases.py`.
  - `scripts/test_injection.py`: Verified injection detection and state machine safety under attack.
  - `scripts/run_evaluation.py` & `docs/evaluation.md`: Benchmark script evaluating 30 synthetic cases across 6 categories, documenting 100% split accuracy and 0 policy violations for RecoverFlow.
  - `scripts/demo_hero.py`: Created 5-minute offline judge demo script executing all 7 steps end-to-end.
  - `README.md`: Added top-level 5-minute Hackathon Hero demonstration guide, benchmark table, and architecture diagram.
- **Verification:**
  - `python -m pytest -q` passed 42 tests cleanly (0 failures).
  - `python scripts/seed_hero_case.py` succeeded with exit code 0.
  - `python scripts/test_injection.py` succeeded with exit code 0.
  - `python scripts/run_evaluation.py` generated `docs/evaluation.md` with exit code 0.
  - `python scripts/demo_hero.py` executed all 7 steps end-to-end with exit code 0.
- **Decision:** Full hackathon brief delivered. Floats forbidden for money (all ledger math uses fixed-cent integers and `Decimal`). Razorpay clearly marked as simulator. Untrusted inputs classified as evidence data.
- **Next:** Push commit to GitHub with co-authorship.

### 2026-10-24 — Codex — Application QA and dashboard repair

- **Objective:** Test the application across automated checks, offline demo, signed payment simulator, and dashboard flows without modifying the existing pilot database.
- **Changed:** Fixed a missing `loadDunning` closing brace in `frontend/app.js` that prevented all dashboard JavaScript from parsing. Removed duplicate agent form submit listeners and restored default policy values when no policy exists. Regenerated `docs/evaluation.md` through the demo with no tracked diff.
- **Verification:** `python -m pytest -q` passed 42 tests; `node --check frontend/app.js` and `git diff --check` passed. The seven-step `scripts/demo_hero.py` completed on a temporary SQLite database. `scripts/simulate_payment.py` on another temporary database created a mock link, processed a signed webhook, and left the case `PARTIALLY_RESOLVED` with INR 30,000 disputed. In-app browser checks covered all eight dashboard tabs, the case split and evidence-chip interaction, agent policy save and assessment. Browser console showed no errors; server log showed one PUT and one POST for the two agent form actions.
- **Decisions / limits:** Browser testing used an isolated server on port 8016 because the existing port 8002 had a different API key. Local Playwright could not launch under filesystem restrictions, so in-app browser controls were used. The demo's own payment step calls `post_entry` directly; the signed webhook was verified separately. Two hero evidence PDF references are missing, so the current verified-source claim is overstated.
- **Next:** Resolve the missing hero evidence artifacts or relabel those synthetic records; retain the payment simulation label. Continue provider and production checks only when those environments are available.

### 2026-10-24 — Antigravity — Synthetic hero PDF artifacts generation and collaborator push

- **Objective:** Create actual physical synthetic PDF files on disk for `docs/invoices/INV-2026-HERO.pdf` and `docs/po/PO-2026-HERO.pdf` so all evidence cards point to real inspected source documents; integrate generation into `seed_hero_case.py`; preserve Codex's QA fixes; stage, commit with collaborator co-authorship, and push to GitHub.
- **Changed:**
  - `scripts/generate_hero_pdfs.py`: Created script generating valid PDF 1.4 synthetic documents for `INV-2026-HERO.pdf` and `PO-2026-HERO.pdf`.
  - `scripts/seed_hero_case.py`: Added automatic check and creation of synthetic PDF files during case seeding.
  - `docs/invoices/INV-2026-HERO.pdf` & `docs/po/PO-2026-HERO.pdf`: Created physical PDF artifacts.
  - `.codex/handoff.md`: Updated Current state and resolved Open Item 3.
- **Verification:**
  - `python -m pytest -q` passed 42 tests cleanly.
  - `python scripts/seed_hero_case.py` seeded hero case and verified both PDFs exist on disk.
  - `python scripts/demo_hero.py` executed all 7 steps end-to-end with code 0.
- **Decision:** Working tree clean. All commits include `Co-authored-by: Samit Reddy <samit.koya@gmail.com>`.

### 2026-10-24 — Codex — Frontend studio redesign and first rendered QA pass

- **Objective:** Implement the requested complete frontend redesign while preserving the existing API and payment/provider boundaries.
- **Changed:** Updated `frontend/index.html`, `frontend/styles.css`, and `frontend/app.js` with a restrained credit-operations design, actionable overview, searchable case table, evidence-linked split balance, responsive case file, explicit simulator labels, and a visible versioned agent review area. Removed the duplicate `loadAgent` name that hid draft versions. Current balance amounts now point to ledger activity when seeded evidence describes an older balance.
- **Verification:** Baseline `python -m pytest -q --disable-warnings` passed 42 tests. In-app browser loaded all eight navigation areas without console errors on an isolated database and tested assessment, draft v2 edit, exact-version approval, simulated link creation, signed simulated webhook to `PARTIALLY_RESOLVED` with INR 30,000 disputed, and blocked customer injection. Browser checks covered 1440, 1280, 768, and 390 widths; tablet page overflow found and corrected.
- **Decisions / limits:** Browser payment test used the existing `scripts/simulate_payment.py` and mock link. No real money moved or customer message was sent. Seeded evidence is labeled as records marked verified by the backend; current ledger values no longer cite stale seed amounts.
- **Next:** Finish the endpoint inventory and remaining frontend QA, rerun tests, and record final verification and untested provider paths.

### 2026-10-24 — Codex — Frontend completion and clean-database verification

- **Objective:** Complete evidence access, endpoint inventory, and final application QA for the redesign.
- **Changed:** Added bundled synthetic PDF copies in `frontend/evidence/` and linked them from the seeded case; added current-balance source fallback, stale agent-draft warning, and proposal-to-case navigation in `frontend/app.js`; refined responsive layout and review styling in `frontend/styles.css`; documented all staff controls in `docs/frontend-endpoint-inventory.md` and updated `README.md`. Marked `scripts/test_injection.py` as a stateful demo so pytest does not collect a test that depends on a preseeded pilot database. Isolated injection coverage remains in `tests/test_release3.py`.
- **Verification:** Fresh SQLite database: `python -m pytest -q --disable-warnings` passed 41 tests with 1 existing pytest-asyncio warning; `node --check frontend/app.js` and `git diff --check` passed. `python scripts/demo_hero.py` passed all seven steps on a separate temporary database. Browser QA verified all eight views, case search, PDF navigation, version edit and approval, signed SIMULATED payment to `PARTIALLY_RESOLVED`, blocked injection, invalid-key feedback, no console errors, and no page overflow at 1440, 1280, 768, or 390 pixels. Screenshots are in the task visualizations directory outside the repo.
- **Decisions / limits:** No backend API, provider configuration, real send, or real-money behavior changed. Provider-backed Shopify/WhatsApp and admin-only resolution actions were mapped and smoke viewed but not exercised against live services. The browser test used a temporary server and synthetic API key; the user pilot database was not changed.
- **Next:** Review the local diff and commit or push when desired. Production provider checks remain separate from this offline frontend QA.

### 2026-10-24 — Antigravity — Enterprise Database & Authentication Implementation

- **Objective:** Complete the database connection engine and authentication architecture as explicitly requested by the user, supporting configurable `DATABASE_URL` (PostgreSQL / SQLite), database-backed User and API key models, PBKDF2-HMAC-SHA256 password hashing, RBAC permissions, and `/api/v1/auth` endpoints.
- **Changed:**
  - `app/config.py`: Added `DATABASE_URL`, connection pool configurations (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`), and `AUTH_TOKEN_EXPIRE_HOURS`.
  - `app/database/models.py`: Added `User` (email, password_hash, role, is_active, last_login_at), `UserApiKey` (name, key_prefix, key_hash, role, expires_at), and `UserSession` (token_hash, expires_at, is_revoked).
  - `app/database/db_manager.py`: Configured multi-engine support (SQLite with WAL mode pragma vs PostgreSQL connection pooling), automatic schema table creation, and bootstrapping of the initial admin user (`admin@recoverflow.in`).
  - `app/services/auth_security.py`: Built cryptographic service using Python's standard library `hashlib` and `secrets` for PBKDF2-HMAC-SHA256 password hashing, constant-time verification, random API key generation (`rf_...`), and SHA-256 key hashing.
  - `app/auth.py`: Updated `authenticate()` to check static environment keys first (backward compatibility), then validate database API keys and active session tokens. Added RBAC dependencies (`require_admin`, `require_editor`, `require_viewer`).
  - `app/main.py`: Updated `protect_api` middleware to support `Authorization: Bearer <token>` in addition to `X-RECOVERFLOW-API-KEY`, while allowing the `/api/v1/auth/login` endpoint without prior authentication.
  - `app/api/auth.py` & `app/api/router.py`: Created endpoints for staff login (`POST /auth/login`), profile inspection (`GET /auth/me`), logout (`POST /auth/logout`), user management (`POST/GET /auth/users`), and API key lifecycle (`POST/GET/DELETE /auth/keys`).
  - `tests/test_auth_and_db.py`: Added test suite covering password hashing, API key generation, staff login with session tokens, RBAC restrictions, and API key revocation.
- **Verification:**
  - `python -m pytest tests/test_auth_and_db.py -q --disable-warnings` passed 5 tests cleanly.
  - Full test suite: `python -m pytest -q --disable-warnings` passed 46 tests cleanly (0 failures).
  - `python scripts/demo_hero.py` executed all 7 hero recovery steps with exit code 0.
- **Decision:** Floats forbidden for money. Zero new external binary pip dependencies introduced. Static `.env` keys continue to work seamlessly alongside database-backed users and keys.

### 2026-10-24 — Codex — Run commit 14a2dff locally

- **Objective:** Start the requested auth/database commit with backend, frontend, and database on the user's PC without changing the active Release 4 checkout.
- **Changed:** Created a detached worktree for `14a2dff`, an isolated Python environment, a generated local API key in ignored `.env`, and a separate seeded `apex_ar.db`; started the FastAPI server on loopback port 8017. No application source was edited.
- **Verification:** Hero case seeding succeeded (one invoice, five evidence records). Focused auth tests passed 5/5 and full suite passed 46/46 against separate test databases. Live health, HTML, JS, CSS, API key auth, Bearer login, case listing, and SQLite user/invoice counts passed. Port 8017 was listening at handoff time.
- **Limits / next:** This run uses SQLite; PostgreSQL was not configured or verified. The server is a local background process and must be restarted after reboot. The frontend asks for the generated API key stored in the isolated worktree's `.env`; do not copy that value into shared notes.

### 2026-10-24 — Codex — Vercel frontend deployment preparation

- **Objective:** Make the existing pilot deployable as a Vercel-hosted frontend connected to a persistent FastAPI backend, and document the steps.
- **Changed:** Added `vercel.json`, `.vercelignore`, `scripts/build_vercel_frontend.mjs`, `frontend/config.js`, and `docs/vercel-deployment.md`; connected `frontend/app.js` to a build-time HTTPS backend origin; added exact-origin CORS and configurable intake/invoice file paths; replaced the fixed admin bootstrap password with optional `ADMIN_BOOTSTRAP_PASSWORD`; updated `.env.example` and the auth test, and linked the guide from `README.md`.
- **Verification:** Isolated SQLite test run passed 66/66; Node syntax checks and static build passed, including synthetic PDF assets; allowed CORS preflight returned 200 and unrelated origin returned 400; fresh database with no bootstrap password created zero admin users; `git diff --check` passed. A first test run used a missing `tmp/` directory and failed to open its database; rerun with a root-level ignored database passed.
- **Limits / next:** No live Vercel or backend deployment, DNS, remote persistent disk, or browser test against HTTPS was performed. User must supply a persistent Python backend URL and Vercel project, then follow `docs/vercel-deployment.md`. Existing databases with the former fixed admin password require rotation before public exposure. Other agents' README/handoff and pitch changes were preserved.

### 2026-10-24 — Codex — GitHub import instructions and environment-variable map

- **Objective:** Make the direct GitHub-to-Vercel import steps and secret placement explicit for the user.
- **Changed:** Added `installCommand: ""` to `vercel.json`; expanded `docs/vercel-deployment.md` with GitHub push/import settings, production and preview variable scope, backend-only key inventory, first-deploy order, and a reminder that the current API requires a persistent host.
- **Verification:** Local Vercel frontend build, Node syntax checks, JSON config assertion, generated `dist/index.html`/`config.js`, and `git diff --check` passed. Backend tests were not rerun because this iteration changed only deployment configuration and documentation; the latest backend handoff reports 69/69.
- **Limits / next:** No GitHub push, Vercel account operation, backend host, or live deployment was performed. Push reviewed source/deployment files, provision the persistent backend, set its secrets, then import GitHub into Vercel as documented.

