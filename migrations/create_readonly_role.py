#!/usr/bin/env python3
"""
Create a least-privilege read-only database role that can only SELECT from
the CCDR Explorer tables defined in db/schema.py.

Characteristics:
- Idempotent: safe to re-run
- Restricts privileges to just the application tables
- No default privileges on future tables

Usage examples:
  ./migrations/create_readonly_role.py --role ccdr_readonly --password 'strong-pass' --confirm
  ./migrations/create_readonly_role.py --role ccdr_readonly --password 'strong-pass' --dry-run
"""

from __future__ import annotations

import argparse
import os
from typing import List

from sqlalchemy import text
from sqlmodel import Session

from db.db import engine


APP_TABLES: List[str] = [
    "publication",
    "document",
    "node",
    "contentdata",
    "relation",
    "embedding",
]


def build_sql(db_name: str, role: str, password: str) -> str:
    tables_csv = ",\n  ".join(f"public.{t}" for t in APP_TABLES)
    return f"""
DO $$
BEGIN
   IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
      CREATE ROLE {role}
        LOGIN
        PASSWORD '{password}'
        NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
   END IF;
END$$;

GRANT CONNECT ON DATABASE "{db_name}" TO {role};

GRANT USAGE ON SCHEMA public TO {role};

REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {role};
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM {role};

GRANT SELECT ON TABLE
  {tables_csv}
TO {role};
"""


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    
    parser = argparse.ArgumentParser(
        description="Create a read-only DB role with SELECT on app tables"
    )
    parser.add_argument("--role", required=True, help="Role name to create/grant")
    parser.add_argument(
        "--password",
        required=True,
        help="Password for the role (only used on initial creation)",
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

    db_name = os.getenv("POSTGRES_DB")
    sql = build_sql(db_name=db_name, role=args.role, password=args.password)

    if args.dry_run:
        print(sql)
        return

    if not args.confirm:
        resp = input(
            f"This will create/grant role '{args.role}' on database '{db_name}'. Continue? (yes/no): "
        ).strip().lower()
        if resp not in ("yes", "y"):
            print("Aborted.")
            return

    with Session(engine) as session:
        session.exec(text(sql))
        session.commit()
        print(
            f"Completed role setup. Role '{args.role}' has SELECT on {len(APP_TABLES)} tables in '{db_name}'."
        )


if __name__ == "__main__":
    main()


