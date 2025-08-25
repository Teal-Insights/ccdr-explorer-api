#!/usr/bin/env python3
"""
Migration: remove NodeType and node.node_type, and enforce NOT NULL on node.tag_name.

- Safe to re-run (checks existence; uses IF EXISTS where possible)
- Confirmation prompt unless --confirm is passed
- Optional --dry-run to see what would be executed
"""

import argparse
import sys
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from db.db import engine, get_database_url


CHECK_COLUMN_SQL = text(
    """
SELECT 1
FROM information_schema.columns
WHERE table_schema = :schema
  AND table_name = :table
  AND column_name = :column
LIMIT 1
"""
)

CHECK_NULLS_SQL = text(
    """
SELECT COUNT(*)
FROM public.node
WHERE tag_name IS NULL
"""
)

ALTER_DROP_COLUMN_SQL = text(
    "ALTER TABLE public.node DROP COLUMN IF EXISTS node_type;"
)

ALTER_TAGNAME_NOT_NULL_SQL = text(
    "ALTER TABLE public.node ALTER COLUMN tag_name SET NOT NULL;"
)

DROP_ENUM_SQL = text(
    "DROP TYPE IF EXISTS nodetype;"
)


def column_exists(conn, schema: str, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            CHECK_COLUMN_SQL, {"schema": schema, "table": table, "column": column}
        ).scalar()
    )


def main():
    parser = argparse.ArgumentParser(
        description="Drop node.node_type column and nodetype enum; set node.tag_name NOT NULL"
    )
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
        resp = input(
            "This will drop column public.node.node_type, drop type nodetype, and set public.node.tag_name NOT NULL. Continue? (yes/no): "
        ).strip().lower()
        if resp not in ("yes", "y"):
            print("Aborted.")
            return

    try:
        with engine.begin() as conn:
            # Check tag_name has no NULLs before enforcing NOT NULL
            null_count = conn.execute(CHECK_NULLS_SQL).scalar() or 0
            if null_count and null_count > 0:
                raise RuntimeError(
                    f"Cannot set tag_name NOT NULL; found {null_count} rows with tag_name IS NULL."
                )

            node_type_exists = column_exists(conn, "public", "node", "node_type")

            if args.dry_run:
                if node_type_exists:
                    print(f"Would execute: {ALTER_DROP_COLUMN_SQL.text}")
                print(f"Would execute: {ALTER_TAGNAME_NOT_NULL_SQL.text}")
                print(f"Would execute: {DROP_ENUM_SQL.text}")
                return

            if node_type_exists:
                print(f"Executing: {ALTER_DROP_COLUMN_SQL.text}")
                conn.execute(ALTER_DROP_COLUMN_SQL)
                print("✓ Dropped column 'node_type' from 'public.node'.")
            else:
                print("No-op: column 'node_type' does not exist on 'public.node'.")

            print(f"Executing: {ALTER_TAGNAME_NOT_NULL_SQL.text}")
            conn.execute(ALTER_TAGNAME_NOT_NULL_SQL)
            print("✓ Enforced NOT NULL on 'public.node.tag_name'.")

            print(f"Executing: {DROP_ENUM_SQL.text}")
            conn.execute(DROP_ENUM_SQL)
            print("✓ Dropped type 'nodetype' if it existed.")

    except (SQLAlchemyError, RuntimeError) as e:
        print(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


