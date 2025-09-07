# services/semantic_search.py
from typing import Iterable, List, Optional, Tuple, TypedDict, Union
from sqlmodel import Session, select
from sqlalchemy import text
from db.schema import Node, ISO3Country, GeoAggregate

class SearchResult(TypedDict):
    node_id: int
    document_id: int
    publication_id: Optional[int]
    distance: float
    similarity: float
    html: str

def embed_query(query: str, *, model: str = "text-embedding-3-small") -> List[float]:
    # Use your OPENAI_API_KEY in env
    from openai import OpenAI
    client = OpenAI()
    emb = client.embeddings.create(model=model, input=query)
    return emb.data[0].embedding  # List[float]

def semantic_search_nodes(
    session: Session,
    query_text: str,
    *,
    top_k: int = 20,
    model_name: str = "text-embedding-3-small",
    document_ids: Optional[Iterable[int]] = None,
    publication_ids: Optional[Iterable[int]] = None,
    tag_names: Optional[Iterable[str]] = None,           # values from TagName enum
    section_types: Optional[Iterable[str]] = None,       # values from SectionType enum
    include_citation_data: bool = True,
    geographies: Optional[Iterable[Union[str, ISO3Country, GeoAggregate]]] = None,
) -> List[SearchResult]:
    qvec = embed_query(query_text, model=model_name)

    # NOTE: Uses pgvector cosine distance operator in ORDER BY.
    # If your column type is `vector`, this works as-is.
    # If your column is float[] in the DB, adjust migration to vector or cast appropriately.
    sql = """
        SELECT
          e.id AS embedding_id,
          cd.id AS content_data_id,
          n.id AS node_id,
          n.document_id AS document_id,
          d.publication_id AS publication_id,
          (e.embedding_vector <=> ((:qvec)::double precision[]::vector(1536))) AS distance
        FROM embedding e
        JOIN contentdata cd ON cd.id = e.content_data_id
        JOIN node n ON n.id = cd.node_id
        JOIN document d ON d.id = n.document_id
        LEFT JOIN publication p ON p.id = d.publication_id
        WHERE 1=1
          -- dynamic filters below
          {doc_filter}
          {pub_filter}
          {tag_filter}
          {sect_filter}
          {geog_filter}
        ORDER BY e.embedding_vector <=> ((:qvec)::double precision[]::vector(1536))
        LIMIT :top_k
    """

    def make_filter(column: str, values: Optional[Iterable]) -> Tuple[str, dict]:
        if values:
            return f"AND {column} = ANY(:{column}_arr)", {f"{column}_arr": list(values)}
        return "", {}

    doc_sql, doc_params = make_filter("n.document_id", document_ids)
    pub_sql, pub_params = make_filter("d.publication_id", publication_ids)

    tag_sql, tag_params = ("", {})
    if tag_names:
        tag_sql = "AND n.tag_name = ANY(:tag_name_arr)"
        tag_params = {"tag_name_arr": list(tag_names)}

    sect_sql, sect_params = ("", {})
    if section_types:
        sect_sql = "AND n.section_type = ANY(:section_type_arr)"
        sect_params = {"section_type_arr": list(section_types)}

    # Geography filter: split inputs into ISO3 codes vs aggregates
    geog_sql, geog_params = ("", {})
    if geographies:
        iso3_list: List[str] = []
        agg_list: List[str] = []

        for g in geographies:
            value = getattr(g, "value", g)
            if isinstance(value, str):
                if value.upper() in {c.value for c in ISO3Country}:
                    iso3_list.append(value.upper())
                else:
                    agg_list.append(value)
        # Deduplicate
        iso3_list = list(dict.fromkeys(iso3_list))
        agg_list = list(dict.fromkeys(agg_list))

        geog_clauses: List[str] = []
        if iso3_list:
            geog_clauses.append(
                "EXISTS (\n"
                "  SELECT 1 FROM jsonb_array_elements_text(p.publication_metadata->'geographical'->'iso3_country_codes') iso(code)\n"
                "  WHERE iso.code = ANY(:iso3_arr)\n"
                ")"
            )
        if agg_list:
            geog_clauses.append(
                "EXISTS (\n"
                "  SELECT 1 FROM jsonb_array_elements_text(p.publication_metadata->'geographical'->'aggregates') agg(val)\n"
                "  WHERE agg.val = ANY(:agg_arr)\n"
                ")"
            )
        if geog_clauses:
            geog_sql = "AND ( " + " OR ".join(geog_clauses) + " )"
            if iso3_list:
                geog_params["iso3_arr"] = iso3_list
            if agg_list:
                geog_params["agg_arr"] = agg_list

    rendered = sql.format(
        doc_filter=doc_sql,
        pub_filter=pub_sql,
        tag_filter=tag_sql,
        sect_filter=sect_sql,
        geog_filter=geog_sql,
    )

    params = {
        "qvec": qvec,
        "top_k": top_k,
        **doc_params,
        **pub_params,
        **tag_params,
        **sect_params,
        **geog_params,
    }

    rows = session.exec(text(rendered), params=params).mappings().all()

    # Load nodes and render HTML
    node_ids = [r["node_id"] for r in rows]
    nodes_by_id = {}
    if node_ids:
        nodes = session.exec(select(Node).where(Node.id.in_(node_ids))).all()
        nodes_by_id = {n.id: n for n in nodes}

    results: List[SearchResult] = []
    for r in rows:
        node = nodes_by_id.get(r["node_id"])
        html = node.to_html(
            include_citation_data=include_citation_data,
            pretty=False,
        ) if node else ""
        dist = float(r["distance"])
        results.append({
            "node_id": int(r["node_id"]),
            "document_id": int(r["document_id"]),
            "publication_id": int(r["publication_id"]) if r["publication_id"] is not None else None,
            "distance": dist,
            "similarity": 1.0 - dist,  # cosine distance -> similarity
            "html": html,
        })
    return results

if __name__ == "__main__":
    from db.db import engine

    # Ad hoc test
    with Session(engine) as session:
        results = semantic_search_nodes(
            session,
            "clean cooking program",
            geographies=["USA", GeoAggregate.CONTINENT_AF]
        )
        print(results)