import os
import sys
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Sequence, Generator

from dotenv import dotenv_values
from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert


def _build_db_url(config: Dict[str, str]) -> str:
    """Build a PostgreSQL SQLAlchemy URL from a dotenv-style config mapping."""
    user = config.get("POSTGRES_USER", "postgres")
    password = config.get("POSTGRES_PASSWORD", "postgres")
    host = config.get("POSTGRES_HOST", "localhost")
    port = config.get("POSTGRES_PORT", "5432")
    db = config.get("POSTGRES_DB", "ccdr-explorer-db")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def _load_envs(local_env_path: str = ".env", prod_env_path: str = ".env.production") -> Dict[str, Dict[str, str]]:
    local_cfg = dotenv_values(local_env_path)
    if not local_cfg:
        raise RuntimeError(f"Could not load local environment from {local_env_path}")
    prod_cfg = dotenv_values(prod_env_path)
    if not prod_cfg:
        raise RuntimeError(f"Could not load production environment from {prod_env_path}")
    return {"local": dict(local_cfg), "prod": dict(prod_cfg)}


def _reflect_tables(engine: Engine, table_names: Sequence[str]) -> Dict[str, Table]:
    meta = MetaData()
    meta.reflect(bind=engine, only=table_names)
    return {tname: meta.tables[tname] for tname in table_names}


def _stream_rows(local_conn: Connection, sql: str, params: Dict[str, Any] | None, chunk_size: int) -> Generator[List[Dict[str, Any]], None, None]:
    """Stream rows from a query in chunks to keep memory bounded."""
    res = local_conn.execution_options(stream_results=True).execute(text(sql), params or {})
    while True:
        rows = res.fetchmany(chunk_size)
        if not rows:
            break
        yield [dict(r._mapping) for r in rows]


def _describe_table(conn: Connection, table_name: str) -> List[Dict[str, Any]]:
    """Return a normalized description of a table's columns for schema comparison.
    Captures column name, data type, is_nullable, default expression, and identity.
    """
    sql = text(
        """
        SELECT
            a.attname AS column_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
            NOT a.attnotnull AS is_nullable,
            pg_get_expr(ad.adbin, ad.adrelid) AS column_default,
            CASE WHEN a.attidentity IN ('a','d') THEN a.attidentity ELSE '' END AS identity
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        LEFT JOIN pg_attrdef ad ON a.attrelid = ad.adrelid AND a.attnum = ad.adnum
        WHERE c.relkind = 'r'
          AND n.nspname = 'public'
          AND c.relname = :tname
          AND a.attnum > 0 AND NOT a.attisdropped
        ORDER BY a.attnum
        """
    )
    res = conn.execute(sql, {"tname": table_name})
    rows = [dict(r._mapping) for r in res.fetchall()]
    # Normalize defaults that embed sequence names to a placeholder
    for r in rows:
        d = r.get("column_default") or ""
        if isinstance(d, str) and "nextval(" in d:
            r["column_default"] = "nextval(...)"
    return rows


def _assert_schemas_match(local_conn: Connection, prod_conn: Connection, table_names: Sequence[str]) -> None:
    mismatches: List[str] = []
    for t in table_names:
        ldesc = _describe_table(local_conn, t)
        pdesc = _describe_table(prod_conn, t)
        if ldesc != pdesc:
            mismatches.append(t)
    if mismatches:
        raise RuntimeError(f"Schema mismatch for tables: {', '.join(mismatches)}")


def _fetch_pub_doc_fingerprints(conn: Connection) -> Dict[str, Any]:
    """Return simple counts and checksum-ish fingerprints for publication and document.
    Fingerprint is based on sorted array of IDs and basic stable fields to avoid huge payloads.
    """
    fp: Dict[str, Any] = {}
    # publication
    pub_count = conn.execute(text("SELECT COUNT(*) FROM publication")).scalar_one()
    pub_ids = conn.execute(text("SELECT array_agg(id ORDER BY id) FROM publication")).scalar_one()
    # a minimal stable fingerprint on documents and publications
    pub_minmax = conn.execute(text("SELECT COALESCE(MIN(id),0), COALESCE(MAX(id),0) FROM publication")).first()
    fp["publication"] = {"count": pub_count, "ids": pub_ids or [], "minmax": tuple(pub_minmax) if pub_minmax else (0, 0)}

    # document
    doc_count = conn.execute(text("SELECT COUNT(*) FROM document")).scalar_one()
    doc_ids = conn.execute(text("SELECT array_agg(id ORDER BY id) FROM document")).scalar_one()
    doc_minmax = conn.execute(text("SELECT COALESCE(MIN(id),0), COALESCE(MAX(id),0) FROM document")).first()
    fp["document"] = {"count": doc_count, "ids": doc_ids or [], "minmax": tuple(doc_minmax) if doc_minmax else (0, 0)}
    return fp


