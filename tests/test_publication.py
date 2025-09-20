from sqlmodel import Session, select
from sqlalchemy.orm import selectinload
from db.db import engine
from db.schema import Publication

def main():
    with Session(engine) as session:
        stmt = (
            select(Publication)
            .options(selectinload(Publication.documents))
            .limit(1)
        )
        pub = session.exec(stmt).first()
        print(pub.model_dump_json())

if __name__ == "__main__":
    main()