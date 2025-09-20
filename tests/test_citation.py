from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from db.db import engine
from db.schema import Publication, Document, Node, render_csl_item, RenderOptions


def run():
    with Session(engine) as session:
        stmt = (
            select(Publication)
            .options(
                selectinload(Publication.documents)
                .selectinload(Document.nodes)
                .selectinload(Node.content_data)
            )
            .limit(1)
        )
        pub = session.exec(stmt).first()
        if not pub:
            print("No publications found.")
            return

        print("=== Publication ===")
        print(f"Publication ID: {pub.id}")
        print(f"Title: {pub.title}")
        print(f"Simple citation: {pub.citation}")

        print("\n--- CSL (publication only) ---")
        csl_pub = pub.to_csl_item()
        print(csl_pub)
        rendered_pub_html = render_csl_item(csl_pub, options=RenderOptions(style="apa", output="html"))
        rendered_pub_text = render_csl_item(csl_pub, options=RenderOptions(style="apa", output="text"))
        print("Rendered (APA, html):", rendered_pub_html)
        print("Rendered (APA, text):", rendered_pub_text)

        if not pub.documents:
            print("\nNo documents on this publication.")
            return

        print("\n=== Documents ===")
        for doc in pub.documents:
            print(f"\nDocument ID: {doc.id} | type={doc.type} | lang={doc.language} | mime={doc.mime_type}")
            print(f"Description: {doc.description}")

            # Document.get_citation with suffix details (default) in html/text
            doc_cite_html = doc.get_citation(output="html")
            doc_cite_text = doc.get_citation(output="text")
            print("get_citation(html):", doc_cite_html)
            print("get_citation(text):", doc_cite_text)

            # Render via Publication.to_csl_item(document=...) -> render_csl_item
            csl_doc = pub.to_csl_item(doc)
            rendered_doc_html = render_csl_item(csl_doc, options=RenderOptions(style="apa", output="html"))
            rendered_doc_text = render_csl_item(csl_doc, options=RenderOptions(style="apa", output="text"))
            print("render_csl_item(APA, html):", rendered_doc_html)
            print("render_csl_item(APA, text):", rendered_doc_text)

            # Node.get_citation for a few nodes (if present)
            nodes = sorted(list(doc.nodes or []), key=lambda n: n.sequence_in_parent)
            if nodes:
                print("\nNodes (first 3) get_citation(text):")
                for node in nodes[:3]:
                    print(f"  Node ID: {node.id} | tag={node.tag_name}")
                    print("   ", node.get_citation(output="text"))
            else:
                print("No nodes on this document.")


def test_print_citation():
    # Run with: pytest -s tests/test_citation.py::test_print_citation
    run()


def test_print_document_citations():
    # Run with: pytest -s tests/test_citation.py::test_print_document_citations
    run()


def test_print_node_citations():
    # Run with: pytest -s tests/test_citation.py::test_print_node_citations
    run()


if __name__ == "__main__":
    # Or: python tests/test_citation.py
    run()