def _assert_pub_doc_match(local_conn: Connection, prod_conn: Connection) -> None:
    lfp = _fetch_pub_doc_fingerprints(local_conn)
    pfp = _fetch_pub_doc_fingerprints(prod_conn)
    for t in ("publication", "document"):
        if lfp[t]["count"] != pfp[t]["count"]:
            raise RuntimeError(f"{t} row count differs (local={lfp[t]['count']}, prod={pfp[t]['count']})")
        if lfp[t]["ids"] != pfp[t]["ids"]:
            raise RuntimeError(f"{t} id sets differ between local and prod")
        if lfp[t]["minmax"] != pfp[t]["minmax"]:
            raise RuntimeError(f"{t} id min/max differ between local and prod")


def _assert_target_empty(prod_conn: Connection, table_names: Sequence[str]) -> None:
    non_empty: List[str] = []
    for t in table_names:
        cnt = prod_conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar_one()
        if cnt != 0:
            non_empty.append(f"{t}({cnt})")
    if non_empty:
        raise RuntimeError(f"Target database is not empty for: {', '.join(non_empty)}")

@contextmanager
def _connect(engine: Engine) -> Iterable[Connection]:
    with engine.connect() as conn:
        yield conn


def _chunked(items: List[Dict[str, Any]], size: int) -> Iterable[List[Dict[str, Any]]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


_NODE_RECURSIVE_SQL = """
WITH RECURSIVE node_tree AS (
    SELECT n.id, n.parent_id, 1 AS depth
    FROM node n
    WHERE n.parent_id IS NULL
    UNION ALL
    SELECT n.id, n.parent_id, nt.depth + 1
    FROM node n
    JOIN node_tree nt ON n.parent_id = nt.id
)
SELECT n.id,
       n.document_id,
       n.tag_name,
       n.section_type,
       n.parent_id,
       n.sequence_in_parent,
       n.positional_data,
       nt.depth
FROM node n
JOIN node_tree nt ON n.id = nt.id
ORDER BY nt.depth ASC, n.sequence_in_parent ASC, n.id ASC
"""


_CONTENTDATA_SQL = """
SELECT id, node_id, text_content, storage_url, description, caption, embedding_source
FROM contentdata
ORDER BY id ASC
"""


_EMBEDDING_SQL = """
SELECT id, content_data_id, embedding_vector, model_name, created_at
FROM embedding
ORDER BY id ASC
"""


def _ensure_documents_exist(prod_conn: Connection, document_ids: List[int]) -> None:
    if not document_ids:
        return
    # Check that all referenced document IDs exist in production
    res = prod_conn.execute(
        text("SELECT id FROM document WHERE id = ANY(:doc_ids)").bindparams(doc_ids=document_ids)
    )
    present = {row.id for row in res.fetchall()}
    missing = sorted(set(document_ids) - present)
    if missing:
        raise RuntimeError(
            f"Aborting: {len(missing)} document ids referenced by local nodes are missing in production. Example: {missing[:10]}"
        )


def _reset_sequences(prod_conn: Connection, table_names: Sequence[str]) -> None:
    for tname in table_names:
        sql = f"SELECT setval(pg_get_serial_sequence('{tname}', 'id'), COALESCE((SELECT MAX(id) FROM {tname}), 0), true)"
        prod_conn.execute(text(sql))


def sync_local_to_prod(
    local_env_path: str = ".env",
    prod_env_path: str = ".env.production",
    batch_size: int = 2000,
    embedding_page_size: int = 50,
    strict_empty: bool = True,
) -> None:
    envs = _load_envs(local_env_path, prod_env_path)
    local_engine = create_engine(_build_db_url(envs["local"]))
    prod_engine = create_engine(_build_db_url(envs["prod"]))

    with _connect(local_engine) as lconn, prod_engine.begin() as pconn:
        # 0) Pre-flight sanity checks
        print("Checking schema equality for key tables...")
        _assert_schemas_match(lconn, pconn, ("publication", "document", "node", "contentdata", "embedding"))
        print("Schema checks passed.")

        print("Checking publication/document parity (ids and counts)...")
        _assert_pub_doc_match(lconn, pconn)
        print("Publication/document parity checks passed.")

        if strict_empty:
            print("Ensuring target tables are empty (node, contentdata, embedding)...")
            _assert_target_empty(pconn, ("node", "contentdata", "embedding"))
            print("Target emptiness checks passed.")
        else:
            print("Strict emptiness checks disabled (resume mode). Skipping target-emptiness assertion.")
        # Reflect destination (prod) tables for type-aware insertions
        tables = _reflect_tables(pconn.engine, ("node", "contentdata", "embedding", "document"))
        node_table: Table = tables["node"]
        contentdata_table: Table = tables["contentdata"]
        embedding_table: Table = tables["embedding"]
        # Reflect document to assert existence but we don't use the Table object further

        # 1) Read counts from local and verify document references via a distinct query
        local_node_count = lconn.execute(text("SELECT COUNT(*) FROM node")).scalar_one()
        local_content_count = lconn.execute(text("SELECT COUNT(*) FROM contentdata")).scalar_one()
        local_embedding_count = lconn.execute(text("SELECT COUNT(*) FROM embedding")).scalar_one()
        print(f"Local counts — nodes: {local_node_count}, contentdata: {local_content_count}, embeddings: {local_embedding_count}")

        # Verify docs referenced by nodes exist in prod without loading all nodes
        doc_ids_res = lconn.execute(text("SELECT DISTINCT document_id FROM node WHERE document_id IS NOT NULL"))
        doc_ids = [row[0] for row in doc_ids_res.fetchall()]
        print(f"Verifying {len(doc_ids)} distinct document ids exist on production...")
        _ensure_documents_exist(pconn, doc_ids)
        print("Document id parity check passed.")

        # 2) Prepare and apply changes on production
        # 2a) Upsert nodes in parent-first order
        print("Upserting nodes to production (parent-first order, streaming)...")
        node_insert = pg_insert(node_table)
        node_update_cols = {c.name: node_insert.excluded[c.name] for c in node_table.columns if c.name != "id"}
        for rows in _stream_rows(lconn, _NODE_RECURSIVE_SQL, None, batch_size):
            chunk = [
                {
                    "id": r["id"],
                    "document_id": r["document_id"],
                    "tag_name": r["tag_name"],
                    "section_type": r["section_type"],
                    "parent_id": r["parent_id"],
                    "sequence_in_parent": r["sequence_in_parent"],
                    "positional_data": r["positional_data"],
                }
                for r in rows
            ]
            if chunk:
                pconn.execute(
                    node_insert.on_conflict_do_update(
                        index_elements=[node_table.c.id], set_=node_update_cols
                    ),
                    chunk,
                )

        # 2b) Insert contentdata and embeddings from local copies (streamed)
        print("Inserting contentdata (streaming)...")
        if strict_empty:
            for rows in _stream_rows(lconn, _CONTENTDATA_SQL, None, batch_size):
                if rows:
                    pconn.execute(contentdata_table.insert(), rows)
        else:
            cd_insert = pg_insert(contentdata_table)
            cd_update_cols = {c.name: cd_insert.excluded[c.name] for c in contentdata_table.columns if c.name != "id"}
            for rows in _stream_rows(lconn, _CONTENTDATA_SQL, None, batch_size):
                if rows:
                    pconn.execute(
                        cd_insert.on_conflict_do_update(index_elements=[contentdata_table.c.id], set_=cd_update_cols),
                        rows,
                    )

        print(f"Inserting embeddings (streaming, page_size={embedding_page_size})...")
        # Use a reduced insertmanyvalues page size for very large rows (arrays)
        pconn_small = pconn.execution_options(insertmanyvalues_page_size=embedding_page_size)
        if strict_empty:
            for rows in _stream_rows(lconn, _EMBEDDING_SQL, None, embedding_page_size):
                if rows:
                    pconn_small.execute(embedding_table.insert(), rows)
        else:
            emb_insert = pg_insert(embedding_table)
            emb_update_cols = {c.name: emb_insert.excluded[c.name] for c in embedding_table.columns if c.name != "id"}
            for rows in _stream_rows(lconn, _EMBEDDING_SQL, None, embedding_page_size):
                if rows:
                    pconn_small.execute(
                        emb_insert.on_conflict_do_update(index_elements=[embedding_table.c.id], set_=emb_update_cols),
                        rows,
                    )

        # 2c) Reset sequences
        print("Resetting sequences for node, contentdata, embedding...")
        _reset_sequences(pconn, ("node", "contentdata", "embedding"))

        # 2d) Post-insert sanity checks (counts)
        node_count_prod = pconn.execute(select(text("COUNT(*)")).select_from(node_table)).scalar_one()
        content_count_prod = pconn.execute(select(text("COUNT(*)")).select_from(contentdata_table)).scalar_one()
        embedding_count_prod = pconn.execute(select(text("COUNT(*)")).select_from(embedding_table)).scalar_one()
        if node_count_prod < local_node_count:
            raise RuntimeError("Fewer nodes in production than local after sync; aborting.")
        if content_count_prod != local_content_count:
            raise RuntimeError("ContentData row count mismatch after sync; aborting.")
        if embedding_count_prod != local_embedding_count:
            raise RuntimeError("Embedding row count mismatch after sync; aborting.")

        print("Sync complete.")


if __name__ == "__main__":
    local_env = os.environ.get("LOCAL_ENV_FILE", ".env")
    prod_env = os.environ.get("PROD_ENV_FILE", ".env.production")
    embed_ps = int(os.environ.get("EMBED_PAGE_SIZE", "50"))
    strict = os.environ.get("STRICT_EMPTY", "1") not in ("0", "false", "False")
    try:
        sync_local_to_prod(local_env, prod_env, embedding_page_size=embed_ps, strict_empty=strict)
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)

