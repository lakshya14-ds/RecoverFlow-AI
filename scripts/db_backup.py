"""Operational SQLite backup, restore, and verification for RecoverFlow.

Online-safe: backups use the SQLite backup API, so the app can keep running.
Verification checks integrity plus migration revisions. PostgreSQL deployments
use pg_dump/pg_restore instead; see docs/ops-backup.md. This script never
touches a database it was not explicitly given — pass the path every time.
"""
import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

COUNT_TABLES = ("invoices", "receivable_entries", "audit_events", "case_evidence")


def backup_sqlite(src, dest):
    """Copy a live SQLite database to a new file. Refuses to overwrite."""
    src, dest = Path(src), Path(dest)
    if not src.is_file():
        raise FileNotFoundError(f"Source database not found: {src}")
    if dest.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {dest}")
    source = sqlite3.connect(str(src))
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return verify_backup(dest)


def verify_backup(path):
    """Check integrity, revisions, and row counts. Raises on any failure."""
    path = Path(path)
    connection = sqlite3.connect(str(path))
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError(f"Integrity check failed for {path}: {integrity}")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        revisions = []
        if "schema_revisions" in tables:
            revisions = [row[0] for row in connection.execute(
                "SELECT revision FROM schema_revisions ORDER BY revision")]
        counts = {}
        for table in COUNT_TABLES:
            if table in tables:
                counts[table] = connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    finally:
        connection.close()
    return {"path": str(path), "integrity": "ok", "revisions": revisions,
            "counts": counts}


def restore_sqlite(backup, dest, force=False):
    """Restore a verified backup to a new path, then verify the result."""
    dest = Path(dest)
    if dest.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {dest} (use --force)")
    report = verify_backup(backup)
    shutil.copy2(str(backup), str(dest))
    restored = verify_backup(dest)
    if restored["revisions"] != report["revisions"] or restored["counts"] != report["counts"]:
        raise ValueError("Restored database does not match the backup")
    return restored


PG_TEMPLATE = """PostgreSQL backup/restore template (run on the database host):

  pg_dump --format=custom --file=recoverflow-backup.dump "$DATABASE_URL"
  pg_restore --list recoverflow-backup.dump | head -5        # verify it restores
  createdb recoverflow_restore_drill
  pg_restore --dbname=recoverflow_restore_drill recoverflow-backup.dump
  psql "$DATABASE_URL" -c "SELECT revision FROM schema_revisions ORDER BY 1;"
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description="RecoverFlow SQLite backup tool")
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup", help="Back up a SQLite database file")
    backup.add_argument("src")
    backup.add_argument("dest")
    verify = sub.add_parser("verify", help="Verify a backup file")
    verify.add_argument("path")
    restore = sub.add_parser("restore", help="Restore a backup to a new path")
    restore.add_argument("backup")
    restore.add_argument("dest")
    restore.add_argument("--force", action="store_true")
    sub.add_parser("pg-template", help="Print the PostgreSQL backup template")
    args = parser.parse_args(argv)
    if args.command == "backup":
        report = backup_sqlite(args.src, args.dest)
    elif args.command == "verify":
        report = verify_backup(args.path)
    elif args.command == "restore":
        report = restore_sqlite(args.backup, args.dest, force=args.force)
    else:
        print(PG_TEMPLATE)
        return 0
    print(f"{args.command}: integrity={report['integrity']} "
          f"revisions={len(report['revisions'])} counts={report['counts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
