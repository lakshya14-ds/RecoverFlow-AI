# RecoverFlow agent handoff

Shared by Codex and Antigravity. Read `.codex/prompt.md` first. Update this file after every meaningful iteration; re-read it immediately before writing so another agent's entry is preserved. Do not add secrets or customer data.

## Current state

- **Independent verification (2026-10-30, Codex):** 342 tests pass after seven fixes (migration bootstrap binding, debit-aware reversal ceiling, reversal retry identity, privacy party scoping, economics signs, active-lease recovery, expired supervisor pickup). Both demos and 38-case offline evaluation rerun; desktop/mobile and isolated API smoke pass. README rewritten; current 17-workstream status and remaining limitations in docs/verification-2026-10-30.md. Port 8002/live DB untouched. No commits; existing work preserved.

- **P2 B2 done (2026-10-29, Muse Code):** Indian document model — persisted alleged/verified lines, invoice GST/freight split, credit/debit notes (alleged→accepted→posted, SoD accept, admin post, idempotent), supporting docs, debit-kind ledger support (`0 ≤ disputed ≤ outstanding ≤ face + debits`), investigation uses persisted lines + challan/scheme/freight handling + enriched tax clarifications, 6 reconciliation fixtures. Migration `20261105_documents_v10`. 15 new tests; full suite 232 passed. Next: B3 installments.
- **P2 B1 done (2026-10-29, Muse Code):** Counterparty identity — legal/display names, format-only GSTIN (unique per tenant), branches, external IDs, explainable duplicate suggestions, staff-confirmed admin merges (links move, invoice names untouched, immutable history), bootstrap + import linking, case-view party block. Migration `20261104_identity_v9`. 12 new tests pass. Next: B2 document model.
- **P2 Milestone A complete (2026-10-29, Muse Code):** A1 migration status + backup/restore drill, A2 per-tenant secrets/webhooks/AFIS + private evidence, A3 throttle/recovery/rotation + admin money gates + role matrix, A4 assignment/notes/tasks/escalations/workload + SoD on 4 approval paths. Gate: full suite 205 passed, both demos green in isolation, `git diff --check` clean, PG honestly unverified (no instance). Next: Milestone B (identity, documents, installments).
- **P2 A3 done (2026-10-29, Muse Code):** Login throttle (5/email, 20/IP per 15min, 429), admin-issued single-use recovery (public redeem, kills sessions), session rotate/list/revoke/revoke-all, admin-only manual entries/allocation approvals/reconciliation approvals/receipt confirms, `docs/auth-permissions.md` matrix. Migration `20261102_auth_v7`. 9 new tests; full suite 193 passed. Next: A4 team ops.
- **P2 A2 done (2026-10-29, Muse Code):** Tenant audit complete; `TenantSecret` (by reference, never values) + `TenantSetting` with migration `20261101_tenancy_v6`; webhooks verify per-tenant secrets (unknown→503, malformed→404, tampered replay→409); AFIS per-tenant files; evidence fixtures behind authed endpoint with public copies deleted; two invoice-review lookups hardened. 15 new tests; full suite 184 passed. Next: A3 auth.
- **P2 A1 done (2026-10-29, Muse Code):** Migration status (`migrations.status()` + admin `GET /api/v1/system/migrations`, URL never exposed), legacy SQLite upgrade tests (REAL→text money, tenant backfill, invalid-money abort + retry), transaction/constraint tests, `scripts/db_backup.py` + verified backup/restore drill, `docs/ops-backup.md` (SQLite procedure + PG 15+ deployment steps, PG explicitly unverified). 11 new tests pass; full suite not yet rerun. Next: A2 tenancy.
- **P2 baseline + gap matrix (2026-10-29, Muse Code):** Full suite re-verified 158 passed; P1 showcase passes in-tree; hero demo passes in isolated `%TEMP%` copy (tracked eval files untouched); port-8002 app untouched. New `docs/p2-gap-matrix.md` maps all 17 P2 workstreams from code: A1/A2/A3/B1/B2/B3/C2/D2/D3/E/F3 partial, A4/C1/F1 missing, D1/F2 blocked on external input. Notable findings: webhooks hard-reject non-`local` tenants (safe, single-tenant); `frontend/evidence/*` served unauthenticated; no PG client/driver/instance on this host. Next: Milestone A.
- **Port 8002 safe restart on current code (2026-10-28, Antigravity):** Full port and process audit completed. Live DB backed up to `backups/apex_ar-20261028-2331.db` (with `-wal` and `-shm` sidecars). Verified stale PID 37256 stopped gracefully. App cleanly restarted on current working tree code under PID 33808; health 200, authenticated case API 200 (`INV-2026-HERO` split 240000/150000/90000/30000/60000), frontend served (`/`) with Intake/Review-and-Negotiate/Control navigation present, Meta agent active (`muse-spark-1.3`), all 5 DB migrations applied cleanly, zero `gemini` import errors, sibling services (8000/8001) and unrelated processes untouched, zero orphan test servers.

- **Meta Model API swap complete (2026-10-28, Muse Code):** Full Gemini replacement per explicit user request. New `app/services/meta_agent.py` (OpenAI-compatible `muse-spark-1.3` via `https://api.meta.ai/v1`, same slot/rate-limit architecture); vision extraction via multimodal image/PDF parts; config/docs/tests/frontend repointed; live key verified (classify, generate, image + PDF vision). 158/158 tests pass. `.env` model updated; old Gemini keys left unused. Tree still dirty.
- **P1 Milestone 5 complete (2026-10-28, Muse Code):** 38-case three-arm evaluation (rules/single/specialist, fixed seeds, Wilson intervals, per-case failures in `docs/p1-evaluation.md`); failure-testing fixed zero-claim overlap, damage-idempotency stall, and ISO promise dates; 9-beat showcase + walkthrough + architecture docs. 158/158 tests pass (7 new M5 + 2 M2 regressions). Next: review/commit the dirty tree. Tree still dirty.
- **P1 Milestone 4 complete (2026-10-28, Muse Code):** Multilingual (en/hi/Hinglish) validated drafting, owner queue + activity view, `generic_csv` import adapter; live-verified on isolated port-8019 app. 149/149 tests pass (14 new + 1 M1). Next: M5 evaluation + showcase. Tree still dirty.
- **P1 Milestone 3 complete (2026-10-28, Muse Code):** Transfer allocation (scored candidates, splits, ambiguity held for staff, guarded staff approval through `post_entry`) + nonfinancial promise tracking (extract/confirm/remind/kept/broken); migration `20261031_allocation_v5`. 135/135 tests pass (13 new); isolated demo regression passes. Razorpay still SIMULATED. Next: M4 multilingual + queues + import adapter. Tree still dirty.

- **P1 Milestone 2 complete (2026-10-28, Muse Code):** Evidence-led investigation: pure `line_matching` (SKU/unit/qty/price/tax/freight/rounding, no silent conversion or apportionment), competing explanations + clarification tasks + staff unit rules (migration `20261030_investigation_v4`), damage claims, multi-SKU attribution, duplicate/unreadable handling, unsent drafts only. 122/122 tests pass (15 new); isolated demo regression passes. Next: M3 payment allocation + promises. Tree still dirty.

- **P1 Milestone 1 complete (2026-10-28, Muse Code):** Deterministic supervisor + 6 specialist contracts + durable `supervisor_tasks` (migration `20261029_supervisor_v3`) with pause/resume/retries/budgets/replay, tenant-scoped API, triggers on ledger/reply/document/staff events, background execution loop. 107/107 tests pass (13 new); isolated demo regression passes; live port-8019 chain ran resolution→communication→verification to steady with ledger untouched. User port-8002 process untouched. Next: M2 evidence-led investigation. Tree still dirty.

- **P0 foundations complete (2026-10-28, Muse Code):** Accounting/currency hardened (Decimal everywhere, currency-mismatch rejection, no float money paths), canonical lifecycle in `app/services/case_lifecycle.py` (7 stages, credit-aware status, stale-approval guards), evidence trust states (alleged/extracted/verified/accepted/rejected) with conservative migration `20261028_trust_states_v2`, 13 new P0 regression tests (94 passed total), seed reseed-fix, honesty docs updated. Verified: full suite 94/94, `node --check`, `git diff --check`, isolated `demo_hero.py` + evaluation (30/30, 10/10, 5/10), live port-8019 checks on isolated SQLite DB. User port-8002 process untouched. PostgreSQL/Gemini-accuracy/live-provider validation still not run (no instances). Tree still dirty (all prior agent work preserved).

- **Baseline re-verification (2026-10-28, Muse Code):** No code changed, verification only. Full suite 81/81 with Anaconda Python 3.12 unsandboxed (sandboxed runs fail 37 tests on WinError 10013 socket blocks; environmental, not code). User's own `run.py` server (process 37256, started 2026-10-27 22:39) healthy on port 8002; hero case live with 240000/150000/90000/30000/60000 split, 5 evidence records, 1 proposal, 3 Gemini slots configured. Post-restart edits are frontend-only (`app.js`, `styles.css` nav fix), served from disk, no restart needed. `node --check` and `git diff --check` pass. Tree still dirty (foundation repair uncommitted). No app errors found; nothing fixed.

- **Foundation repair (2026-10-27, Codex):** Cash receipts and credits now display separately; new ledger entries record dispute allocation and reversals restore the original allocation. Exact decimal money storage and a versioned SQLite migration are in place. Inconsistent old cases open in staff review with no eligible amount. Expanded document investigation, common case checkpoints, stale offer checks, and broader untrusted-text/outbound guards are implemented. Full suite: 81 passed; offline hero demo passed; local app and synthetic credit flow passed. PostgreSQL remains unverified without a server. See `docs/foundations-2026-10-27.md`.

