# Changelog

## Unreleased

- Added Release 1 retailer CSV import, assisted case review, fixed-cent receivable entries, payment allocation, and daily DSO snapshots.
- Moved PDF processing to a restartable database-backed worker and added AR document review and retry.
- Added draft refresh and approval, contact suppression, opt-out safeguards, and neutral later-stage templates.
- Repaired OCR dependency loading and removed mock advisory and sync nodes from the active workflow.
- Renamed the application to RecoverFlow and changed its dashboard, API metadata, messages, and configuration examples to English.
- Added RecoverFlow API key settings and header while retaining legacy aliases for existing installations.
- Added durable invoice processing jobs and explicit review/error outcomes.
- Fixed date persistence, matching input, review routing, duplicate alerts, and reconciliation records.
- Made collections draft and send states truthful; unsupported providers now return 503.
- Replaced fixed AR aging and dashboard figures with database queries.
- Added API key access, organization scoping, audit events, bounded PDF uploads, and tests.

## [1.2.0] - 2026-07-20
### Added
- Added accounting synchronization routes through `accounting_sync.py` and `/api/v1/sync`.
- Added payment transfer routes through `external_pay.py` and `/api/v1/payments`.
- Added a semantic approval agent to the LangGraph workflow for common invoices.
- Added a virtual CFO agent that uses DSO forecasts for cash flow recommendations.
- Added document ingestion webhooks with an optional Vision LLM integration.
### Changed
- Revised `README.md` for small and midsize businesses.
## [1.1.0] - 2026-07-13
### Changed
- Refactored security checks and auditability.
- Enabled SQLite WAL mode to improve concurrency.
- Scoped database sessions used by background invoice processing.
- Added exponential retries for LLM integration.
- Added structured Pydantic parsing for collection agents.
- Added error handling around LangGraph nodes.
- Expanded README documentation, docstrings, and type hints.

## [1.0.0] - 2026-06-15
### Added
- Created the initial LangGraph workflow with six agents.
- Integrated PyTesseract for invoice OCR.
- Added scikit-learn Isolation Forest and Prophet models for fraud detection and DSO forecasting.
- Built a vanilla JavaScript and CSS frontend with an amber palette.
- Added read-only AFIS finance and AXIS tax adapters.
