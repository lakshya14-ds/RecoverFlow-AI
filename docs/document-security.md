# Document security (P2 C2)

Evidence bytes live in `data/documents/{tenant_id}/` under random names, and
intake bytes in `data/intake/`. Neither directory is web-served. Every read
is authorized, hash-checked where a hash exists, and logged.

## What is enforced

- **Type allowlist:** portal evidence takes PDF/JPEG/PNG; staff intake adds
  CSV. Anything else (including archives, HTML/SVG, and executables) is
  rejected with 415 — archives are refused because their contents cannot be
  scanned by the policy engine.
- **Content sniffing:** magic bytes must match the extension (PDF/JPEG/PNG
  signatures, UTF-8 CSV with a real header). The declared content type is
  ignored; forged types fail closed.
- **Dangerous names:** double extensions that hide executable or archive
  types (`run.exe.pdf`) are rejected. Filenames must be short ASCII.
- **Size cap:** `MAX_UPLOAD_BYTES` (10 MB), enforced while streaming so an
  oversized body never lands on disk (413).
- **Hashing:** every new file records SHA-256. Intake downloads recompute
  the digest: a mismatch returns 409 and the file is treated as
  quarantined-for-review. Pre-C2 intake rows carry no hash and are backfilled
  on first verified read.
- **Quarantine:** any staff can quarantine (reads block immediately: 403 for
  staff, 404 for the portal so nothing leaks). Release requires admin.
  Portal uploads land as `pending` and need that release before case use.
- **Holds and deletion:** a hold blocks deletion and retention purge.
  Deletion is admin-only, removes the bytes, and keeps the row as a soft
  delete for the audit trail.
- **Retention:** `DOC_RETENTION_DAYS` (2920, eight years) default expiry per
  file. `POST /system/documents/purge` is dry-run by default, tenant-scoped,
  admin-only, and skips holds; run the real pass from cron and keep the
  audit event it writes.
- **Access log:** `document_access_log` records stored/download/
  released/quarantined/hold/deleted with actor and IP. Intake downloads
  write `intake_file_downloaded` audit events.

## What is NOT claimed

No antivirus engine is wired. The `clean` mark means "policy scan passed on
a staff-authenticated channel" (or "released by staff after review"), not
"malware-free". `scanned_by` says exactly which: `policy-v1` or the staff
actor. A ClamAV/cloud-AV integration is the pending hardening item; until
then, treat even released files as untrusted evidence.

## Untrusted-evidence rule

Uploaded bytes and notes are data, never instructions. They enter the case
only as `alleged` evidence rows, are served as `attachment` downloads (never
inline rendering), and no upload path posts ledger entries or flips case
state beyond flagging `requires_human_review`.

## Tests

`tests/test_p2_c2_documents.py` (10 tests): staff list/download + access
log, cross-tenant/guessed-id 404s, quarantine blocking both channels,
admin-only release, hold blocking delete + byte removal with row kept,
dry-run vs real purge with hold skip, intake hash/409-tamper/NULL-backfill,
double-extension/forged-type/oversize negatives, injection content shipped
inert as an attachment, missing-bytes 404s.
