from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

from diligence_pipelines.settings import Settings
from diligence_pipelines.storage.factory import postgres_dsn


SOURCE_LABELS = {
    "sec_edgar": "SEC EDGAR",
    "gleif": "GLEIF",
    "openalex": "OpenAlex",
    "uspto_patents": "USPTO",
    "uspto_patents_index": "USPTO index",
    "usaspending": "USAspending",
    "gdelt_doc": "GDELT DOC 2.0",
}
SYNTHETIC_SOURCE_IDS = {"synthetic_fixture", "openalex_fixture", "uspto_patents_fixture"}
SOURCE_PIPELINES = {"sec_edgar": "01", "gleif": "01", "openalex": "02", "uspto_patents": "02", "uspto_patents_index": "02", "usaspending": "04", "gdelt_doc": "05"}


class ReviewConflictError(ValueError):
    """Raised when an approval would create competing accepted entity matches."""


def _records(connection, table: str, key: str, limit: int) -> list[dict]:
    # Table and key are internal allowlisted constants; values are parameterized.
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {key}, run_id, record, created_at
            FROM (
                SELECT DISTINCT ON ({key}) {key}, run_id, record, created_at
                FROM diligence.{table}
                ORDER BY {key}, created_at DESC
            ) AS latest_records
            ORDER BY created_at DESC, {key}
            LIMIT %s
            """,
            (limit,),
        )
        return [{"key": row[0], "run_id": str(row[1]), "record": row[2], "created_at": row[3].isoformat()} for row in cursor.fetchall()]


def _table_exists(connection, table: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", (f"diligence.{table}",))
        return cursor.fetchone()[0] is not None


def _optional_records(connection, table: str, key: str, limit: int) -> list[dict]:
    return _records(connection, table, key, limit) if _table_exists(connection, table) else []


def _match_candidate_records(connection, limit: int) -> list[dict]:
    """Load the latest decision for each candidate without assuming a legacy timestamp column."""
    if not _table_exists(connection, "match_candidates"):
        return []
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT candidate_id, run_id, record, COALESCE(record->>'published_at', record->>'reviewed_at') AS reviewed_at
            FROM (
                SELECT DISTINCT ON (candidate_id) candidate_id, run_id, record
                FROM diligence.match_candidates
                ORDER BY candidate_id, record->>'published_at' DESC NULLS LAST, record->>'reviewed_at' DESC NULLS LAST, run_id DESC
            ) AS latest_candidates
            ORDER BY reviewed_at DESC NULLS LAST, candidate_id
            LIMIT %s
            """,
            (limit,),
        )
        candidates = [{"key": row[0], "run_id": str(row[1]), "record": row[2], "created_at": row[3]} for row in cursor.fetchall()]
    decisions = _review_decision_history(connection)
    for candidate in candidates:
        history = decisions.get(candidate["key"], [])
        if not history:
            candidate["record"] = {**candidate["record"], "review_history": []}
            continue
        latest = history[-1]
        candidate["record"] = {
            **candidate["record"],
            "review_status": latest["review_status"],
            "decision": latest["action"],
            "reviewer": latest["reviewer"],
            "reviewed_at": latest["decided_at"],
            "review_note": latest["note"],
            "review_history": history,
        }
    return candidates


def _review_decision_history(connection) -> dict[str, list[dict]]:
    if not _table_exists(connection, "match_review_decisions"):
        return {}
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT candidate_id, record, created_at
            FROM diligence.match_review_decisions
            ORDER BY candidate_id, created_at, decision_id
        """)
        histories: dict[str, list[dict]] = {}
        for candidate_id, record, created_at in cursor.fetchall():
            histories.setdefault(candidate_id, []).append({
                "decisionId": record.get("decision_id"),
                "action": record.get("action"),
                "review_status": record.get("review_status"),
                "previous_review_status": record.get("previous_review_status"),
                "reviewer": record.get("reviewer"),
                "note": record.get("note"),
                "decided_at": record.get("decided_at") or created_at.isoformat(),
            })
    return histories


def _sector_reviewer(settings: Settings, sector: str | None) -> str:
    if not sector:
        raise ValueError("Candidate has no sector; add one before it can be reviewed")
    path = Path(settings.sector_reviewer_config)
    if not path.exists():
        raise ValueError("Sector reviewer configuration is unavailable")
    payload = yaml.safe_load(path.read_text()) or {}
    reviewer = payload.get("sectors", {}).get(sector, {}).get("reviewer") if isinstance(payload, dict) else None
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError(f"No configured reviewer for sector: {sector}")
    return reviewer.strip()


def _ensure_review_decision_table(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS diligence.match_review_decisions (
                decision_id uuid PRIMARY KEY,
                candidate_id text NOT NULL,
                record jsonb NOT NULL,
                created_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS match_review_decisions_candidate_created_at_idx
            ON diligence.match_review_decisions (candidate_id, created_at DESC)
        """)
    connection.commit()


