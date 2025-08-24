#!/usr/bin/env python3
"""
Migration: drop 'citation' column from 'publication' table.

- Safe to re-run (checks existence; uses IF EXISTS)
- Confirmation prompt unless --confirm is passed
- Optional --dry-run to see what would be executed
"""

import argparse
import sys
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from db.db import engine, get_database_url


CHECK_SQL = text("""
SELECT 1
FROM information_schema.columns
WHERE table_schema = :schema
  AND table_name = :table
  AND column_name = :column
LIMIT 1
""")

DROP_SQL = text("ALTER TABLE public.publication DROP COLUMN IF EXISTS citation;")


def column_exists(conn, schema: str, table: str, column: str) -> bool:
    return bool(conn.execute(
        CHECK_SQL,
        {"schema": schema, "table": table, "column": column}
    ).scalar())


def main():
    parser = argparse.ArgumentParser(description="Drop 'citation' column from 'publication' table")
    parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    args = parser.parse_args()

    # Show DB target for sanity
    try:
        db_url = get_database_url()
        host_port_db = db_url.split("@")[1] if "@" in db_url else db_url
        print(f"Target database: {host_port_db}")
    except Exception as e:
        print(f"Failed to resolve database URL: {e}")
        sys.exit(1)

    if not args.confirm:
        resp = input("This will drop column public.publication.citation. Continue? (yes/no): ").strip().lower()
        if resp not in ("yes", "y"):
            print("Aborted.")
            return

    try:
        with engine.begin() as conn:
            if not column_exists(conn, "public", "publication", "citation"):
                print("No-op: column 'citation' does not exist on 'public.publication'.")
                return

            if args.dry_run:
                print(f"Would execute: {DROP_SQL.text}")
                return

            print(f"Executing: {DROP_SQL.text}")
            conn.execute(DROP_SQL)
            print("✓ Dropped column 'citation' from 'public.publication'.")

    except SQLAlchemyError as e:
        print(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()