- **Polished Neobrutalist Frontend Redesign (2026-10-27):** Redesigned the entire RecoverFlow frontend in a production-grade Neobrutalist style across all three main pages (Intake, Review and Negotiate, Control) and all reachable legacy tools. Built a unified design system in `frontend/styles.css` with warm surfaces (`#f8f6f0`), dark borders (`#121212`), unblurred offset shadows, vivid accents (cobalt, yellow, coral, mint), tactile button active states, 5-figure split balance cards with distinct tints, high-visibility injection security banner, styled file upload dropzone, and responsive layouts. Verified with 69/69 pytest tests, `node --check`, `demo_hero.py` 7-step offline run, and browser automated testing via Edge across 1440, 1280, 768, and 390 px viewports with 0 console errors and zero horizontal overflow on mobile.

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

### 2026-10-27 — Antigravity — Polished Neobrutalist Frontend Redesign and Cross-Device Verification

- **Objective:** Redesign the complete RecoverFlow frontend in a polished neobrutalist style across all three main pages (Intake, Review and Negotiate, Control) and all reachable legacy tools, while strictly preserving backend authority, ledger calculations, SIMULATED payments, sandbox messaging boundaries, keyboard accessibility, and zero-overflow responsiveness across 1440, 1280, 768, and 390 px viewports.
- **Changed:**
  - `frontend/styles.css`: Complete redesign into a cohesive neobrutalist design system with warm light surfaces (`#f8f6f0`), strong dark outlines (`2px` / `3px` solid `#121212`), hard offset box-shadows (`2px 2px`, `4px 4px`, `6px 6px 0 #121212` with no blur), squared/lightly rounded borders (`4px`), thick dividers, tactile button active states (`translate(2px, 2px)`), restrained vivid accents (cobalt `#2563eb`, yellow `#facc15`, coral `#f43f5e`, mint `#10b981`), high-contrast accessible typography, 5-figure split balance cards with distinct color tints, high-visibility injection security alert banner, neobrutalist multi-file drag-and-drop zone, styled tables with uppercase headers and hover row borders, evidence cards, negotiation chat bubbles with sender tags, and draft approval version badges.
  - Mobile responsiveness fixes in `frontend/styles.css` ensuring `.search-field` collapses to 100% on narrow viewports, section headers wrap gracefully, and horizontal overflow is eliminated on 390px screens (`clientWidth: 390px, scrollWidth: 390px`).
- **Verification:**
  - Ran backend test suite: `py -3.12 -m pytest -q --disable-warnings` (69 passed, 0 failures, 3 warnings in 23.15s).
  - Syntax checked JavaScript: `node --check frontend/app.js` (passed with code 0).
  - Executed offline demo runner: `py -3.12 scripts/demo_hero.py` (all 7 steps passed cleanly with exit code 0).
  - Executed hero case seeding: `py -3.12 scripts/seed_hero_case.py` (INV-2026-HERO seeded with split metrics ₹2,40,000 / ₹1,50,000 / ₹90,000 / ₹30,000 / ₹60,000).
  - Automated browser testing using Microsoft Edge across 4 viewport resolutions:
    - 1440x900 Desktop: Verified Intake, Review & Negotiate, open case with 5 split figures, clickable source chips, draft versions, and Control.
    - 1280x800 Desktop: Verified layout integrity and consistent neobrutalist shadows.
    - 768x1024 Tablet: Verified horizontal top navigation and scrollable tables.
    - 390x844 Mobile: Verified zero horizontal page overflow (`clientWidth: 390px, scrollWidth: 390px`).
    - Browser console inspection: 0 console errors logged.
  - End-to-end user interaction script: Verified negotiation modes (Manual & Delegate), co-pilot draft suggestions, manual sandbox sending, simulated customer reply, and simulated payment link generation.
- **Limits / next:** Razorpay and WhatsApp remain SIMULATED/sandboxed in compliance with safety requirements; monetary math remains authoritative on the server.

### 2026-10-27 — Codex — Accounting, evidence, workflow, and safety foundations

- **Objective:** Repair the defects identified in the project analysis, using SQLite for this run, while preserving the existing synthetic demo and other agent's frontend styling and evaluation edits.
- **Changed:** Added exact `Money` storage and a versioned schema upgrade; separated cash, credits and outstanding; added explicit payment/credit dispute allocation and linked reversals; made inconsistent legacy cases reviewable and repairable; expanded line-level investigation and staff review for contradictory or ambiguous evidence; added common case lifecycle checkpoints; rechecked controlled-agent and negotiated offer context; broadened input and outbound policy checks. Updated the case screen for credits, allocations, investigation, and reviewed-source decisions. Updated the README and `docs/foundations-2026-10-27.md`; marked the older architecture document as historical. Files are recorded in this worktree's diff.
- **Verification:** `python -m pytest -q --disable-warnings` passed 81 tests with one existing pytest-asyncio configuration warning. Fresh and legacy SQLite migrations completed twice; legacy REAL money was converted to exact decimal text. `python scripts/demo_hero.py` completed all seven steps with SIMULATED payment and expected ₹30,000 dispute. A local FastAPI run returned 200 for health, UI, and authenticated cases. In the browser, a synthetic ₹1,000 credit appeared separately from ₹1,50,000 cash received and reduced outstanding to ₹89,000; no console errors were reported. `node --check frontend/app.js` and `git diff --check` passed. The isolated test server was stopped and its test database removed.
- **Limits / next:** No live PostgreSQL, Gemini, Razorpay, WhatsApp, or production data was used. Historical payment allocations that lack metadata need staff reconciliation. Further multilingual adversarial evaluation and real document field trials are needed; the guards are not a proof of injection immunity. Existing evaluation and frontend style changes from Antigravity were preserved.

### 2026-10-27 — Antigravity — Navigation view switching fix and comprehensive end-to-end feature verification

- **Objective:** Fix sidebar navigation where `#view-upload` remained permanently visible across all tabs due to missing `.view` and `.hidden` display rules, and thoroughly test every single feature across Intake, Review and Negotiate, and Control.
- **Changed:**
  - `frontend/styles.css`: Added strict view visibility rules (`.view { display: none !important; }`, `.view.active { display: block !important; }`, `.hidden { display: none !important; }`).
  - `frontend/app.js`: Updated `navigate()` so it synchronizes both `.active` and `.hidden` classes when toggling views.
- **Verification:**
  - Browser Playwright automation with Edge (`scratch/test_all_features.py`):
    - View isolation: Intake displays `#view-upload` only; Review displays `#view-cases` only; Control displays `#view-control` only.
    - Intake: Multi-file drag-and-drop file upload, processing queue status, and tracker verified.
    - Review & Negotiate: Case queue search filtering, case file opening (`INV-2026-HERO`), 5-metric split balance verification (₹2,40,000 / ₹150,000 / ₹90,000 / ₹30,000 / ₹60,000), clickable interactive source chips, controlled agent proposal & versioned draft approval, Manual vs. Delegate negotiation modes, co-pilot draft generation, sandbox message dispatch, simulated customer reply, simulated payment link generation, and case close action.
    - Control: Autonomy policy mode switching & save, Gemini slot assignment monitor, sandbox outbox rendering, mini evaluation summary rendering, and legacy manual invoice tool.
  - Ran backend test suite: `py -3.12 -m pytest -q --disable-warnings` (81 passed, 0 failures in 22.80s).
  - Syntax checked JavaScript: `node --check frontend/app.js` (passed with code 0).
  - Verified `git diff --check` with zero errors.
- **Limits / next:** Razorpay and WhatsApp remain SIMULATED/sandboxed per safety boundaries.

### 2026-10-28 — Muse Code — Build step 1 baseline: analyse, run app, gap list

- **Objective:** Analyse the project, run the application, fix any errors, and report what implementations are lacking, starting from `.codex`.
- **Changed:** No application code changed. Removed my own stray `pytest-of-Lakshya Arora/` temp dir from the repo root. Updated this handoff only.
- **Verification:** `python -m pytest tests/ -q --disable-warnings` with Anaconda Python 3.12 unsandboxed: 81 passed. Sandboxed runs fail 37/81 on WinError 10013 (socket creation blocked; all failures are `socket.socketpair` PermissionError, zero code failures). Live server (user process 37256, port 8002, healthy `{"status":"ok"}`) verified read-only: hero INV-2026-HERO split 240000/150000/90000/30000/60000, 5 source-linked evidence records, 1 agent proposal, 3/3 Gemini slots configured with 15/1500 limits, intake 3 files / 1 case / 2 duplicate-review flags, frontend index 200. `node --check frontend/app.js` and `git diff --check` pass. Hero PDFs present in `docs/` and `frontend/evidence/`.
- **Decisions / limits:** Did not start a second server or touch the user's running process; backend tree matches the running code (only `app.js`/`styles.css` changed after its start, served live from disk). Did not run `demo_hero.py`/`run_evaluation.py` (they rewrite tracked `docs/evaluation.md`); their paths are covered by the 81 tests plus live API checks. Gap list delivered to user: uncommitted foundation tree, no live PostgreSQL/Provider/Gemini-accuracy validation, synthetic-only evaluation, legacy send routes retained but verified sandbox-gated, no in-repo browser smoke test.
- **Next:** Review and commit the dirty foundation tree; run provider/PostgreSQL checks only when those environments are available; rehearse `demo_hero.py` from a clean clone before judging.

### 2026-10-28 — Muse Code — P0 foundations: accounting, lifecycle, trust states, tests, docs