def submit_review_decision(settings: Settings, candidate_id: str, action: str, note: str) -> dict:
    """Append a review event and return the refreshed graph; source candidates are never overwritten."""
    if action not in {"approve", "reject", "reopen"}:
        raise ValueError("Review action must be approve, reject, or reopen")
    if action in {"approve", "reject"} and not note.strip():
        raise ValueError("Approval and rejection require an analyst note")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install PostgreSQL support with: pip install -e '.[postgres]'") from exc
    with psycopg.connect(postgres_dsn(settings)) as connection:
        _ensure_review_decision_table(connection)
        candidates = _match_candidate_records(connection, limit=500)
        target = next((candidate for candidate in candidates if candidate["key"] == candidate_id), None)
        if not target:
            raise ValueError("Review candidate was not found")
        current = target["record"]
        current_status = current.get("review_status", "unreviewed")
        if action == "reopen" and current_status == "unreviewed":
            raise ValueError("This candidate is already pending review")
        if action == "approve" and current_status == "accepted":
            raise ValueError("This candidate is already accepted; reopen it before recording another decision")
        if action == "reject" and current_status == "rejected":
            raise ValueError("This candidate is already rejected; reopen it before recording another decision")
        sector = current.get("sector")
        reviewer = _sector_reviewer(settings, sector)
        review_status = {"approve": "accepted", "reject": "rejected", "reopen": "unreviewed"}[action]
        if action == "approve":
            conflicts = [
                candidate for candidate in candidates
                if candidate["key"] != candidate_id
                and candidate["record"].get("source_record_id") == current.get("source_record_id")
                and candidate["record"].get("review_status") == "accepted"
            ]
            if conflicts:
                raise ReviewConflictError("Another accepted match already uses this source record. Reopen or reject it before approving this candidate.")
        decided_at = datetime.now(timezone.utc).isoformat()
        decision = {
            "decision_id": str(uuid.uuid4()),
            "candidate_id": candidate_id,
            "action": action,
            "review_status": review_status,
            "previous_review_status": current_status,
            "sector": sector,
            "reviewer": reviewer,
            "note": note.strip() or "Reopened for further analyst review.",
            "decided_at": decided_at,
        }
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO diligence.match_review_decisions (decision_id, candidate_id, record)
                VALUES (%s, %s, %s)
            """, (decision["decision_id"], candidate_id, json.dumps(decision)))
        connection.commit()
        return build_graph(connection, limit=120)


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


def _optional_edge_records(connection, table: str, limit: int) -> list[dict]:
    return _edge_records(connection, table, limit) if _table_exists(connection, table) else []


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
    awards = _optional_records(connection, "awards", "record_id", limit)
    recipients = _optional_records(connection, "recipient_entities", "record_id", limit)
    documents = _optional_records(connection, "source_documents", "record_id", limit)
    event_candidates = _optional_records(connection, "event_candidates", "record_id", limit)
    entity_event_edges = _optional_edge_records(connection, "entity_event_edges", limit)
    match_candidates = _match_candidate_records(connection, limit)
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
    awards = [row for row in awards if is_real_record(row["record"])]
    recipients = [row for row in recipients if is_real_record(row["record"])]
    documents = [row for row in documents if is_real_record(row["record"])]
    event_candidates = [row for row in event_candidates if is_real_record(row["record"])]
    entity_event_edges = [row for row in entity_event_edges if is_real_record(row["record"])]
    match_candidates = [row for row in match_candidates if is_real_record(row["record"])]
    captures = [capture for capture in captures if capture["source_id"] not in SYNTHETIC_SOURCE_IDS]
    review_queue = [
        {
            "candidateId": row["key"],
            "sourceRecordId": row["record"].get("source_record_id"),
            "sourceName": row["record"].get("source_name"),
            "candidateEntityId": row["record"].get("candidate_entity_id"),
            "candidateEntityName": row["record"].get("candidate_entity_name"),
            "sector": row["record"].get("sector"),
            "matchScore": row["record"].get("match_score"),
            "matchMethod": row["record"].get("match_method"),
            "reviewStatus": row["record"].get("review_status", "unreviewed"),
            "reviewer": row["record"].get("reviewer"),
            "reviewNote": row["record"].get("review_note"),
            "reviewHistory": row["record"].get("review_history", []),
        }
        for row in match_candidates
    ]

    nodes: dict[str, dict] = {}
    edges: dict[tuple[str, str, str, str], dict] = {}

    def add_edge(a: str, b: str, label: str, class_name: str = "", metadata: dict | None = None) -> None:
        if a in nodes and b in nodes:
            edge_metadata = metadata or {}
            edges[(a, b, label, str(edge_metadata.get("candidateId", "")))] = {"a": a, "b": b, "label": label, "className": class_name, **edge_metadata}

    def add_source(source_id: str, pipe: str | None = None) -> str:
        node_id = f"source:{source_id}"
        if node_id not in nodes:
            _add_node(nodes, node_id, name=SOURCE_LABELS.get(source_id, source_id), kind="Source", node_type="source", pipe=pipe or SOURCE_PIPELINES.get(source_id, "01"), fields={"source_id": source_id})
        return node_id

    for capture in captures:
        source_id = capture["source_id"]
        node_id = add_source(source_id)
        nodes[node_id]["fields"] = capture

    for row in entities:
        record = row["record"]
        _add_node(nodes, f"entity:{row['key']}", name=record.get("canonical_name", row["key"]), kind=f"Entity · {record.get('entity_type', 'organization')}", node_type="entity", pipe="01", fields={"entity_id": row["key"], "run_id": row["run_id"], "source_id": record.get("source_id"), "review": "source-derived"})

    for row in works:
        record = row["record"]
        work_id = row["key"]
        work_node = f"research:{work_id}"
        _add_node(nodes, work_node, name=record.get("title", work_id), kind=f"Research work · {work_id.rsplit('/', 1)[-1]}", node_type="research", pipe="02", fields={"work_id": work_id, "run_id": row["run_id"], "publication_date": record.get("publication_date"), "source_record_id": record.get("source_record_id")})
        source_id = record.get("source_id", "openalex")
        source_node = add_source(source_id, "02")
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
        source_node = add_source(source_id, "02")
        add_edge(source_node, patent_node, "normalizes", "source")

    for row in awards:
        record = row["record"]
        award_id = record.get("award_id") or row["key"]
        award_node = f"award:{award_id}"
        display_id = record.get("award_display_id") or award_id
        description = record.get("description") or "No source description available"
        _add_node(nodes, award_node, name=f"{display_id} · {record.get('recipient_name') or 'Unknown recipient'}", kind="Public award · {record.get('award_group', 'contract')}", node_type="award", pipe="04", fields={"award_id": award_id, "award_display_id": display_id, "recipient_name": record.get("recipient_name"), "awarding_agency": record.get("awarding_agency"), "naics_code": record.get("naics_code"), "base_obligation_date": record.get("base_obligation_date"), "obligated_amount_usd": record.get("obligated_amount_usd"), "description": description, "source_url": record.get("source_url"), "source_record_id": record.get("source_record_id"), "review": "source-derived public award"})
        add_edge(add_source(record.get("source_id", "usaspending"), "04"), award_node, "award record", "source")

    for row in recipients:
        record = row["record"]
        recipient_key = record.get("recipient_key") or row["key"]
        recipient_node = f"recipient:{recipient_key}"
        _add_node(nodes, recipient_node, name=record.get("recipient_name") or recipient_key, kind="Award recipient", node_type="recipient", pipe="04", fields={"recipient_key": recipient_key, "award_count": record.get("award_count"), "total_obligated_usd": record.get("total_obligated_usd"), "first_base_obligation_date": record.get("first_base_obligation_date"), "new_entrant_in_window": record.get("new_entrant_in_window"), "review": "award recipient; not a canonical entity match"})
        for award_id in record.get("award_ids") or []:
            add_edge(recipient_node, f"award:{award_id}", "recipient")

    for row in match_candidates:
        record = row["record"]
        review_status = record.get("review_status")
        if review_status not in {"accepted", "unreviewed"}:
            continue
        entity_node = f"entity:{record.get('candidate_entity_id')}"
        recipient_node = record.get("source_record_id")
        if isinstance(recipient_node, str) and recipient_node.startswith("recipient:"):
            metadata = {
                "candidateId": record.get("candidate_id"),
                "matchScore": record.get("match_score"),
                "matchMethod": record.get("match_method"),
                "reviewStatus": review_status,
                "reviewer": record.get("reviewer"),
                "reviewNote": record.get("review_note"),
                "sector": record.get("sector"),
                "reviewHistory": record.get("review_history", []),
            }
            if review_status == "accepted":
                add_edge(entity_node, recipient_node, "analyst-reviewed match", "reviewed", metadata)
            else:
                add_edge(entity_node, recipient_node, "candidate match · review needed", "candidate", metadata)

    for row in documents:
        record = row["record"]
        document_id = record.get("document_id") or row["key"]
        document_node = f"document:{document_id}"
        _add_node(nodes, document_node, name=record.get("title") or document_id, kind="Source document · headline", node_type="document", pipe="05", fields={"document_id": document_id, "url": record.get("url"), "domain": record.get("domain"), "first_seen_at": record.get("first_seen_at"), "language": record.get("language"), "content_scope": record.get("content_scope"), "review": "discovery source; title only"})
        add_edge(add_source(record.get("source_id", "gdelt_doc"), "05"), document_node, "indexes", "source")

    for row in event_candidates:
        record = row["record"]
        candidate_id = record.get("event_candidate_id") or row["key"]
        candidate_node = f"event:{candidate_id}"
        _add_node(nodes, candidate_node, name=f"{record.get('event_type', 'Event')} candidate", kind="Event candidate · unverified", node_type="event", pipe="05", fields={"event_candidate_id": candidate_id, "event_type": record.get("event_type"), "status": record.get("status"), "confidence": record.get("confidence"), "report_time": record.get("report_time"), "evidence": record.get("evidence"), "review": "headline-derived candidate; analyst review required"})
        add_edge(f"document:{record.get('document_id')}", candidate_node, "candidate event", "candidate")

    for row in entity_event_edges:
        record = row["record"]
        candidate_node = f"event:{record.get('event_candidate_id')}"
        entity_id = record.get("entity_id")
        target_node = f"recipient:{entity_id}" if f"recipient:{entity_id}" in nodes else f"entity:{entity_id}"
        add_edge(target_node, candidate_node, "headline mention", "candidate")

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
    return {"mode": "postgres", "node_count": len(nodes), "edge_count": len(edges), "nodes": list(nodes.values()), "edges": list(edges.values()), "reviewQueue": review_queue}


def _layout(nodes: dict[str, dict]) -> None:
    columns = {"source": 95, "capture": 275, "entity": 500, "recipient": 500, "patent": 720, "research": 720, "person": 720, "award": 720, "document": 720, "institution": 1000, "topic": 1000, "event": 1000}
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "http://localhost:5173")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

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

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/knowledge/reviews":
            self._send(404, {"error": "Not found"})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 16_384:
                raise ValueError("Review request body is missing or too large")
            payload = json.loads(self.rfile.read(content_length))
            if not isinstance(payload, dict):
                raise ValueError("Review request must be a JSON object")
            candidate_id = str(payload.get("candidateId") or "")
            action = str(payload.get("action") or "")
            note = str(payload.get("note") or "")
            if not candidate_id:
                raise ValueError("Review candidate is required")
            self._send(200, {"status": "saved", "graph": submit_review_decision(self.settings, candidate_id, action, note)})
        except ReviewConflictError as exc:
            self._send(409, {"error": str(exc)})
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            self._send(503, {"error": "Unable to save the analyst review", "detail": str(exc)})

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Investment-diligence PostgreSQL graph and analyst review API")
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
