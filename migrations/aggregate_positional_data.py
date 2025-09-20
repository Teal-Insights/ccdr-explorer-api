#!/usr/bin/env python3
"""
Migration: Aggregate Node.positional_data to one bbox per page.

For each Node, consolidate positional_data entries that share the same page_pdf
into a single bounding rectangle per page using min(x1,y1) and max(x2,y2).

Features:
- Safe to re-run (idempotent): only updates rows whose aggregated value differs
- Confirmation prompt unless --confirm is passed
- Optional --dry-run to preview changes without writing
- Optional --document-id to limit to a single document
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, select

from db.db import engine, get_database_url
from db.schema import Node


def _safe_json_loads(value: str) -> Any:
    """Attempt to parse a JSON string, handling double-encoded cases.

    Returns the parsed object on success; otherwise returns the original string.
    """
    try:
        parsed = json.loads(value)
        # Handle double-encoded JSON strings (a JSON string that itself contains JSON)
        if isinstance(parsed, str):
            try:
                return json.loads(parsed)
            except Exception:
                return parsed
        return parsed
    except Exception:
        return value


def _normalize_positional_list(raw: Any) -> List[Dict[str, Any]]:
    """Normalize various stored formats to a list of positional dicts.

    Accepts:
    - None -> []
    - list[dict] -> as-is
    - dict -> [dict]
    - str -> json.loads(str), possibly double-encoded
    Anything invalid produces [].
    """
    if raw is None:
        return []

    value: Any = raw
    if isinstance(value, str):
        value = _safe_json_loads(value)

    if isinstance(value, dict):
        return [value]

    if isinstance(value, list):
        # Ensure each entry is a dict; coerce otherwise
        result: List[Dict[str, Any]] = []
        for item in value:
            if isinstance(item, str):
                item = _safe_json_loads(item)
            if isinstance(item, dict):
                result.append(item)
        return result

    return []


def _to_int(value: Any) -> Optional[int]:
    try:
        if isinstance(value, bool):  # guard against bool subclassing int
            return int(value)
        if isinstance(value, (int,)):
            return int(value)
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            return int(float(value))
    except Exception:
        return None
    return None


def _to_float(value: Any) -> Optional[float]:
    try:
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value)
    except Exception:
        return None
    return None


def _aggregate_positional_data_by_page(
    pos_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Merge positional data that share the same page into a single bbox per page."""
    if not pos_list:
        return []

    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for pd in pos_list:
        page_pdf_raw = pd.get("page_pdf")
        bbox = pd.get("bbox")
        if bbox is None or not isinstance(bbox, dict):
            continue

        page_pdf = _to_int(page_pdf_raw)
        if page_pdf is None:
            continue

        by_page.setdefault(page_pdf, []).append(pd)

    aggregated: List[Dict[str, Any]] = []
    for page_pdf, group in by_page.items():
        xs1: List[float] = []
        ys1: List[float] = []
        xs2: List[float] = []
        ys2: List[float] = []

        page_logical: Optional[str] = None

        for p in group:
            bbox = p.get("bbox") or {}
            x1 = _to_float(bbox.get("x1"))
            y1 = _to_float(bbox.get("y1"))
            x2 = _to_float(bbox.get("x2"))
            y2 = _to_float(bbox.get("y2"))

            if x1 is None or y1 is None or x2 is None or y2 is None:
                continue

            xs1.append(x1)
            ys1.append(y1)
            xs2.append(x2)
            ys2.append(y2)

            if page_logical is None:
                pl = p.get("page_logical")
                if pl is not None:
                    page_logical = str(pl)

        if not xs1:
            # No valid bbox in this group
            continue

        aggregated.append(
            {
                "page_pdf": page_pdf,
                "page_logical": page_logical,
                "bbox": {
                    "x1": min(xs1),
                    "y1": min(ys1),
                    "x2": max(xs2),
                    "y2": max(ys2),
                },
            }
        )

    aggregated.sort(key=lambda p: p["page_pdf"])  # deterministic order
    return aggregated


def _json_equal(a: Any, b: Any) -> bool:
    """Compare two JSON-like values for semantic equality."""
    try:
        return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    except Exception:
        return a == b


def _iter_target_nodes(session: Session, document_id: Optional[int]) -> Iterable[Tuple[int, Any]]:
    stmt = select(Node.id, Node.positional_data)
    if document_id is not None:
        stmt = stmt.where(Node.document_id == document_id)
    # We do not add an IS NOT NULL filter to also normalize string/invalid forms
    for node_id, pd in session.exec(stmt):
        yield node_id, pd


def aggregate_migration(document_id: Optional[int], dry_run: bool) -> Tuple[int, int, int]:
    """Run aggregation and return (scanned, updated, unchanged)."""
    scanned = 0
    updated = 0
    unchanged = 0

    with Session(engine) as session:
        for node_id, pd_raw in _iter_target_nodes(session, document_id):
            scanned += 1
            original_list = _normalize_positional_list(pd_raw)
            aggregated_list = _aggregate_positional_data_by_page(original_list)

            if _json_equal(original_list, aggregated_list):
                unchanged += 1
                continue

            if dry_run:
                updated += 1
                continue

            stmt = (
                update(Node)
                .where(Node.id == node_id)
                .values(positional_data=aggregated_list)
            )
            session.exec(stmt)
            updated += 1

        if not dry_run:
            session.commit()

    return scanned, updated, unchanged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Aggregate Node.positional_data to one bbox per page"
    )
    parser.add_argument(
        "--document-id",
        type=int,
        default=None,
        help="Limit to a single document ID",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to the database",
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
        return

    if not args.confirm and not args.dry_run:
        scope = (
            f"document {args.document_id}"
            if args.document_id is not None
            else "ALL documents"
        )
        resp = input(
            f"This will update positional_data for {scope}. Continue? (yes/no): "
        ).strip().lower()
        if resp not in ("yes", "y"):
            print("Aborted.")
            return

    try:
        scanned, updated, unchanged = aggregate_migration(
            document_id=args.document_id, dry_run=args.dry_run
        )
        mode = "(dry-run) " if args.dry_run else ""
        print(
            f"{mode}Completed aggregation. Scanned: {scanned}, Updated: {updated}, Unchanged: {unchanged}"
        )
    except SQLAlchemyError as e:
        print(f"Migration failed: {e}")
        raise


if __name__ == "__main__":
    main()


