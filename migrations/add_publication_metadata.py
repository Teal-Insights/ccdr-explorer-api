#!/usr/bin/env python3
"""
Migration: Add JSONB column 'metadata' to the 'publication' table.

- Idempotent: uses IF NOT EXISTS
- Safe: no default or NOT NULL constraints applied
- Supports --dry-run and --confirm flags
"""

from __future__ import annotations

import argparse
from sqlalchemy import text
from sqlmodel import Session

from db.db import engine, get_database_url


SQL = """
ALTER TABLE public.publication
    ADD COLUMN IF NOT EXISTS metadata JSONB;
"""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add 'metadata' JSONB column to 'publication' table"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print SQL without executing",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt",
    )

    args = parser.parse_args()

    # Show DB target for sanity
    try:
        db_url = get_database_url()
        host_port_db = db_url.split("@")[1] if "@" in db_url else db_url
        print(f"Target database: {host_port_db}")
    except Exception as e:
        print(f"Failed to resolve database URL: {e}")

    if args.dry_run:
        print(SQL.strip())
        return

    if not args.confirm:
        resp = input(
            "This will alter table 'publication' to add column 'metadata'. Continue? (yes/no): "
        ).strip().lower()
        if resp not in ("yes", "y"):
            print("Aborted.")
            return

    with Session(engine) as session:
        session.exec(text(SQL))
        session.commit()
        print(
            "Completed: ensured column 'metadata' (JSONB) exists on table 'publication'."
        )


if __name__ == "__main__":
    main()


