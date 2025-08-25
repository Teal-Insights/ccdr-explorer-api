from datetime import date
import pytest

from sqlmodel import Session

from db.db import engine
from db.schema import (
    SQLModel,
    Publication,
    Document,
    DocumentType,
    Node,
    TagName,
    ContentData,
    EmbeddingSource,
)


def setup_module(module):
    # Ensure tables exist; tests may run against a dev DB
    SQLModel.metadata.create_all(engine)


def create_pub_doc(session: Session):
    pub = Publication(
        title="Test",
        abstract=None,
        authors="A. Author",
        publication_date=date(2024, 1, 1),
        source="UnitTest",
        source_url="https://example.com/src",
        uri="https://example.com/uri",
    )
    doc = Document(
        publication=pub,
        type=DocumentType.MAIN,
        download_url="https://example.com/file",
        description="Doc",
        mime_type="text/html",
        charset="utf-8",
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


def test_description_allowed_for_img(session=None):
    with Session(engine) as session:
        doc = create_pub_doc(session)
        node = Node(
            document=doc,
            tag_name=TagName.IMG,
            sequence_in_parent=0,
        )
        session.add(node)
        session.flush()
        content = ContentData(
            node=node,
            text_content=None,
            storage_url="https://example.com/img.png",
            description="alt text",
            caption=None,
            embedding_source=EmbeddingSource.DESCRIPTION,
        )
        session.add(content)
        session.commit()


def test_description_rejected_for_paragraph(session=None):
    with Session(engine) as session:
        doc = create_pub_doc(session)
        node = Node(
            document=doc,
            tag_name=TagName.P,
            sequence_in_parent=0,
        )
        session.add(node)
        session.flush()
        content = ContentData(
            node=node,
            text_content="Hello",
            description="should fail",
            caption=None,
            embedding_source=EmbeddingSource.TEXT_CONTENT,
        )
        session.add(content)
        with pytest.raises(ValueError):
            session.commit()


