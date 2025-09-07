#!/usr/bin/env python3
"""
Migration: Rename column 'metadata' to 'publication_metadata' on table 'publication'.

- Idempotent: inspects information_schema before acting
- Safe: only renames when old exists and new does not
- Supports --dry-run and --confirm flags
"""

from __future__ import annotations

import argparse
from typing import Set

from sqlalchemy import text
from sqlmodel import Session

from db.db import engine, get_database_url


def get_existing_columns(session: Session) -> Set[str]:
    rows = session.exec(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'publication'
              AND column_name IN ('metadata', 'publication_metadata')
            """
        )
    )
    return {row[0] for row in rows}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rename publication.metadata to publication_metadata"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended action without executing",
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

    with Session(engine) as session:
        cols = get_existing_columns(session)
        has_old = "metadata" in cols
        has_new = "publication_metadata" in cols

        if has_new and not has_old:
            print("No action: column already renamed to 'publication_metadata'.")
            return
        if has_new and has_old:
            print(
                "Both 'metadata' and 'publication_metadata' exist. No automatic action taken."
            )
            return
        if not has_old and not has_new:
            print("Neither column exists on 'publication'. Nothing to do.")
            return

        # At this point: old exists, new does not -> rename
        sql = "ALTER TABLE public.publication RENAME COLUMN metadata TO publication_metadata;"

        if args.dry_run:
            print(sql)
            return

        if not args.confirm:
            resp = input(
                "This will RENAME column 'metadata' to 'publication_metadata' on table 'publication'. Continue? (yes/no): "
            ).strip().lower()
            if resp not in ("yes", "y"):
                print("Aborted.")
                return

        session.exec(text(sql))
        session.commit()
        print("Completed: renamed 'metadata' to 'publication_metadata' on 'publication'.")


if __name__ == "__main__":
    main()


