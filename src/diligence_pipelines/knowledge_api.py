from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from diligence_pipelines.settings import Settings
from diligence_pipelines.storage.factory import postgres_dsn


SOURCE_LABELS = {
    "sec_edgar": "SEC EDGAR",
    "gleif": "GLEIF",
    "openalex": "OpenAlex",
    "uspto_patents": "USPTO",
    "uspto_patents_index": "USPTO index",
}
SYNTHETIC_SOURCE_IDS = {"synthetic_fixture", "openalex_fixture", "uspto_patents_fixture"}


def _records(connection, table: str, key: str, limit: int) -> list[dict]:
    # Table and key are internal allowlisted constants; values are parameterized.
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT DISTINCT ON ({key}) {key}, run_id, record, created_at
            FROM diligence.{table}
            ORDER BY {key}, created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [{"key": row[0], "run_id": str(row[1]), "record": row[2], "created_at": row[3].isoformat()} for row in cursor.fetchall()]


def _patent_catalog_records(connection, limit: int) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", ("diligence.patent_catalog",))
        if cursor.fetchone()[0] is None:
            return _records(connection, "patent_records", "patent_id", limit)
        cursor.execute("""
            SELECT patent_id, record, updated_at
            FROM diligence.patent_catalog
            ORDER BY updated_at DESC, patent_id
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
    if rows:
        return [{"key": row[0], "run_id": "canonical", "record": row[1], "created_at": row[2].isoformat()} for row in rows]
    return _records(connection, "patent_records", "patent_id", limit)


def _edge_records(connection, table: str, limit: int) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT record FROM diligence.{table} ORDER BY run_id DESC LIMIT %s", (limit,))
        return [{"record": row[0], "created_at": None} for row in cursor.fetchall()]


def _raw_sources(connection, limit: int) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT source_id, source_uri, status_code, adapter_version, retrieved_at, content_sha256
            FROM diligence.raw_captures
            ORDER BY retrieved_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [
            {"source_id": row[0], "source_uri": row[1], "status_code": row[2], "adapter_version": row[3], "retrieved_at": row[4].isoformat(), "content_sha256": row[5]}
            for row in cursor.fetchall()
        ]


def _add_node(nodes: dict[str, dict], node_id: str, *, name: str, kind: str, node_type: str, pipe: str, fields: dict) -> None:
    if node_id not in nodes:
        nodes[node_id] = {"id": node_id, "name": name, "kind": kind, "type": node_type, "pipe": pipe, "fields": fields}


def build_graph(connection, limit: int = 80) -> dict:
    limit = max(1, min(limit, 500))
    entities = _records(connection, "entities", "entity_id", limit)
    works = _records(connection, "research_works", "work_id", limit)
    patents = _patent_catalog_records(connection, limit)
    aliases = _edge_records(connection, "entity_aliases", limit)
    assignments = _edge_records(connection, "patent_assignments", limit)
    inventors = _edge_records(connection, "inventor_edges", limit)
    institutions = _edge_records(connection, "institution_edges", limit)
    captures = _raw_sources(connection, min(max(limit * 10, 500), 5000))
    capture_sources = {f"source:{capture['content_sha256']}": capture["source_id"] for capture in captures}

    def is_real_record(record: dict) -> bool:
        source_id = record.get("source_id")
        if source_id in SYNTHETIC_SOURCE_IDS:
            return False
        source_record_id = record.get("source_record_id")
        return not source_record_id or capture_sources.get(source_record_id) not in SYNTHETIC_SOURCE_IDS

    entities = [row for row in entities if is_real_record(row["record"])]
    works = [row for row in works if is_real_record(row["record"])]
    patents = [row for row in patents if is_real_record(row["record"])]
    aliases = [row for row in aliases if is_real_record(row["record"])]
    assignments = [row for row in assignments if is_real_record(row["record"])]
    inventors = [row for row in inventors if is_real_record(row["record"])]
    institutions = [row for row in institutions if is_real_record(row["record"])]
    captures = [capture for capture in captures if capture["source_id"] not in SYNTHETIC_SOURCE_IDS]

    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str], dict] = {}

    def add_edge(a: str, b: str, label: str, class_name: str = "") -> None:
        if a in nodes and b in nodes:
            edges[(a, b, label)] = {"a": a, "b": b, "label": label, "className": class_name}

    for capture in captures:
        source_id = capture["source_id"]
        node_id = f"source:{source_id}"
        _add_node(nodes, node_id, name=SOURCE_LABELS.get(source_id, source_id), kind="Source", node_type="source", pipe="02" if "openalex" in source_id or "uspto" in source_id else "01", fields=capture)

    for row in entities:
        record = row["record"]
        _add_node(nodes, f"entity:{row['key']}", name=record.get("canonical_name", row["key"]), kind=f"Entity · {record.get('entity_type', 'organization')}", node_type="entity", pipe="01", fields={"entity_id": row["key"], "run_id": row["run_id"], "source_id": record.get("source_id"), "review": "source-derived"})

    for row in works:
        record = row["record"]
        work_id = row["key"]
        work_node = f"research:{work_id}"
        _add_node(nodes, work_node, name=record.get("title", work_id), kind=f"Research work · {work_id.rsplit('/', 1)[-1]}", node_type="research", pipe="02", fields={"work_id": work_id, "run_id": row["run_id"], "publication_date": record.get("publication_date"), "source_record_id": record.get("source_record_id")})
        source_id = record.get("source_id", "openalex")
        source_node = f"source:{source_id}"
        if source_node not in nodes:
            _add_node(nodes, source_node, name=SOURCE_LABELS.get(source_id, source_id), kind="Source", node_type="source", pipe="02", fields={"source_id": source_id})
        add_edge(source_node, work_node, "normalizes", "source")
        for author in record.get("authors", []):
            author_id = author.get("id") or f"name:{author.get('name', '')}"
            person_node = f"person:{author_id}"
            _add_node(nodes, person_node, name=author.get("name") or author_id, kind="Author", node_type="person", pipe="02", fields={"author_id": author_id, "relationship": "authorship", "review": "not employment evidence"})
            add_edge(work_node, person_node, "authorship")
        for institution in record.get("institutions", []):
            institution_id = institution.get("id") or f"name:{institution.get('name', '')}"
            institution_node = f"institution:{institution_id}"
            _add_node(nodes, institution_node, name=institution.get("name") or institution_id, kind="Institution", node_type="institution", pipe="02", fields={"institution_id": institution_id, "relationship": "authorship affiliation"})
            add_edge(work_node, institution_node, "institution")

    for row in patents:
        record = row["record"]
        patent_id = row["key"]
        patent_node = f"patent:{patent_id}"
        _add_node(nodes, patent_node, name=record.get("title", patent_id), kind=f"Patent · {patent_id}", node_type="patent", pipe="02", fields={"patent_id": patent_id, "run_id": row["run_id"], "source_record_id": record.get("source_record_id"), "review": "source evidence"})
        source_id = record.get("source_id", "uspto_patents")
        source_node = f"source:{source_id}"
        if source_node not in nodes:
            _add_node(nodes, source_node, name=SOURCE_LABELS.get(source_id, source_id), kind="Source", node_type="source", pipe="02", fields={"source_id": source_id})
        add_edge(source_node, patent_node, "normalizes", "source")

    for row in inventors:
        record = row["record"]
        patent_node = f"patent:{record.get('patent_id')}"
        inventor_id = record.get("inventor_id") or record.get("inventor_name")
        person_node = f"person:inventor:{inventor_id}"
        _add_node(nodes, person_node, name=record.get("inventor_name") or str(inventor_id), kind="Inventor", node_type="person", pipe="02", fields={"inventor_id": inventor_id, "relationship": "appears as inventor", "review": "not employment evidence"})
        add_edge(patent_node, person_node, "inventor record")

    for row in institutions:
        record = row["record"]
        work_node = f"research:{record.get('work_id')}"
        institution_id = record.get("institution_id")
        institution_node = f"institution:{institution_id}"
        _add_node(nodes, institution_node, name=record.get("institution_name") or str(institution_id), kind="Institution", node_type="institution", pipe="02", fields={"institution_id": institution_id, "relationship": record.get("relationship_type")})
        add_edge(work_node, institution_node, "institution")

    for row in assignments:
        record = row["record"]
        patent_node = f"patent:{record.get('patent_id')}"
        assignee = record.get("assignee_name") or record.get("assignee_id") or "Unknown assignee"
        assignee_node = f"assignee:{record.get('assignee_id') or assignee}"
        _add_node(nodes, assignee_node, name=assignee, kind="Assignee record", node_type="person", pipe="02", fields={"assignee_id": record.get("assignee_id"), "relationship": "patent assignee record", "review": "entity matching deferred"})
        add_edge(patent_node, assignee_node, "assignee record", "candidate")

    for row in aliases:
        record = row["record"]
        entity_node = f"entity:{record.get('entity_id')}"
        alias_node = f"alias:{record.get('record_id')}"
        _add_node(nodes, alias_node, name=record.get("alias", "LEI alias"), kind="Exact identifier alias", node_type="capture", pipe="01", fields={"match_method": record.get("match_method"), "match_score": record.get("match_score"), "review_status": record.get("review_status")})
        add_edge(entity_node, alias_node, "identifier")

    _layout(nodes)
    return {"mode": "postgres", "node_count": len(nodes), "edge_count": len(edges), "nodes": list(nodes.values()), "edges": list(edges.values())}


def _layout(nodes: dict[str, dict]) -> None:
    columns = {"source": 95, "capture": 275, "entity": 500, "patent": 720, "research": 720, "person": 720, "institution": 1000, "topic": 1000}
    grouped: dict[float, list[dict]] = {}
    for node in nodes.values():
        x = columns.get(node["type"], 500)
        grouped.setdefault(x, []).append(node)
    for x, group in grouped.items():
        step = min(92, 420 / max(1, len(group) - 1))
        for index, node in enumerate(group):
            node["x"] = x
            node["y"] = 105 + index * step


def load_graph(settings: Settings, limit: int = 80) -> dict:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install PostgreSQL support with: pip install -e '.[postgres]'") from exc
    with psycopg.connect(postgres_dsn(settings)) as connection:
        return build_graph(connection, limit=limit)


class KnowledgeHandler(BaseHTTPRequestHandler):
    settings = Settings()

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "http://localhost:5173")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {"status": "ok", "backend": "postgres"})
            return
        if parsed.path != "/api/knowledge/graph":
            self._send(404, {"error": "Not found"})
            return
        try:
            limit = int(parse_qs(parsed.query).get("limit", ["80"])[0])
            self._send(200, load_graph(self.settings, limit=limit))
        except Exception as exc:  # Boundary converts connection/schema errors into safe API responses.
            self._send(503, {"error": "Unable to load the PostgreSQL knowledge graph", "detail": str(exc)})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Read-only Pipeline 01/02 PostgreSQL graph API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    KnowledgeHandler.settings = Settings.from_env()
    server = ThreadingHTTPServer((args.host, args.port), KnowledgeHandler)
    print(f"Knowledge API listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
