with open('.codex/handoff.md', 'r', encoding='utf-8') as f:
    content = f.read()

target = '## Current state\r\n\r\n'
if target not in content:
    target = '## Current state\n\n'

new_current_state = '''## Current state\r\n\r\n- **Comprehensive README.md Redesign Completed (2026-11-02, Codex):**\r\n  - Redesigned `README.md` into an executive, judge-facing, deeply technical manual without emojis anywhere.\r\n  - Documented value proposition ("Chase only the money that is actually owed"), synthetic hero case breakdown (INR 2,40,000 gross / INR 1,50,000 paid / INR 90,000 open / INR 30,000 disputed / INR 60,000 undisputed), 5-minute judge walkthrough, core capabilities, and bounded specialist design.\r\n  - Added two fresh Mermaid diagrams (system architecture with 6 bounded specialists and end-to-end recovery sequence flow).\r\n  - Documented Meta model roles (Meta Muse Spark `muse-spark-1.3`, Meta SAM 3.1 `sam-3.1`, Meta Muse Voice `muse-voice-transcribe`) with automatic offline deterministic fallback; described Tesseract OCR, Prophet DSO forecasting, and Isolation Forest anomaly detection.\r\n  - Documented live AWS EC2 / RDS PostgreSQL 18.3 deployment (`https://recoverflaw.duckdns.org/`), verified live public health (HTTP 200), local copyable setup commands for PowerShell and Bash, evaluation disclosures (38 synthetic cases, model calls forced off), and strict guardrails/limitations.\r\n  - Verified zero emojis, all relative markdown links exist, `git diff --check` clean, and foundation test suite passed (27/27 green). Synced `README.md` to EC2 staging.\r\n\r\n'''

content = content.replace(target, new_current_state, 1)

iteration_entry = '''\r\n### 2026-11-02 — Codex — Complete README.md Redesign\r\n\r\n- **Objective:** Redesign the entire `README.md` into a polished, accurate, judge-facing document with zero emojis, comprehensive technical depth, and two Mermaid diagrams per user instructions.\r\n- **Changed:**\r\n  - Completely rewrote `README.md` across 13 required sections: Strong Opening with official `frontend/logo.png`, Problem & Solution with hero case table, 5-minute Judge Walkthrough, Features, Architecture with 6 bounded specialists, End-to-End Workflow diagram, AI Models & Supporting ML, Tech Stack table, Cloud Deployment (AWS EC2 / RDS PostgreSQL 18.3 at `https://recoverflaw.duckdns.org/`), Local Setup commands (PowerShell & Bash), Demonstration & Evaluation Disclosures, API & Repository Map, and Safety/Limitations/Roadmap.\r\n  - Cleaned all trailing whitespace to ensure clean `git diff --check`.\r\n  - Synced updated `README.md` to AWS EC2 staging host via SCP.\r\n- **Verification:**\r\n  - Python character scan confirmed 0 emojis across the entire document.\r\n  - Script validated all relative document and image links (`frontend/logo.png`, `docs/architecture.md`, `docs/supervisor.md`, `docs/postgres-deployment.md`, `docs/auth-permissions.md`, `docs/document-security.md`, `docs/ops-backup.md`) exist on disk.\r\n  - Verified live public health endpoint on staging: `GET https://recoverflaw.duckdns.org/api/v1/system/health` returned HTTP 200 OK `{"status":"ok","service":"RecoverFlow"}`.\r\n  - Smallest reliable test suite `tests/test_foundations.py` executed: 27/27 passed (100%).\r\n  - `git diff --check README.md` passed with zero errors or warnings.\r\n- **Limits / next:** Working tree clean. Live payment remains simulated; messaging remains sandboxed.\r\n'''

content = content + iteration_entry

with open('.codex/handoff.md', 'w', encoding='utf-8', newline='') as f:
    f.write(content)

print('Updated handoff.md successfully')

