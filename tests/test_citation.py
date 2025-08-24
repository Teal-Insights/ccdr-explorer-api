from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from db.db import engine
from db.schema import Publication


def run():
    with Session(engine) as session:
        stmt = (
            select(Publication)
            .options(selectinload(Publication.documents))
            .limit(1)
        )
        pub = session.exec(stmt).first()
        if not pub:
            print("No publications found.")
            return
        print(f"Publication ID: {pub.id}")
        print(f"Citation: {pub.citation}")


def test_print_citation():
    # Run with: pytest -s tests/test_citation.py::test_print_citation
    run()


if __name__ == "__main__":
    # Or: python tests/test_citation.py
    run()