- **Objective:** Implement and verify every P0 roadmap item (accounting/categories, dispute allocation, monetary consistency, canonical lifecycle, evidence trust, regression coverage, honest docs) on a separate port/DB without touching the user's port-8002 app.
- **Changed:** `receivables.py` (currency-mismatch rejection on `post_entry`); `case_lifecycle.py` (documented 7 stages, `derive_stage`/`settle_invoice_status`, status-event guards so drafts/approvals/sandbox never close or reopen, trust-aware fingerprint); `models.py` + `migrations.py` (`CaseEvidence` trust_state/decided_by/decided_at/decision_reason/currency, revision `20261028_trust_states_v2` with conservative backfill: old verified→verified, never accepted); `cases.py` (currency on entries, trust-scoped evidence creation, `POST .../evidence/{id}/review`, credit-aware dispute-review/resume, injection evidence rejected, checkpoint on evidence changes); `intake.py` (confirm-invoice→verified, confirm-receipt→accepted with currency check); `investigation.py` + `intake_pipeline.py` (new claims extracted, never verified); `controlled_agent.py` + `negotiations.py` (checkpoint on approvals); Decimal fixes in `imports.py`, `invoices.py`, `shopify.py`, `reconciliation.py`; `razorpay.py` (webhook currency passed); `app.js`/`index.html` (trust display, Verify/Accept/Reject buttons, allocation + disputed-delta in ledger view; `.view`/`.active`/`.hidden` nav preserved); `seed_hero_case.py` (Decimal, explicit allocation, verified seed trust, full reseed cleanup incl. `case_workflows`); `test_injection.py` (rejected trust); 13 new tests in `test_foundations.py`; `.codex/prompt.md` ("injection-proof"→"injection-resistance" + honesty note); `foundations-2026-10-27.md` (P0 rules/migration/reconciliation procedure); `README.md` (trust-state pointer).
- **Verification:** `py -3.12 -m pytest -q --disable-warnings` 94 passed; `node --check frontend/app.js` + `git diff --check` clean; `demo_hero.py` + `run_evaluation.py` in `%TEMP%\\p0-demo` copy (7 steps pass, 30/30 split, 10/10 triage, 5/10 review; tracked evaluation files untouched); isolated SQLite app on port 8019 — health ok, hero split 240000/150000/90000/30000/60000, live ₹100 credit (outstanding ₹89,900, credits separate), trust accept, dispute review to ₹25,000, opt-out/resume, overpayment 409, nav views served; test server stopped and port freed, user process 37256/port 8002 verified healthy after.
- **Decisions / limits:** No PostgreSQL instance (migration path untested there); no live Gemini/Razorpay/WhatsApp validation; no browser automation this run (nav covered by static regression test + served-HTML checks). Fixed a real reseed FK bug found during verification. Other agents' uncommitted work preserved; pre-existing `docs/evaluation.md` + `frontend/evaluation.*` diffs untouched.
- **Next:** Review and commit the dirty tree; run PostgreSQL-backed migration test when a server exists; rehearse demo from a clean clone before judging.

### 2026-10-28 — Muse Code — P1 Milestone 1: supervisor, specialists, durable execution

- **Objective:** Build P1 M1 (deterministic supervisor, 6 specialist contracts, durable tasks, review-gate API) after verified P0, extending existing services.
- **Changed:** New `app/services/specialists.py` (typed output contract, tool gateway with per-specialist allowlists, 13 read/write-scoped tools, 6 runners wrapping intake/investigation/matching/split/draft paths; model use is classification-only in M1) and `app/services/supervisor.py` (deterministic `select_next`, idempotent reassess, executor with retries/budgets/stale-rejection, `COMPLETION_RULES`/`ESCALATION_RULES` in one place, crash recovery, pause/resume/retry). New `SupervisorTask` model + migration `20261029_supervisor_v3`; new `app/api/supervisor.py` (reassess, history, pause/resume/retry/run, run-due) registered in router. `intake_pipeline` refactored to `claim_job`/`process_job` (behavior preserved) for session-injectable intake tasks. Triggers in `post_entry`, reply/dispute/evidence/resume, approvals (agent/dunning/negotiation), intake `_advance`, and upload (intake task per upload). `main.py` runs recovery + supervisor loop with clean shutdown. `tests/test_p1_supervisor.py` (13 tests: contract, allowlist, budgets, idempotency, chain, stale, exhaustion, crash, API gates, trigger, intake-link, blocked, deps). `docs/supervisor.md`. Migration-count test bumped to 3.
- **Verification:** `py -3.12 -m pytest -q --disable-warnings` 107 passed; `git diff --check` clean (`node --check` not run — no JS changed). Isolated-copy `demo_hero.py` passes (audit lines grew 48→61 from supervisor rows; printed, not asserted). Live port-8019 isolated-DB app: reassess→run-due→background loop completed resolution→communication→verification to `steady`, ledger untouched (₹90,000 outstanding), pause/resume gates correctly 409 on terminal tasks; server stopped, port freed, user process 37256 healthy.
- **Decisions / limits:** Intake tasks are upload-scoped until linked; escalations hold contact via `investigation_hold` (has a staff clear path). No ledger/post/approve/send tools exist, so unauthorized financial action fails closed. M1 wording is deterministic template only; multilingual model wording is M4. No PostgreSQL/live-model validation (no instances).
- **Next:** M2 — evidence-led investigation (line-level links, competing explanations, clarification tasks) on top of the M1 task framework.

### 2026-10-28 — Muse Code — P1 Milestone 2: evidence-led investigation

- **Objective:** Line-level evidence links, no silent unit/tax/freight handling, competing explanations, clarification tasks, stage separation.
- **Changed:** New `app/services/line_matching.py` (pure SKU/unit/qty/price/tax/freight/rounding comparison; hypotheses need positive evidence). `investigation.py` extended (explanation + clarification persistence with upsert/supersede, staff unit-rule conversion, multi-SKU message attribution, damage-claim allegations, duplicate-skip by content hash, unreadable-doc path; existing messages and claim behavior preserved). New models `CompetingExplanation`/`ClarificationTask`/`UnitRule` + migration `20261030_investigation_v4`. `cases.py`: explanations + clarifications in case view; resolve/create/fulfill/unit-rule endpoints with reassess triggers. `specialists.py`: investigation findings carry explanations/clarifications, verification checks them, resolution notes open clarifications. `seed_hero_case.py` reseed cleanup extended. `tests/test_p1_m2_investigation.py` (15 tests: contradictory PO, multi-SKU, tax, freight, units, duplicates, unreadable, overturned proposal, sourceless, damage, stage separation, API lifecycles, pure rules). `docs/investigation.md`. Vision schema untouched (no new document type needed).
- **Verification:** `py -3.12 -m pytest -q --disable-warnings` 122 passed; `git diff --check` clean (`node --check` not run — no JS changed); isolated-copy `demo_hero.py` passes with identical story numbers. API behavior covered via TestClient; no live-server run this milestone (M1 covered the loop).
- **Decisions / limits:** Tax-basis hypothesis requires variance == stated tax exactly plus total fit; scheme hypothesis requires a matching scheme line. Escalations still hold via `investigation_hold`; explanation resolution never moves money. No PostgreSQL/live validation.
- **Next:** M3 — payment allocation (one-to-many, many-to-one, scored candidates, ambiguity) + nonfinancial promise tracking.

### 2026-10-28 — Muse Code — P1 Milestone 3: payment allocation and promises

