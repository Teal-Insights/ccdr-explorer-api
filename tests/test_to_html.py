import argparse
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from db.db import engine
from db.schema import Document, Node


def export_document_html(
    *,
    document_id: Optional[int],
    output_path: Path,
    pretty: bool,
    include_citation_data: bool,
    include_node_ids: bool,
) -> Path:
    with Session(engine) as session:
        if document_id is not None:
            stmt = select(Document).where(Document.id == document_id)
            document = session.exec(stmt).first()
        else:
            # Select the first Document that has at least one Node
            stmt = select(Document).join(Node).order_by(Document.id).limit(1)
            document = session.exec(stmt).first()

        if document is None:
            raise SystemExit("No Document found. Populate the database before running this script.")

        html_text: str = document.to_html(
            include_citation_data=include_citation_data,
            include_node_ids=include_node_ids,
            include_html_wrapper=True,
            pretty=pretty,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


def export_node_html(
    *,
    node_id: Optional[int],
    output_path: Path,
    pretty: bool,
    include_citation_data: bool,
    include_node_ids: bool,
) -> Path:
    with Session(engine) as session:
        if node_id is not None:
            stmt = select(Node).where(Node.id == node_id)
            node = session.exec(stmt).first()
        else:
            # Select the first Node
            stmt = select(Node).order_by(Node.id).limit(1)
            node = session.exec(stmt).first()

        if node is None:
            raise SystemExit("No Node found. Populate the database before running this script.")

        html_fragment: str = node.to_html(
            include_citation_data=include_citation_data,
            include_node_ids=include_node_ids,
            is_top_level=True,
            pretty=pretty,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_fragment, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a Document or a Node rendered as HTML for inspection."
    )
    parser.add_argument(
        "--document-id",
        type=int,
        default=None,
        help="Document ID to export. If omitted, exports the first document with at least one node.",
    )
    parser.add_argument(
        "--node-id",
        type=int,
        default=None,
        help="Node ID to export. If omitted and selected, exports the first node.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/out/document.html"),
        help="Output file path.",
    )
    parser.add_argument(
        "--include-ids",
        action="store_true",
        help="Include node IDs as id attributes on top-level elements.",
    )
    # Descriptions are never emitted as plain text; only used as img alt text
    parser.add_argument(
        "--citation",
        action="store_true",
        help="Include publication and document data attributes on top-level elements.",
    )
    args = parser.parse_args()

    # Determine mode: Node takes precedence if provided
    if args.node_id is not None:
        # If default document output is unchanged, switch to a node-specific default
        default_doc_output = Path("tests/out/document.html")
        output_path = args.output if args.output != default_doc_output else Path("tests/out/node.html")
        output_path = export_node_html(
            node_id=args.node_id,
            output_path=output_path,
            pretty=True,
            include_citation_data=args.citation,
            include_node_ids=args.include_ids,
        )
        print(f"Wrote node output to: {output_path}")
    else:
        output_path = export_document_html(
            document_id=args.document_id,
            output_path=args.output,
            pretty=True,
            include_citation_data=args.citation,
            include_node_ids=args.include_ids,
        )
        print(f"Wrote document output to: {output_path}")


if __name__ == "__main__":
    main()


