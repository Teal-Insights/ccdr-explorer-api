import argparse
from pathlib import Path
from typing import Optional

from sqlmodel import Session, select

from db.db import engine
from db.schema import Document, Node


def export_document_html(
    *, document_id: Optional[int], output_path: Path, include_descriptions: bool, pretty: bool
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
            include_descriptions=include_descriptions,
            include_html_wrapper=True,
            pretty=pretty,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a Document rendered as HTML to a file for inspection."
    )
    parser.add_argument(
        "--document-id",
        type=int,
        default=None,
        help="Document ID to export. If omitted, exports the first document with at least one node.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/out/document.html"),
        help="Output file path.",
    )
    parser.add_argument(
        "--no-descriptions",
        action="store_true",
        help="Exclude descriptions from the output.",
    )
    args = parser.parse_args()

    output_path = export_document_html(
        document_id=args.document_id,
        output_path=args.output,
        include_descriptions=not args.no_descriptions,
        pretty=True,
    )
    print(f"Wrote document output to: {output_path}")


if __name__ == "__main__":
    main()