- **Objective:** Candidate allocation of transfers across invoices with ambiguity held for staff, plus nonfinancial promise tracking.
- **Changed:** New `app/services/allocation.py` (explainable scoring: reference/payer-alias/amount/date + uncertainty; greedy leg drafts; guarded approval through `post_entry`; residuals; idempotent propose/approve/reject) and `app/services/promises.py` (rules extraction with confidence, confirm/remind/cancel, kept/broken refresh on postings). Models `AllocationProposal`/`AllocationLeg`/`PayerAlias`/`PromiseToPay` + migration `20261031_allocation_v5`. New `app/api/allocations.py` (unmatched transfers, proposals, approve/reject, aliases) + promise endpoints in `cases.py` + promises in case view. `post_entry` refreshes promises; supervisor reconciliation triggers on pending legs and escalates ambiguous proposals; resolution notes open promises. `tests/test_p1_m3_payments.py` (13 tests: split, multi-transfer, duplicates, reversal, ambiguity, tenant/currency, aliases, reasons, promise broken/kept, promise isolation, specialist escalation, Razorpay unconfigured, extraction rules). `docs/payments.md`. Payments/webhooks untouched (SIMULATED preserved).
- **Verification:** `py -3.12 -m pytest -q --disable-warnings` 135 passed; `git diff --check` clean (`node --check` not run — no JS changed); isolated-copy `demo_hero.py` passes with identical story numbers. API covered via TestClient.
- **Decisions / limits:** AFIS has no tenant/currency columns, so proposals record both explicitly; multi-tenant AFIS files are future work. Ambiguous proposals require explicit staff legs. Reversed legs stay applied-history. No PostgreSQL/live validation.
- **Next:** M4 — multilingual classification/drafting, owner queue + activity view, accounting import adapter (needs user's sanitized export before claiming system support).

### 2026-10-28 — Muse Code — P1 Milestone 4: multilingual communication, owner queue, import adapter

- **Objective:** English/Hindi/Hinglish classification and validated drafting, owner action queue + agent activity view, provider-neutral accounting import adapter.
- **Changed:** New `app/services/multilingual.py` (rules detection, structured message build/check/render/validate, approval-time `verify_outbound_body`; ~600 elective-Hindi markers, goods/address/Indian-English/name exclusions documented); `negotiation.py` classifier extended multilingual; communication specialist builds structured message from server facts, template default with opt-in `model_wording` rephrasing fact-free carriers only; approval-time verification wired into controlled-agent/dunning/negotiation approvals. New `app/services/action_queue.py` + `GET /api/v1/supervisor/queue` (next action per case: action/reason/owner/deadline/amount/uncertainty/source/approval). Frontend Control panels `owner-queue` + `agent-activity` with mobile CSS. New `app/services/import_adapter.py` + rewritten `app/api/imports.py` (profiles/preview/confirm, `generic_csv` only, idempotent, staff-confirmed; legacy CSV path preserved). Live-verification fixes: extended Hinglish markers (everyday Hinglish was detected as English); new `_supersede_proposed_drafts` in `cases.py` called from dispute-review and resume so staff review marks older proposed drafts `stale` (freshness check would 409 them anyway) instead of verification failing forever. `tests/test_p1_m4_communication.py` (14 tests) + 1 M1 test (staff review supersedes stale drafts, verification passes). `docs/communication.md`, `docs/import-adapter.md`, `docs/supervisor.md` supersede note.
- **Verification:** `py -3.12 -m pytest -q` 149 passed; `node --check frontend/app.js` clean; `git diff --check` clean; isolated-copy `demo_hero.py` passes with identical story numbers. Live port-8019 isolated-DB app: clarification appeared in queue; resolution->communication->verification chain to steady; Hinglish reply recorded, contact paused then staff-resumed, chain produced Hinglish draft (undisputed INR 60,000 only, disputed INR 30,000 carved out with negation, template engine); stale-draft escalation held correctly, then staff dispute-review superseded old proposals and the next chain verified 5/5 clean; import preview/confirm/reconfirm idempotent live; served HTML contains both panels with loader. Server stopped, 8019 freed, user process 37256 on 8002 healthy.
- **Decisions / limits:** No multilingual reliability claim beyond tested keyword/template coverage (M5 measures). No Tally/Busy/Zoho claim; sanitized export from first target business still required. Automatic triggers never supersede drafts; only staff review/resume do. Known tradeoff: verb `kar` can flip English text mentioning surname Kar (bounded by staff approval). No PostgreSQL/live-model/live-payment validation. Tree still dirty (~71 files).
- **Next:** M5 — held-out synthetic + adversarial evaluation (rules-only vs single-agent vs specialist workflow), expanded one-command showcase, hero demo as regression. Then review/commit the dirty tree.

### 2026-10-28 — Muse Code — P1 Milestone 5: comparative evaluation, failure testing, showcase

- **Objective:** Held-out + adversarial three-arm evaluation, expanded one-command showcase, architecture/walkthrough docs, whole-project README.
- **Changed:** New `scripts/p1_eval_cases.py` (24 held-out seed 20261028 + 14 adversarial seed 20261117, generator-computed ground truth), `scripts/p1_eval_arms.py` (rules/single/specialist arms on fresh DBs), `scripts/run_p1_evaluation.py` (scores requested/dispute/escalation/allocation/unsupported/unsafe/corrections/latency/cost with Wilson intervals; writes `docs/p1-evaluation.md` + `frontend/p1-evaluation.json`, forced offline). Failure-testing fixes: `investigation.py` skips zero-amount claims (full delivery no longer overlaps price claims) and dedups damage allegations (was appending a row per run, stalling the supervisor loop forever); `promises.py` parses ISO dates literally. New `scripts/demo_p1_showcase.py` (9-beat offline story, asserts, writes nothing), `docs/showcase-walkthrough.md`, P1 section in `docs/architecture.md`. `tests/test_p1_m5_evaluation.py` (7 tests) + 2 M2 regression tests. README updated for the whole project (still one page).
- **Verification:** Full suite 158 passed; `node --check` and `git diff --check` clean; isolated-copy `demo_hero.py` passes (regression retained); showcase passes all beats; P1 eval ran 38 cases x 3 arms offline (model configured=True in env, forced off, recorded). Measured: dispute/allocation tie single=specialist perfect; single leads held-out escalation 28/28 vs 22/28 (legless-ambiguous-trigger gap); specialist alone catches sourceless/stale cases; rules carries the only unsafe action (cross-currency leg); all arms request against unapplied clear transfers (shared finding); specialist ~4x single latency; 0 model calls everywhere. No scores hard-coded; failures listed per case in the report.
- **Decisions / limits:** Ground truth fixed before arms ran (withhold requests on holds/quarantines/unknown payers/unapplied money). No multilingual-reliability or multi-agent-advantage claim: intervals overlap, samples small, run offline. Open follow-ups: legless ambiguous proposals never queue reconciliation; no specialist extracts promises; legacy 5%-fuzzy matcher escalated 2 clear splits. No PostgreSQL/live-model/live-payment validation. Tree still dirty (~80 files).
- **Next:** Review/commit the dirty tree; run PostgreSQL-backed migration when a server exists; rehearse both demos from a clean clone; get the sanitized accounting export before claiming vendor support.

### 2026-10-28 — Muse Code — P1 final checklist (roadmap items)

- M1 supervisor/contracts/durable execution/API/triggers/budgets/recovery: implemented + tested (14 M1 tests, live chain verified).
- M2 line links, no silent unit/tax/freight, competing explanations, clarifications, stage separation: implemented + tested (17 M2 tests incl. 2 M5-found regressions).
- M3 one-to-many/many-to-one allocation, scored candidates, ambiguity held, tenant/currency/idempotency guards, SIMULATED Razorpay, nonfinancial promises: implemented + tested (13 M3 tests).
- M4 en/hi/Hinglish classify/draft, structured message + triple validation, approval-time verification, owner queue + activity view, generic_csv import adapter: implemented + tested (14 M4 tests, live verified). Vendor formats (Tally/Busy/Zoho): blocked, needs sanitized export.
- M5 held-out + adversarial sets, three-arm comparison on all listed measures, expanded showcase, walkthrough, architecture explanation, hero regression: implemented + tested (7 M5 tests). Live-model advantage: blocked, needs measured Meta run (env has a key; eval forced offline by design).
- Running the agent: `python -m venv`, install requirements, `seed_hero_case.py`, `python run.py` on 8002 with `RECOVERFLOW_API_KEY`; demos via `demo_hero.py` / `demo_p1_showcase.py`; evals via `run_evaluation.py` / `run_p1_evaluation.py`.

### 2026-10-28 — Muse Code — Meta Model API swap (full Gemini replacement)

- **Objective:** Per explicit user request for the Meta hackathon: route every model call through Meta's Muse Spark (`muse-spark-1.3`) via the Meta Model API, including multimodal extraction. Full replacement, no Gemini fallback.
- **Changed:** New `app/services/meta_agent.py` (OpenAI-compatible `POST {base}/chat/completions`, Bearer auth, `json_object` responses; same interface and slot architecture as before: configured/generate/classify_intent/safe_reply/chat/get_rate_limit_status, 3 role slots, 15 RPM / 1500 RPD per-slot caps, UTC day reset). Deleted `app/services/gemini_agent.py`. Config: `META_MODEL_API_KEY` / `META_API_KEY_1..3` / `META_API_BASE_URL` (= `https://api.meta.ai/v1`) / `META_ROLE_MAP_JSON` / reserves / limits; `AGENT_MODEL` default `muse-spark-1.3`; model id must match `muse-*`. Vision extraction now sends images as `image_url` data URLs and PDFs as `file` parts, with `json_object` mode and unchanged server validation. Repointed callers (controlled agent service+API, specialists, negotiations, intake pipeline) and all tests/scripts/docs/frontend labels; `.env` `AGENT_MODEL` updated (old Gemini keys left untouched in `.env`); prompts name the exact JSON shape since `json_object` carries no field schema.
- **Verification:** Live key verified: classify (valid labels), generate (validates, sensible empty-draft behavior), PNG vision (transport + JSON + server validation + low-confidence staff fallback), PDF vision (file part read the invoice number). Full suite 158 passed; `node --check` and `git diff --check` clean; isolated hero demo passes; showcase passes; P1 report regenerated offline with identical behavior and no Gemini remnants. Repo-wide sweep: no `gemini|GEMINI|generativelanguage|x-goog` left outside generated `docs/evaluation.md` / `frontend/evaluation.*` (refresh on next demo run) and one intentional history note in `.codex/prompt.md`.
- **Decisions / limits:** Single Meta key maps through the legacy-key path (works; slots 1-3 ready for more keys). Timeouts raised for reasoning latency (30s text, 60s vision). Daily reset moved PT->UTC (Meta reset window undocumented). Live-model eval advantage still unmeasured (runner forces offline by design); rerun P1 eval with keys enabled to measure it. Tree still dirty.
- **Next:** Review/commit the dirty tree; restart the port-8002 app to pick up the swap; optionally run a keys-enabled P1 eval to measure live-model behavior.

### 2026-10-28 — Muse Code — README rewrite and .codex sync

- **Objective:** Study the whole project, make the README impressive and understandable, and bring `.codex` files up to the work done.
- **Changed:** Rewrote `README.md` (pitch, two demos, fixed Mermaid node-id collision on the supervisor node, condensed feature table, Meta config, measured-numbers section with P1 citations, grouped docs map; still one page, no emojis). `.codex/handoff.md`: prepended Meta-swap/M5/M4 Current-state bullets (section was stale at M3), moved the dangling "Running the agent" line back under the P1 checklist, appended this entry. `.codex/prompt.md` left unchanged (already Meta-current; brief scope is historical by design).
- **Verification:** 158 tests collected (count cited in README verified); P1 numbers rechecked against `docs/p1-evaluation.md`; every README doc link verified to exist; `git diff --check` clean. No code changed, so no suite/demo rerun (last full run: 158 passed).
- **Decisions / limits:** Older handoff entries kept verbatim as history; stale model references in old bullets are superseded by the new top bullets. README claims stay inside measured evidence (synthetic fixtures only).
- **Next:** Review/commit the dirty tree; restart the port-8002 app to pick up the Meta swap.

### 2026-10-28 — Antigravity — Port audit, live DB backup, and safe restart of port-8002 app

- **Objective:** Audit listening ports and Python processes across the machine; verify port 8002 listener; safely back up the live database and its sidecars; terminate only the verified repo-serving Python process; restart the application on current working tree code; verify health, authenticated case API, frontend navigation, Meta agent init, migration consistency, and absence of Gemini import errors; confirm no orphan test servers remain.
- **Changed:**
  - Backed up live database `apex_ar.db` along with `-wal` and `-shm` sidecars to `backups/apex_ar-20261028-2331.db`, `backups/apex_ar-20261028-2331.db-wal`, `backups/apex_ar-20261028-2331.db-shm`.
  - Stopped stale Python PID 37256 (`"C:\Users\Lakshya Arora\Documents\anaconda\python.exe" run.py`, cwd `C:\Users\Lakshya Arora\Documents\GitHub\RecoverFlow-AI`, started 2026-10-27 22:39) gracefully.
  - Restarted live server via `python run.py` on current working-tree code under PID 33808.
  - No application code, `.env`, or database records modified; no git commits, resets, or stashes made.
- **Verification:**
  - Port & Process Audit: Before restart, port 8002 was held by PID 37256 (cwd matched repo root). Sibling services on ports 8000 (AFIS) and 8001 (AXIS) were not listening and left untouched. Port 8019 was empty (0 listeners). System/unrelated listening ports (135, 139, 445, 1521, 3306, 5040, 6463, 7680, 8080, 9222, 19292, 33060, 42050, 49664-49680, 53896-65191) were mapped and left untouched.
  - Backup: Verified backup files exist on disk: `apex_ar-20261028-2331.db` (102,400 bytes), `apex_ar-20261028-2331.db-shm` (32,768 bytes), `apex_ar-20261028-2331.db-wal` (3,275,432 bytes).
  - Stop Target: Terminated PID 37256 gracefully; verified port 8002 was cleanly freed before restart.
  - Fresh Startup: Server started on PID 33808. Port 8002 listening verified. Old PID 37256 verified gone. Exactly 1 repo-serving Python process active.
  - Health check: `GET http://127.0.0.1:8002/api/v1/system/health` returned HTTP 200 `{"status":"ok","service":"RecoverFlow"}` (31.28 ms).
  - Authenticated Case API: `GET http://127.0.0.1:8002/api/v1/cases/1` using `X-RECOVERFLOW-API-KEY` returned HTTP 200 (44.23 ms), status `disputed`, invoice `INV-2026-HERO`, split: total ₹2,40,000 / received ₹1,50,000 / credits ₹0 / outstanding ₹90,000 / disputed ₹30,000 / undisputed ₹60,000, 5 evidence records.
  - Frontend: `GET http://127.0.0.1:8002/` returned HTTP 200 (22,081 bytes) with Intake, Review and Negotiate, and Control navigation present.
  - Meta Agent & Schema Migrations: `GET http://127.0.0.1:8002/api/v1/agent/status` returned HTTP 200, `model: "muse-spark-1.3"`, `model_configured: true`. Database revisions verified applied: `20261027_foundations_v1`, `20261028_trust_states_v2`, `20261029_supervisor_v3`, `20261030_investigation_v4`, `20261031_allocation_v5`; `PRAGMA foreign_key_check` returned 0 violations.
  - Clean Logs: Startup log shows clean uvicorn initialization (`Started server process [33808]`, `Starting RecoverFlow...`, `Application startup complete`). Zero `gemini` references or import errors.
  - Orphan Sweep: Port 8019 verified free. Zero orphan test processes found.
- **Decisions / limits:** No live Razorpay, WhatsApp, or PostgreSQL access used (payments remain SIMULATED). Tree remains dirty as requested (uncommitted work preserved). Rollback target remains `backups/apex_ar-20261028-2331.db`.
- **Next:** Review uncommitted tree changes; test Meta model extraction with live provider traffic if desired; rehearse demo scripts prior to hackathon presentation.

### 2026-10-29 — Codex — P2 implementation prompt refresh

- **Objective:** Prepare a repository-specific execution prompt for all 17 P2 roadmap items requested by the user, with staged delivery and verifiable acceptance criteria.
- **Changed:** Documentation handoff only. The detailed copy-ready prompt was supplied in the chat; no application code, configuration, database, or live integration was changed.
- **Verified:** Read `AGENTS.md`, `.codex/prompt.md`, this handoff, `README.md`, and current service/API/docs inventory. `git status --short` was clean before this entry. Cross-checked official Razorpay, Tally, Zoho Books, CBIC GST, and MeitY sources for provider and policy research pointers. Tests were not run because this iteration changes only documentation.
- **Decisions / limits:** The new P2 request extends the older hackathon scope in `.codex/prompt.md`; its financial-action and customer-contact approval gates still apply until the user explicitly authorizes live activation. A future implementation agent must obtain a sanitized pilot accounting export, chosen provider/accounts, consented pilot access, and PostgreSQL test instance before claiming those paths were tested in the real world. Existing port-8002 app and database were not touched.
- **Next:** Execute the staged P2 prompt against isolated test infrastructure, beginning with a baseline and gap matrix. Record each milestone here after implementation and verification; distinguish implemented/tested, mocked, and blocked work.

### 2026-10-29 — Muse Code — P2 baseline verification and gap matrix

- **Objective:** Verify the reported 158-test baseline, run the offline showcase isolated, and map all 17 P2 workstreams from code before implementing Milestone A.
- **Changed:** Added `docs/p2-gap-matrix.md` (17 rows: existing/missing/files/deps/tests/external-input/status). No application code changed.
- **Verification:** `py -3.12 -m pytest -q --disable-warnings` → 158 passed in 57.9s; `py -3.12 scripts/demo_p1_showcase.py` → all beats pass in-tree (verified it writes nothing); `scripts/demo_hero.py` → passes in `%TEMP%\p2-baseline-demo` robocopy (30/30, 10/10, 5/10; tracked `docs/evaluation.md` + `frontend/evaluation.*` untouched). Read models/migrations/db_manager/money/auth/config/main/razorpay/whatsapp/intake/imports/action-queue; tenant heatmap over all 20 route files. Port-8002 live app and DB untouched.
- **Decisions / limits:** PG status is honestly unverifiable here: no `psql`/`pg_ctl`, no psycopg driver installed or pinned, no instance — A1 will document + test SQLite only. Findings for later milestones: webhooks hard-code `tenant_id == "local"`; `frontend/evidence/*.pdf` is public static; `require_editor`/`require_viewer` unused; provider credentials are global settings, not per-tenant.
- **Next:** Milestone A — A1 migration status + backup/restore drill + tests, then A2 tenancy audit + secret store + negative tests, A3 auth hardening, A4 team ops.

### 2026-10-29 — Muse Code — P2 A1: database operations

- **Objective:** Migration status, upgrade/transaction/constraint tests, backup procedure + restore drill, honest PostgreSQL report.
- **Changed:** `app/database/migrations.py` (`status()` + wrap raw `InvalidOperation` as `ValueError`); `app/api/system.py` (admin `GET /system/migrations`, no URL leak); new `scripts/db_backup.py` (online backup/verify/restore, overwrite refusals, pg template); new `docs/ops-backup.md`; new `tests/test_p2_a1_db.py` (11 tests); `docs/p2-gap-matrix.md` A1 row marked done-on-SQLite.
- **Verification:** `tests/test_p2_a1_db.py` 11 passed; `git diff --check` clean. Full suite rerun deferred to the Milestone A gate.
- **Decisions / limits:** PG path reviewed (advisory lock, NUMERIC, partial indexes all valid) but never executed — no `psql`, no driver, no instance; doc states PG 15+ target + deployment steps and forbids claiming PG support. SQLite-only init was already excluded from the PG path (verified by inspection, no change needed). No live DB touched.
- **Next:** A2 — per-tenant secret store + migration, webhook tenant binding, cross-tenant negative tests, evidence-file privacy fix.

### 2026-10-29 — Muse Code — P2 A2: tenant isolation

- **Objective:** Audit every tenant surface, add per-business credentials, bind webhooks/AFIS per tenant, close the public evidence files, and prove isolation with negative tests.
- **Changed:** `models.py` + migration `20261101_tenancy_v6` (`tenant_secrets`, `tenant_settings`; foundations count 5→6); new `app/services/tenant_config.py` (env/file secret refs, allowlisted settings, local fallback); `AFISReader(db_path=...)` + per-tenant resolution in allocation/specialists; explicit-secret params on the three provider verify functions + per-tenant phone check; `webhooks.py` per-tenant binding; `integrations.py` secret/setting admin endpoints + per-tenant status; `invoices.py` two hardened lookups; `cases.py` authed evidence-file endpoint; `frontend/app.js` blob-fetch repoint; deleted `frontend/evidence/*.pdf`; `scripts/p1_eval_cases.py` sets eval5 AFIS path; new `tests/test_p2_a2_tenancy.py` (15 tests); new `docs/tenancy.md`; gap matrix A2 done + D3 correction (24h window already enforced).
- **Verification:** New 15 pass; full suite 184 passed; `node --check frontend/app.js` clean; `git diff --check` clean (this entry's check below).
- **Decisions / limits:** Legacy LangGraph orchestrator keeps its safe local-only AFIS gate (documented, not rewired). `local` falls back to global settings so the pilot DB needs no migration of behavior. Production vault/KMS still future work. No live DB touched.
- **Next:** A3 — login throttling, recovery, session rotation, permission matrix + role wiring.

### 2026-10-29 — Muse Code — P2 A3: production authentication

- **Objective:** Throttle logins, add recovery + rotation, gate money/admin actions, and document the role matrix.
- **Changed:** `models.py` + migration `20261102_auth_v7` (`login_attempts`, `user_recovery_tokens`; count 6→7); `auth_security.py` recovery tokens; `api/auth.py` (throttle in login, rotate/sessions/revoke/revoke-all/recovery endpoints); `main.py` public `/auth/recover`; inline admin gates on manual entries, allocation approve, reconciliation approve, receipt confirm (matching the file convention of reverse/resume); new `tests/test_p2_a3_auth.py` (9 tests); new `docs/auth-permissions.md`; gap matrix A3 done.
- **Verification:** New 9 pass; full suite 193 passed (no regressions from the new admin gates — all existing callers use admin keys).
- **Decisions / limits:** Message approvals stay editor-accessible; their stronger check is SoD in A4 plus exact-version + server re-verification. Invoice review (data correction, no posting) stays editor. Throttle uses naive UTC consistently for SQLite/PG comparability. No live DB touched.
- **Next:** A4 — assignment, staff notes, escalation deadlines, workload views, SoD enforcement.

### 2026-10-29 — Muse Code — P2 A4: team operations + Milestone A gate

- **Objective:** Assignment, notes, tasks, escalation deadlines, workload views, and SoD on sensitive approvals; then run the Milestone A gate.
- **Changed:** `models.py` + migration `20261103_team_v8` (`case_assignments`, `staff_tasks`, `staff_notes`, `case_escalations`; count 7→8); new `app/services/team_ops.py` (insert-only history, sweep, workload, `sod_allows` with lone-operator rule); new `app/api/team.py` + router registration; SoD wired into allocation/agent-draft/dunning/negotiation approvals (fail-fast placement); dunning authorship stamping on trigger/edit; escalations surface first in `action_queue`; new `tests/test_p2_a4_team.py` (12 tests); new `docs/team-ops.md`; gap matrix A4 done.
- **Verification:** New 12 pass; gate: full suite 205 passed; P1 showcase passes in-tree; hero demo passes in fresh `%TEMP%\\p2-milestoneA-demo` copy (30/30, 10/10, 5/10; audit lines 61→62 from one SoD lone-skip note, printed not asserted); tracked eval files untouched per `git status`; `git diff --check` exit 0; live port-8002 app/DB untouched.
- **Decisions / limits:** SoD blocks self-approval only with ≥2 active users; solo tenants proceed with a `sod_skipped_lone_operator` audit note (keeps the pilot + demos working, conflict still tested). Reversals/resume were already admin-gated (left as-is). PG remains honestly unverified. No browser QA this milestone (frontend change is the A2 blob-fetch repoint, syntax-checked + served-HTML-covered pattern).
- **Next:** Milestone B — B1 counterparty identity (GSTIN, branches, merge), B2 Indian document model (CBIC/e-invoice check first), B3 installment schedules.

### 2026-10-29 — Muse Code — P2 B1: business identity

- **Objective:** Legal/display names, GSTIN, branches, addresses, external IDs, explainable duplicates, staff-confirmed merges, import matching.
- **Changed:** `models.py` (Counterparty extension + branches/external-ids/merges tables + `Invoice.counterparty_id`) with migration `20261104_identity_v9` (incl. portable partial unique index for GSTIN); new `app/services/counterparties.py` (format-only GSTIN, difflib duplicates, merge/bootstrap/link); new `app/api/counterparties.py` + router; import auto-link in `confirm_import`; party block in case `_summary`; new `tests/test_p2_b1_identity.py` (12 tests); new `docs/identity.md`; gap matrix B1 done.
- **Verification:** New 12 pass. Full-suite rerun deferred to the Milestone B gate.
- **Decisions / limits:** rapidfuzz is pinned but not installed — used stdlib difflib per codebase convention instead of touching the user env. Removed two provably-dead branches (same-tax-ID scoring, merge external-clash check) after DB uniques made them unreachable. GSTIN checksum/registry verification explicitly out of scope. CBIC Rule 46 + e-invoice schema fetched from official pages to ground B1/B2 field design. No live DB touched.
- **Next:** B2 — Indian document model (line items, GST split, challans, credit/debit notes, freight/returns/scheme docs, six fixtures).

### 2026-10-29 — Muse Code — P2 B2: Indian document model

- **Objective:** Persisted lines, GST components, challans, credit/debit notes, freight/returns/scheme handling with source links; six exact-reconciliation fixtures.
- **Changed:** `models.py` (`invoice_line_items`, `credit_debit_notes`, `supporting_documents`, invoice tax/freight columns) + migration `20261105_documents_v10`; `receivables.py` debit kind + debit-aware split/consistency + reversal-of-debit; `vision_extraction.py` 5 new doc types + GST fields + split reconciliation; `intake_pipeline.py` persists lines/split/notes/support docs; `investigation.py` persisted-first lines, challan/scheme mapping, freight branch, enriched tax figures; new `app/services/documents.py` + `app/api/documents.py` (notes accept/post/cancel, manual lines, reads) + case-detail blocks; new `tests/test_p2_b2_documents.py` (15 tests); new `docs/documents.md`; matrix B2 done.
- **Verification:** New 15 pass; full suite 232 passed (ledger change regression-clean).
- **Decisions / limits:** Tax-inclusive line pricing fails strict intake validation by design — staff records those lines manually (verified status) instead of the system guessing. Tax/freight apportionment stays staff-decided; clarifications now state exact figures. Debit notes post unallocated (fresh debt). No tax-compliance claim without accountant review. No live DB touched.
- **Next:** B3 — installment schedules (legs, payment application, late/missed/reschedule/cancel/reversal, schedule-vs-ledger split).


### 2026-10-29 - Muse Code - P2 B3: installment lifecycle + Milestone B gate

- **Objective:** Accepted installment schedules with per-leg due dates/amounts/status, waterfall payment application, late/missed/reschedule/cancel/reversal handling, schedule-vs-ledger split; then run the Milestone B gate.
- **Changed:** `models.py` (`installment_schedules`, `installment_legs`, `installment_applications`) + migration `20261106_installments_v11`; new `app/services/schedules.py` (create/approve/cancel/reschedule, waterfall apply, reversal un-apply with reopen, read-time late/missed flags); new `app/api/schedules.py` (6 endpoints) + router registration; `receivables.py` `post_entry` hook; `cases.py` reverse endpoint now passes `reversal_of_id` (was NULL, broke un-application); new `tests/test_p2_b3_installments.py` (12 tests); new `docs/installments.md`; gap matrix B3 done.
- **Verification:** New 12 pass. Gate: full suite 244 passed (exit 0); P1 showcase passes in-tree (exit 0, no tree writes); hero demo passes in fresh `%TEMP%\p2-b-demo` copy (30/30, 10/10, 5/10; 62 audit records); tracked eval files untouched per `git status`; isolated smoke server on port 8124 + temp DB: health ok, 11/11 migrations applied, invoice->schedule->approve (lone-operator SoD skip)->700 payment->waterfall (leg1 paid 60000, leg2 partial 10000, remaining 30000, case balance 30000); `git diff --check` clean; port-8002 app/DB untouched.
- **Decisions / limits:** Schedules are nonfinancial (approval is not posting); credits/debits never apply to legs; overpay residual stays on ledger; reversals preserve history rows and reopen derived `completed` schedules only (explicit `cancelled` stays terminal); 30-day missed threshold. Two real bugs fixed: missing `reversal_of_id` on the reverse endpoint, and `unapply_entry` re-querying before flush under `autoflush=False` (production session mode) - legs kept paid totals. No live DB touched.
- **Next:** Milestone C - C1 customer response page (scoped short-lived access, dispute->staff review), C2 document security (private storage, auth on every read, quarantine, retention).

### 2026-10-29 - Muse Code - P2 C1: customer response page

- **Objective:** Single-invoice portal: scoped tokens, safe summary, dispute/evidence/payref submissions into staff review, customer page.
- **Changed:** `models.py` (`portal_tokens`, `portal_attempts`, `stored_documents`, `document_access_log`, `customer_messages.source`) + migrations `20261107_portal_v12`/`20261108_docstore_v13`; new `app/services/customer_messages.py` (shared staff/portal recording; `cases.record_reply` refactored onto it, behavior-identical); new `app/services/portal.py` (issue/revoke/verify, 60+200+20 per-15min limits, safe summary) + `app/services/document_store.py` (allowlist/magic-byte/double-extension validation, sha256, random private names, pending-vs-clean scan status); new `app/api/portal.py` (staff token mgmt + 7 public endpoints) + router; `main.py` exempts `/api/v1/portal/` from staff auth (token verified per route) + CORS header; new `frontend/portal.html` + `frontend/portal.js`; new `tests/test_p2_c1_portal.py` (12 tests); new `docs/portal.md`; gap matrix C1 done.
- **Verification:** New 12 pass (`EXIT=0`); `node --check` clean on portal.js + app.js. Full-suite rerun deferred to the Milestone C gate.
- **Decisions / limits:** Portal evidence uploads use the raw-body + x-filename convention (no python-multipart installed; matches intake). No AV engine: portal uploads stay `pending` until staff release (C2 adds the release flow). Token is not staff auth (401 when misused). No live DB touched.
- **Next:** C2 - quarantine/release/hold/delete/retention staff endpoints, access logging on all reads, intake hardening, malicious-upload negatives, then the Milestone C gate.

### 2026-10-29 - Muse Code - P2 C2: document security

- **Objective:** Quarantine/release lifecycle, holds, deletion, retention purge, hashing, access logs, malicious-upload negatives.
- **Changed:** `document_store.py` lifecycle ops (release/quarantine/hold/delete/purge + `doc_view`); `documents.py` staff endpoints (list/download/release/quarantine/hold/delete) with admin gates on release+delete; `system.py` tenant-scoped dry-run-first purge; `intake.py` moved onto the shared validator (messages/codes preserved), SHA-256 on upload, hash-verify + backfill + audit on download; `IntakeUpload.sha256` + migration addition; new `tests/test_p2_c2_documents.py` (10 tests); new `docs/document-security.md`; gap matrix C2 done.
- **Verification:** New 10 pass (`EXIT=0`). Full-suite rerun deferred to the Milestone C gate.
- **Decisions / limits:** Quarantine is the safe direction (any staff); release/delete/purge are admin. Tampered intake bytes return 409. No AV engine wired: `clean` honestly means policy-passed or staff-released, per `scanned_by`. Portal uploads stay `pending` until release. No live DB touched.
- **Next:** Milestone C gate - full suite, both demos, isolated smoke incl. portal page, diff check, handoff.

### 2026-10-29 - Muse Code - P2 Milestone C gate

- **Objective:** Verify C1 + C2 end to end: full suite, both demos, isolated smoke incl. the portal page.
- **Changed:** `tests/test_foundations.py` revision tally 11 -> 13 (v12/v13).
- **Verification:** Full suite 266 passed (exit 0); P1 showcase passes in-tree (exit 0, no tree writes); hero demo passes in fresh `%TEMP%\p2-c-demo` copy (30/30, 10/10, 5/10; 62 audit records); tracked eval files untouched; smoke on port 8125 + temp DB: portal.html 200 with all three forms, invoice -> token -> summary -> dispute -> evidence (pending) -> staff release (clean), summary flips to disputed with 1 submission, migrations current `20261108_docstore_v13` with zero pending; `git diff --check` exit 0; `node --check` clean on portal.js/app.js; port-8002 app/DB untouched.
- **Decisions / limits:** C gate holds: no portal action posts money or approves outcomes; quarantined/deleted docs serve nothing; AV engine still the honest pending item. No live DB touched.
- **Next:** Milestone D - accounting/payment/comms integrations in test mode (D1 needs the sanitized pilot export first; D2/D3 need sandbox accounts + explicit authorization).

### 2026-10-30 - Muse Code - P2 D1: accounting import runs

- **Objective:** Provider-neutral import rails � runs, idempotency keys, provenance, cursor, conflict queue, reconciliation report. No vendor claims.
- **Changed:** `models.py` (`import_runs`, `import_conflicts`) + migration `20261109_import_runs_v14`; `import_adapter.py` run flow (`start_run`/`confirm_run`/`resolve_conflict`/`run_view`); `imports.py` run + conflict-queue endpoints; new `tests/test_p2_d1_import_runs.py` (12 tests); new `docs/accounting-import.md`; gap matrix D1 done-generic/blocked-vendor.
- **Verification:** New 12 pass (`EXIT=0`). Full-suite rerun deferred to the Milestone D gate.
- **Decisions / limits:** Intra-batch self-contradicting files mark the run invalid (source must be fixed); ledger-vs-source mismatches queue as conflicts while clean rows import; re-confirm never duplicates rows or conflicts. Only `generic_csv` exists � Tally/BUSY/Zoho e2e blocked on the sanitized pilot export; unknown profiles get 422. No live DB touched.
- **Next:** D2 - Razorpay live-off hardening (config checks, failure/settlement handling, refund posting, discrepancy queue, event replay), then D3 comms, then the D gate.

### 2026-10-30 - Muse Code - P2 D2: payment hardening behind a live gate

- **Objective:** Disabled-by-default live mode, per-tenant status, failure/settlement handling, refund/chargeback reversal path, discrepancy queue. Mocks only.
- **Changed:** `models.py` (`payment_discrepancies`, `settlement_lines`, event/link `mode`, link `last_error`) + migration `20261110_payments_v15`; `razorpay.py` (live gate in `validate_mode`, event mode, `payment.failed`, settlement parking, `queue_discrepancy`, `status_for_tenant`, `match_settlement`, `resolve_discrepancy`); `webhooks.py` live-mode 503 + mode pass-through; `payments.py` live gate + link mode stamp + status/discrepancy/settlement endpoints; `config.py` `RAZORPAY_LIVE_ENABLED=false`; new `tests/test_p2_d2_payments.py` (15 tests); new `docs/live-payments.md`; gap matrix D2 done-mock/blocked-live.
- **Verification:** New 15 pass (`EXIT=0`). Full-suite rerun deferred to the Milestone D gate.
- **Decisions / limits:** Out-of-order is safe by parking (refund-first queues unlinked; reversal refused until the payment posts). Settlement reports are staff-uploaded matching input, never auto-posting. No sandbox account connected: status honestly mock-tested/sandbox-pending/live-disabled. No live DB touched.
- **Next:** D3 - per-business comms config (templates, consent, quiet hours, language, delivery tracking, reply lifecycle), then the D gate.

### 2026-10-30 - Muse Code - P2 D3: comms policy in sandbox

- **Objective:** Templates, consent, quiet hours, language, delivery tracking, replies into the lifecycle. Live stays off.
- **Changed:** `models.py` (`message_templates`, `comms_preferences`, outbound language/template/delivery/hold columns) + migration `20261111_comms_v16`; new `app/services/comms.py` (IST quiet math, template render, consent gate, delivery apply); `tenant_config.py` + `config.py` quiet/toggle settings; `meta_whatsapp.py` statuses[] receipts; `messages.py` rewritten (triage onto shared lifecycle path, template reply path, template CRUD, preferences, outbound list, hold release, live-or-sandbox send with rollback); new `tests/test_p2_d3_comms.py` (11 tests); new `docs/comms-policy.md`; gap matrix D3 done-sandbox.
- **Verification:** New 11 pass (`EXIT=0`). Full-suite rerun deferred to the Milestone D gate.
- **Decisions / limits:** Templates anchor to triaged threads (cold-proactive needs nullable inbound_id + campaign work � deferred, documented). Quiet holds template sends; direct replies exempt. Triage keeps unconditional suppression and gains checkpoint/reassessment/injection-screening. statuses[] shape verified against current Cloud API docs. No email send endpoint, no SMTP library, non-local live 503. No live DB touched.
- **Next:** Milestone D gate - full suite, both demos, isolated smoke, diff check, handoff.

### 2026-10-30 - Muse Code - P2 Milestone D gate

- **Objective:** Verify D1 + D2 + D3 end to end: full suite, both demos, isolated smoke.
- **Changed:** `tests/test_foundations.py` revision tally 13 -> 16 (v14/v15/v16); `messages.py` reply/release return ORM objects again (controlled_agent calls reply() in-process and needs attributes � regression caught by test_release3, fixed, suite green).
- **Verification:** Full suite 304 passed (exit 0); P1 showcase passes in-tree (exit 0, no tree writes); hero demo passes in fresh `%TEMP%\p2-d-demo` copy (30/30, 10/10, 5/10); tracked eval files untouched; smoke on port 8126 + temp DB: import run start/confirm reconciled, razorpay status mock/test, template draft/approve, migrations current `20261111_comms_v16` with zero pending; `git diff --check` exit 0; port-8002 app/DB untouched.
- **Decisions / limits:** D gate holds with honest states: vendor accounting e2e blocked on the pilot export; payments mock-tested/sandbox-pending/live-disabled; comms sandbox with live off. Note: tool output renders `detail`/`Detail` case unreliably � raw bytes/repr are truth (one D1 test typo caught this way). No live DB touched.
- **Next:** Milestone E - reliable workers (claims/leases/retries/dead-letter) + monitoring/alerts/runbook, then F (privacy/validation/economics).

### 2026-10-30 - Muse Code - P2 E1: durable worker leases

- **Objective:** Atomic multi-worker claims, leases, heartbeats, backoff, dead letters, operator replay; no duplicate money/messages under races.
- **Changed:** New `app/services/worker_lease.py` (conditional-UPDATE claims, steal-expired, heartbeat, deterministic backoff, poison parking, retry/dismiss); lease columns + `elapsed_ms` on intake/supervisor tables + migration `20261112_workers_v17`; `intake_pipeline.py` (lease claims, heartbeat, crash backoff, poison at 3, lease-aware recovery); `supervisor.py` (atomic claim in run_task, transient-vs-poison split, backoff, lease release, dead_letter terminal); `webhooks.py` concurrent-duplicate convergence for Razorpay events; `system.py` operator job endpoints (list/detail/retry/dead-letter resolve); P1 exhaustion test simulates backoff expiry (intended timing change); new `tests/test_p2_e1_workers.py` (11 tests).
- **Verification:** New 11 pass; adjacent suites (P1 supervisor, intake, release2/3, D2 payments) 55 pass. Full suite at the E gate.
- **Decisions / limits:** Attempts count at claim (crash counts as an attempt); poison = 3 unexpected crashes, transients burn the full budget; job list shows error categories only, full error on the audited detail view. Razorpay.py edit was reverted mid-work after a bad splice (file verified pristine at D2 state); convergence lives in the webhook route instead. No live DB touched.
- **Next:** E2 - metrics/alerts endpoints + runbook, then the E gate.

### 2026-10-30 - Muse Code - P2 E2: ops metrics, alerts, runbook

- **Objective:** Counts-and-ages monitoring, 8 alert rules with owners, operator runbook. No customer data.
- **Changed:** New `app/services/ops_metrics.py` (queues, provider events, model calls/latency, delivery, discrepancies, dead letters, alert evaluation); `system.py` metrics/alerts endpoints (tenant-scoped, staff-readable); `config.py` alert thresholds; new `tests/test_p2_e2_ops.py` (4 tests); new `docs/runbook.md`; gap matrix E done.
- **Verification:** New 4 pass (`EXIT=0`). Full suite at the E gate.
- **Decisions / limits:** Metrics carry counts/ages/categories only (planted secrets asserted absent); model cost explicitly not_tracked; alerts are pull; single-tenant ops view. Retry/resolve stay admin; reads are staff.
- **Next:** Milestone E gate - full suite, both demos, isolated smoke, diff check, handoff.

### 2026-10-30 - Muse Code - P2 Milestone E gate

- **Objective:** Verify E1 + E2 end to end: full suite, both demos, isolated smoke.
- **Changed:** `tests/test_foundations.py` revision tally 16 -> 17 (v17).
- **Verification:** Full suite 319 passed (exit 0, first run); P1 showcase passes in-tree (exit 0, no tree writes); hero demo passes in fresh `%TEMP%\p2-e-demo` copy (30/30, 10/10, 5/10); tracked eval files untouched; smoke on port 8127 + temp DB: invoice create, jobs list, all 6 metric sections, 8 alerts all ok on fresh state, migrations current `20261112_workers_v17` with zero pending; `git diff --check` exit 0; port-8002 app/DB untouched.
- **Decisions / limits:** E gate holds: exactly-once claims proven under threads, poison parks at 3 crashes, webhook duplicates converge, ops views carry no customer data. Known honest gaps stand: model cost untracked, pull alerts, single-tenant ops view. No live DB touched.
- **Next:** Milestone F - privacy workflows (F1), real-world validation plan (F2, blocked on pilot), economics instrumentation (F3), then the P2 final report.

## 2026-10-30 � Codex � P2 F1 privacy readiness

- **Objective:** F1 subject-request workflows + inventory + notices + incident runbook.
- **Changed:** `app/database/models.py` (+PrivacyRequest), `app/database/migrations.py` (v18 `20261113_privacy_v18`), `app/services/privacy.py` (new: bundle/correction/deletion rules), `app/api/privacy.py` (new, admin-only) + router, `tests/test_p2_f1_privacy.py` (12 tests), `tests/test_foundations.py` tally 17 -> 18, `docs/privacy.md` (new).
- **Verification:** 12/12 F1 tests pass (export contents + no-secret walk, tenant scoping, correction allowlist + branch binding, open-invoice + hold blocks, erase-contacts-keep-ledger with paid case view intact, staff offboard, self/last-admin blocks, reject/terminal states, editor 403). Full suite + F gate still pending.
- **Decisions / limits:** Deletion erases contact/comms only � invoices, ledger, names-on-books, GSTINs, consent records, audit kept as books-of-account; holds always win. DPDP Rules phased: substantive duties ~May 2027 per secondary sources (MeitY page unreadable, Gazette needs counsel verification). NOT a compliance claim; legal review required. AFIS/AXIS sidecars out of erasure scope.
- **Next:** F2 validation plan doc (blocked on pilot), F3 economics endpoint, then F gate.

## 2026-10-30 � Codex � P2 F2 validation plan

- **Objective:** F2 measurement protocol without inventing data.
- **Changed:** `docs/validation-plan.md` (new: entry criteria, M1-M7 metric definitions + sources, interview/pilot/usability protocols, evidence-trail + report templates, 4 precise blockers).
- **Verification:** Doc-only change; no code, no tests (nothing executable to test). `git diff --check` clean.
- **Decisions / limits:** Execution BLOCKED on pilot businesses + consent + access + accountant reviewer. No validation claim in README/demo until then. Pilot data barred from fixtures/tests/demos.
- **Next:** F3 economics endpoint, then F gate.

## 2026-10-30 � Codex � P2 F3 economics instrumentation

- **Objective:** F3 cost instrumentation with assumptions separated from measurements.
- **Changed:** `app/services/tenant_config.py` (+8 cost_* setting specs/validators), `app/config.py` (+8 COST_* globals, zero defaults), `app/services/economics.py` (new report builder), `app/api/system.py` (+GET /system/economics, admin-only), `tests/test_p2_f3_economics.py` (6 tests), `docs/economics.md` (new).
- **Verification:** 6/6 F3 tests pass (tenant+window scoping, zero-default flagging, priced-lines arithmetic 4648.40 fixture, measured-stable-on-reprice, sensitivity 1596.00/1564.00, invalid price/window rejected). Full suite + F gate still pending.
- **Decisions / limits:** Gateway fees on reporting-currency volume only (no silent FX); supervisor model calls only (intake/vision uninstrumented, reported pending); willingness-to-pay always pending on F2 interviews; no price/market claim without evidence.
- **Next:** Milestone F gate (full suite, demos isolated, smoke), then the final P2 report.

## 2026-10-30 � Codex � P2 Milestone F gate (final P2 gate)

- **Objective:** Verify F1+F2+F3 end to end: full suite, both demos, isolated smoke.
- **Changed:** `tests/test_p2_e1_workers.py` (race assertion accepts post-commit-done loser; exactly-once asserts intact � see below).
- **Verification:** Full suite 337 passed (319 + 12 F1 + 6 F3); P1 showcase in-tree exit 0 (eval files untouched); hero demo in fresh `%TEMP%\p2-f-demo` copy (30/30, 10/10, 5/10); smoke on port 8128 + temp DB: health ok, migrations current `20261113_privacy_v18` zero pending, economics fresh-state INR/0.00/2-pending, privacy list empty, unknown-subject 400, bad-key 401; `git diff --check` exit 0; port-8002 app/DB untouched. No frontend changes, no node check needed.
- **E1 race note:** `test_simultaneous_supervisor_run_executes_once` failed 2x under full-suite load (both outcomes done). Root cause is a third valid serialization � loser arriving after the winner commits returns done without executing (supervisor.py:271-272) � not double execution. Proven by /tmp/e1_probe.py: exactly-once (1 call, attempts 1) across 30/30 races with loser outcomes varying (claimed/running). Test now accepts all three serializations; E1 file green 2x standalone, full suite green after.
- **Demo-copy note:** first robocopy hung on locked live DB files (default 30s retries); killed only my proven robocopy PID, re-copied with /R:2 /W:1 excluding *.db*, .env, caches. Another session''s p0-verify copy + all run.py servers left untouched.
- **Decisions / limits:** F gate holds: subject-request workflows tested, validation protocol ready but BLOCKED on pilot, economics separates measured/assumed/pending. Standing honest gaps: PG unverified, payments simulated, messaging sandbox, DPDP needs counsel, willingness-to-pay unmeasured.
- **Next:** P2 complete � see final report. Remaining work is all external-input gated (pilot, providers, PG instance, reviewers).

### 2026-10-30 - Codex - Independent verification and regression fixes

- **Objective:** Verify P0/P1/P2 claims without touching port 8002 or its database.
- **Changed:** receivables.py (debit-aware reversal ceiling; reversal retry checks original ID), privacy.py (explicit counterparty link wins over matching name), economics.py (negative ledger receipts become positive gross volume), db_manager.py (bootstrap uses the migrated engine). Added three regression tests and corrected economics fixtures to use actual ledger signs.
- **Verification:** Baseline full suite 334 passed, 3 failed on isolated bootstrap DB (migration tests changed engine but SessionLocal still referenced the default engine). Before fixes: targeted regressions 5 failed, 4 passed, confirming all four service defects. P1 showcase and isolated-copy hero demo passed (30/30, 10/10, 5/10). Focused post-fix suite running; full rerun pending.
- **Limits:** CodeRabbit installation failed: unsupported mingw64_nt-10.0-26300. User explicitly chose verification without CodeRabbit. No live-provider or PostgreSQL validation; no live DB opened. Existing changes preserved; no commits.
- **Next:** Finish regression/full-suite checks, isolated server and desktop/mobile smoke, README and 17-workstream report.

### 2026-10-30 - Codex - Worker recovery regression hardening

- **Changed:** supervisor.py now includes expired running leases in normal worker pickup; startup recovery in supervisor.py/intake_pipeline.py resets only legacy unleased jobs, preserving another worker's active lease. Two regression tests added; existing race assertions unchanged.
- **Verification:** Both new tests failed before the fix. Earlier money/privacy/economics/migration focused suite: 76 passed. Worker focused suite running. Isolated port-8138 app: health/case/privacy/economics 200, migrations v18 with 18 applied and zero pending, bad key 401, unknown privacy subject 400.
- **Limits / next:** No general distributed exactly-once claim; verify focused and full suites, then finish browser checks and documentation. Port 8002 and its DB remain untouched.

### 2026-10-30 - Codex - Verification report and README refresh

- **Changed:** Rewrote README from code and fresh results; added docs/verification-2026-10-30.md with seven defects, exact commands, P0/P1 evidence, all 17 P2 workstreams, external blockers and limits. Updated F1/F2/F3 status in p2-gap-matrix, clarified gross-volume signs in economics, marked foundation notes historical.
- **Verification:** Final full suite 342 passed, 177 warnings (113.82 s); focused suites 76 and 30 passed. New worker tests both failed before fixes. Final in-tree P1 showcase passed and five evaluation files were SHA-256 identical before/after. Frontend app/portal/config JS syntax passed. In-app browser: case and Control flow at 1440x900 and 390x844, populated approval queue, three completed specialists, Open case interaction, no horizontal overflow or console warnings/errors. No frontend changes.
- **Limits / next:** Final isolated hero/P1 evaluation rerun and cleanup pending. No provider/PG/pilot/legal-validation claim. Seven fixed defects do not establish exhaustive correctness; report records remaining limits. Port 8002/live DB untouched, no commit or push.

### 2026-10-30 - Codex - Final verification and cleanup

- **Changed:** Corrected README API route map; runbook now explains lease-preserving startup and avoids a blanket multi-worker safety claim. Final report records the fresh P1 benchmark limitations and final smoke.
- **Verification:** Final hero rerun passes (30/30 split, 10/10 routing, 5/10 review). P1 evaluator completed 38 cases x 3 arms offline with published behavioral scores reproduced; zero model calls. Five checkout evaluation files remain byte-identical. Fresh port-8139 smoke passes health/case/privacy/economics, 18 migrations/zero pending, 401/400 negatives and positive gross receipt volume. Both owned servers stopped; temporary smoke/default test DBs removed. README/report/matrix links and no-emoji checks pass; git diff --check passes.
- **Final state:** 342 passed (177 existing/runtime warnings). Seven defects fixed with pre-fix reproduction; five new regression tests. Full details in docs/verification-2026-10-30.md. Known synthetic evaluation decision errors and metering gaps remain explicit; no production-complete, live-provider, PostgreSQL, field-accuracy or legal-compliance claim. No live DB access, customer send, commit or push.
- **Next:** Review the local changes. Production/provider/pilot validation needs the specific external inputs listed in the report; internal follow-ups include complete model metering and the disclosed benchmark limitations.
