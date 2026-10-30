# Database operations: migrations, backup, restore, PostgreSQL

## Migration status

`GET /api/v1/system/migrations` (admin only) reports the engine dialect, the current
revision, and applied/pending/unknown revision lists from the `schema_revisions` table.
It never returns the database URL. Check it after every deploy and before any upgrade:

```powershell
Invoke-RestMethod -Headers @{"X-RECOVERFLOW-API-KEY" = $env:RECOVERFLOW_API_KEY} `
  http://127.0.0.1:8002/api/v1/system/migrations
```

`pending` must be empty before the app serves traffic. `unknown` entries mean the
database was migrated by newer code — do not downgrade the app against it.

## Upgrades (SQLite and PostgreSQL)

- Upgrades run inside `init_db()` at startup through the versioned `migrate()` in
  `app/database/migrations.py`. Revisions are idempotent: re-running records nothing new.
- Run upgrades with one starting process, during a maintenance window, with a fresh
  verified backup (below). PostgreSQL migrations take a transaction-scoped advisory lock
  so two starters cannot interleave.
- The PostgreSQL path never runs SQLite-only initialization (no `schema.sql`, no legacy
  PRAGMA patching); it uses `create_all` plus the versioned revisions.
- A failed money conversion aborts the upgrade without losing rows: fix the offending
  legacy value and re-run; the upgrade resumes. Never hand-edit `schema_revisions`.

## SQLite backup and restore

Online backup (safe while the app runs; uses the SQLite backup API, WAL-aware):

```powershell
py -3.12 scripts/db_backup.py backup apex_ar.db backups/apex_ar-YYYYMMDD-HHMM.db
py -3.12 scripts/db_backup.py verify backups/apex_ar-YYYYMMDD-HHMM.db
```

Restore drill (quarterly, against an isolated copy — never the live file):

```powershell
py -3.12 scripts/db_backup.py restore backups/apex_ar-YYYYMMDD-HHMM.db C:\temp\restore-drill.db
$env:APEX_DB_PATH = "C:\temp\restore-drill.db"   # then start the app on an isolated port
```

Verify after restore: migration status shows zero pending, case counts match the backup
report printed by the script, and the health endpoint returns 200. Keep dated backups
with the retention in `docs/privacy.md`; backups contain customer data and need the same
access control as the live database.

## PostgreSQL deployment (UNVERIFIED — no instance has been available)

Supported target: **PostgreSQL 15 or newer** with the `psycopg` v3 driver
(`pip install "psycopg[binary]"`; SQLAlchemy 2.0 dialect). The migration code path for
PostgreSQL exists and is reviewed, but **no test in this repository has ever run against
a real PostgreSQL server**, so PostgreSQL is NOT verified.

Deployment steps when an instance exists:

1. `SET DATABASE_URL=postgresql+psycopg://user:pass@host:5432/recoverflow`
2. Tune `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` for the host.
3. Back up first: `pg_dump --format=custom --file=... "$DATABASE_URL"`
   (full template: `py scripts/db_backup.py pg-template`).
4. Start one app process; it migrates under the advisory lock. Confirm zero pending via
   the migration-status endpoint, then start the remaining processes.
5. Run the restore drill into a scratch database before going live.

Do not claim PostgreSQL support to a pilot business until steps 3–5 have been executed
against a real server and recorded in `.codex/handoff.md`.
