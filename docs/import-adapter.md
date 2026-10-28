# P1 accounting import adapter (Milestone 4)

`app/services/import_adapter.py` maps foreign rows to one canonical invoice
shape through named profiles. Only `generic_csv` exists. Tally, Busy, and
Zoho support is explicitly NOT claimed: no format is inferred from a name,
and a sanitized export from the first target business is required before any
new profile is added.

- `GET /api/v1/imports/profiles` lists supported profiles.
- `POST /api/v1/imports/preview` maps and validates up to 500 rows without
  writing, returning mapped rows plus row-numbered errors.
- `POST /api/v1/imports/confirm` re-validates and writes idempotently by
  external ID; conflicts raise and nothing partial is kept. Staff
  authentication is the confirmation.
- The legacy `POST /api/v1/imports/receivables/csv` path is preserved
  byte-for-behavior (including its historical USD default) on the same
  shared writer; new adapter profiles default to INR for the India pilot.

Every written invoice stays source-linked (`source_system` + external ID)
and the import is audited. Synthetic fixtures in the test suite stand in for
real exports until the business provides one.
