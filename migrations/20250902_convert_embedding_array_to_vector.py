import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment from .env by default
load_dotenv(os.getenv("ENVIRONMENT", ".env"))


def get_database_url() -> str:
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "ccdr-explorer-db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _fetch_scalar(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar()


def _fetch_all(conn, sql: str, **params):
    return conn.execute(text(sql), params).fetchall()


def ensure_extension(conn) -> None:
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def precheck_dimensions_array(conn, expected_dims: int) -> None:
    bad = _fetch_scalar(
        conn,
        "SELECT COUNT(*) FROM embedding WHERE cardinality(embedding_vector) <> :dims",
        dims=expected_dims,
    )
    if bad and int(bad) != 0:
        raise RuntimeError(f"Found {bad} embeddings with wrong dimensionality; aborting.")


def precheck_dimensions_vector(conn, expected_dims: int) -> None:
    bad = _fetch_scalar(
        conn,
        "SELECT COUNT(*) FROM embedding WHERE vector_dims(embedding_vector) <> :dims",
        dims=expected_dims,
    )
    if bad and int(bad) != 0:
        raise RuntimeError(f"Found {bad} vector embeddings with wrong dimensionality; aborting.")


def get_column_type(conn) -> str:
    row = conn.execute(
        text(
            """
            SELECT atttypid::regtype::text AS type
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'embedding' AND a.attname = 'embedding_vector'
              AND NOT a.attisdropped
            """
        )
    ).first()
    return row[0] if row else ""


def convert_array_to_vector(conn, dims: int) -> None:
    # Use USING cast to convert float8[] -> vector(dims)
    conn.execute(text(f"ALTER TABLE embedding ALTER COLUMN embedding_vector TYPE vector({dims}) USING (embedding_vector::vector({dims}))"))


def create_vector_index(conn, index_name: str = "embedding_vec_cosine_ivfflat", use_hnsw: bool = False) -> None:
    # Try to give the builder more room within the transaction
    try:
        conn.execute(text("SET LOCAL maintenance_work_mem = '256MB'"))
    except Exception:
        pass

    if use_hnsw:
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS " + index_name + " ON embedding USING hnsw (embedding_vector vector_cosine_ops) WITH (m = 16, ef_construction = 200)"
        ))
        return

    # Retry ivfflat with decreasing list sizes if memory is tight
    last_err: Exception | None = None
    for lists in (100, 80, 64, 48, 32):
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS " + index_name + " ON embedding USING ivfflat (embedding_vector vector_cosine_ops) WITH (lists = :lists)"
            ), {"lists": lists})
            return
        except Exception as exc:  # e.g., ProgramLimitExceeded (maintenance_work_mem)
            last_err = exc
            continue
    if last_err:
        raise last_err


def postcheck_counts(conn, before_count: int) -> None:
    after_count = int(_fetch_scalar(conn, "SELECT COUNT(*) FROM embedding") or 0)
    if after_count != before_count:
        raise RuntimeError(f"Row count mismatch after conversion: before={before_count}, after={after_count}")


def main(expected_dims: int = 1536, use_hnsw: bool = False) -> None:
    engine = create_engine(get_database_url())
    with engine.begin() as conn:
        before_count = int(_fetch_scalar(conn, "SELECT COUNT(*) FROM embedding") or 0)

        # Always ensure extension first
        print("Ensuring pgvector extension exists...")
        ensure_extension(conn)

        # Pre-check current type and dimensions
        current_type = get_column_type(conn)
        print(f"Current type of embedding.embedding_vector: {current_type}")

        print(f"Validating all embeddings have {expected_dims} dimensions...")

        if current_type.startswith("vector"):
            precheck_dimensions_vector(conn, expected_dims)
            print("Column already uses pgvector; skipping type conversion.")
        else:
            precheck_dimensions_array(conn, expected_dims)
            print(f"Converting embedding_vector to vector({expected_dims})...")
            convert_array_to_vector(conn, expected_dims)

        print("Ensuring ANN index on embedding_vector (cosine) exists...")
        create_vector_index(conn, use_hnsw=use_hnsw)

        print("Verifying row counts post-operations...")
        postcheck_counts(conn, before_count)

        # Simple sanity: run a tiny query using the operator to confirm availability
        print("Sanity check: cosine operator available...")
        _ = _fetch_all(conn, "SELECT 1 FROM embedding ORDER BY embedding_vector <=> embedding_vector LIMIT 1")
        print("Migration complete.")


if __name__ == "__main__":
    # Adjust dims to 1536 for text-embedding-3-small
    main(expected_dims=1536, use_hnsw=False)
