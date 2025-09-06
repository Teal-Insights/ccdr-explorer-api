from typing import Optional, Iterable
from bs4 import BeautifulSoup
from sqlmodel import Session, select
from db.db import engine
from db.schema import Node, TagName


def _first_node_id_for_tag(session: Session, tag: TagName) -> Optional[int]:
    node_id: Optional[int] = session.exec(
        select(Node.id).where(Node.tag_name == tag).limit(1)
    ).first()
    return node_id


def _print_context_for_tag(session: Session, tag: TagName) -> None:
    node_id = _first_node_id_for_tag(session, tag)
    print(f"\n=== Tag: {tag.value} ===")
    if node_id is None:
        print("No node found for this tag; skipping.")
        return

    html = Node.render_context_html(session, node_id=node_id, pretty=False)
    if html is None:
        print("render_context_html returned None")
        return

    # Determine selected container tag by inspecting outermost element
    soup = BeautifulSoup(html, "html.parser")
    outer = soup.find(True)
    selected_container_tag = outer.name if outer is not None else None

    # Retrieve immediate parent tag of the original node
    node_obj: Optional[Node] = session.get(Node, node_id)
    parent_tag = node_obj.parent.tag_name.value if (node_obj and node_obj.parent) else None

    print(f"Node ID: {node_id}")
    print(f"Rendered length: {len(html)} characters")
    print(f"Selected container tag: {selected_container_tag}")
    print(f"Immediate parent tag: {parent_tag}")


def _run_for_tags(session: Session, tags: Iterable[TagName]) -> None:
    for tag in tags:
        _print_context_for_tag(session, tag)


if __name__ == "__main__":
    with Session(engine) as session:
        # Table family
        _run_for_tags(session, [
            TagName.TABLE,
            TagName.THEAD,
            TagName.TBODY,
            TagName.TFOOT,
            TagName.TR,
            TagName.TH,
            TagName.TD,
            TagName.CAPTION,
        ])

        # Figure family
        _run_for_tags(session, [
            TagName.FIGURE,
            TagName.FIGCAPTION,
            TagName.IMG,
        ])

        # Lists
        _run_for_tags(session, [
            TagName.UL,
            TagName.OL,
            TagName.LI,
        ])

        # Common containers
        _run_for_tags(session, [
            TagName.SECTION,
            TagName.ASIDE,
            TagName.NAV,
        ])

        # Text-ish nodes
        _run_for_tags(session, [
            TagName.P,
            TagName.H1,
            TagName.H2,
            TagName.H3,
            TagName.H4,
            TagName.H5,
            TagName.H6,
            TagName.CODE,
            TagName.CITE,
            TagName.BLOCKQUOTE,
        ])
