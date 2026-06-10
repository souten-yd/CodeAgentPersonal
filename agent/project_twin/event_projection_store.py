"""Durable delivery-trace projection storage (PIR-4)."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.project_intelligence.contracts import IntelligenceDiagnostic, IntelligenceErrorCode
from agent.project_twin.event_bridge import (
    DeliveryEdge,
    DeliveryIngestResult,
    DeliveryNode,
    DeliveryTrace,
    _facts_for_event,
)
from agent.project_twin.facade import PROJECT_EVENT_TYPES, ProjectEventEnvelope

SQLITE_MEMORY_PATH = ":" + "memory" + ":"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_db_path() -> Path:
    root = Path(tempfile.gettempdir()) / "kasane_project_intelligence"
    root.mkdir(parents=True, exist_ok=True)
    return root / "event-projection.sqlite3"


def _payload(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _diagnostic(code: IntelligenceErrorCode, message: str) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(code=code, message=message, severity="info")


class EventProjectionStore:
    """SQLite-backed durable inbox/outbox projection for delivery trace facts."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = str(db_path or _default_db_path())
        self._conn = sqlite3.connect(self._db_path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if self._db_path != SQLITE_MEMORY_PATH:
            try:
                self._conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.DatabaseError:
                pass
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_event_inbox (
                event_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                project_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                state TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, workspace_id, event_id)
            )
            """
        )
        self._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_project_event_inbox_idem
            ON project_event_inbox (project_id, workspace_id, idempotency_key)
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_nodes (
                project_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                ref TEXT NOT NULL,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                source_refs TEXT NOT NULL DEFAULT '[]',
                source_revision TEXT,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, workspace_id, ref)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_edges (
                project_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                target_ref TEXT NOT NULL,
                edge_kind TEXT NOT NULL,
                inferred INTEGER NOT NULL DEFAULT 0,
                source_refs TEXT NOT NULL DEFAULT '[]',
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (project_id, workspace_id, source_ref, target_ref, edge_kind)
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_diagnostics (
                row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                workspace_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                code TEXT NOT NULL,
                message TEXT NOT NULL,
                refs TEXT NOT NULL DEFAULT '[]',
                severity TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    def begin_event(self, env: ProjectEventEnvelope) -> bool:
        """Persist a full event payload. Returns False for duplicate replay."""
        key = env.idempotency_key or env.event_id
        existing = self._conn.execute(
            """
            SELECT 1 FROM project_event_inbox
            WHERE project_id = ? AND workspace_id = ? AND idempotency_key = ?
            """,
            (env.project_id, env.workspace_id, key),
        ).fetchone()
        if existing is not None:
            return False
        now = _now()
        payload = env.model_dump(mode="json")
        self._conn.execute(
            """
            INSERT INTO project_event_inbox
            (event_id, idempotency_key, project_id, workspace_id, event_type, payload_json,
             state, attempts, last_error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'running', 1, NULL, ?, ?)
            """,
            (env.event_id, key, env.project_id, env.workspace_id, env.event_type, _payload(payload), now, now),
        )
        return True

    def complete_event(self, env: ProjectEventEnvelope, *, diagnostics: list[IntelligenceDiagnostic]) -> None:
        now = _now()
        state = "done_with_diagnostics" if diagnostics else "done"
        error = "; ".join(d.message for d in diagnostics) if diagnostics else None
        self._conn.execute(
            """
            UPDATE project_event_inbox
            SET state = ?, last_error = ?, updated_at = ?
            WHERE project_id = ? AND workspace_id = ? AND event_id = ?
            """,
            (state, error, now, env.project_id, env.workspace_id, env.event_id),
        )
        self.add_diagnostics(env, diagnostics)

    def poison_event(self, env: ProjectEventEnvelope, diagnostics: list[IntelligenceDiagnostic]) -> None:
        now = _now()
        error = "; ".join(d.message for d in diagnostics)
        self._conn.execute(
            """
            UPDATE project_event_inbox
            SET state = 'poison', last_error = ?, updated_at = ?
            WHERE project_id = ? AND workspace_id = ? AND event_id = ?
            """,
            (error, now, env.project_id, env.workspace_id, env.event_id),
        )
        self.add_diagnostics(env, diagnostics)

    def fail_event(self, env: ProjectEventEnvelope, error: str) -> None:
        now = _now()
        self._conn.execute(
            """
            UPDATE project_event_inbox
            SET state = 'retryable', last_error = ?, updated_at = ?
            WHERE project_id = ? AND workspace_id = ? AND event_id = ?
            """,
            (error, now, env.project_id, env.workspace_id, env.event_id),
        )
        self.add_diagnostics(env, [_diagnostic(IntelligenceErrorCode.STORE_UNAVAILABLE, error)])

    def add_nodes(self, project_id: str, workspace_id: str, nodes: list[DeliveryNode]) -> int:
        added = 0
        now = _now()
        for node in nodes:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO delivery_nodes
                (project_id, workspace_id, ref, kind, label, source_refs, source_revision,
                 payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    project_id,
                    workspace_id,
                    node.ref,
                    node.kind,
                    node.label,
                    _payload(node.source_refs),
                    node.source_revision,
                    now,
                    now,
                ),
            )
            added += int(cur.rowcount or 0)
        return added

    def add_edges(self, project_id: str, workspace_id: str, edges: list[DeliveryEdge]) -> int:
        added = 0
        now = _now()
        for edge in edges:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO delivery_edges
                (project_id, workspace_id, source_ref, target_ref, edge_kind, inferred,
                 source_refs, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                """,
                (
                    project_id,
                    workspace_id,
                    edge.source_ref,
                    edge.target_ref,
                    edge.edge_type,
                    int(edge.inferred),
                    _payload(edge.source_refs),
                    now,
                    now,
                ),
            )
            added += int(cur.rowcount or 0)
        return added

    def add_diagnostics(self, env: ProjectEventEnvelope, diagnostics: list[IntelligenceDiagnostic]) -> None:
        now = _now()
        for diagnostic in diagnostics:
            self._conn.execute(
                """
                INSERT INTO delivery_diagnostics
                (project_id, workspace_id, event_id, code, message, refs, severity, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    env.project_id,
                    env.workspace_id,
                    env.event_id,
                    diagnostic.code.value,
                    diagnostic.message,
                    _payload(diagnostic.refs),
                    diagnostic.severity,
                    now,
                ),
            )

    def event_payload(self, project_id: str, workspace_id: str, event_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            """
            SELECT payload_json FROM project_event_inbox
            WHERE project_id = ? AND workspace_id = ? AND event_id = ?
            """,
            (project_id, workspace_id, event_id),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def event_state(self, project_id: str, workspace_id: str, event_id: str) -> str | None:
        row = self._conn.execute(
            """
            SELECT state FROM project_event_inbox
            WHERE project_id = ? AND workspace_id = ? AND event_id = ?
            """,
            (project_id, workspace_id, event_id),
        ).fetchone()
        return str(row["state"]) if row else None

    def workspace_ids(self, project_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT workspace_id FROM project_event_inbox WHERE project_id = ? ORDER BY workspace_id",
            (project_id,),
        ).fetchall()
        return [str(row["workspace_id"]) for row in rows]

    def nodes(self, project_id: str, workspace_id: str) -> dict[str, DeliveryNode]:
        rows = self._conn.execute(
            """
            SELECT * FROM delivery_nodes
            WHERE project_id = ? AND workspace_id = ?
            ORDER BY rowid
            """,
            (project_id, workspace_id),
        ).fetchall()
        return {
            row["ref"]: DeliveryNode(
                ref=row["ref"],
                kind=row["kind"],
                label=row["label"],
                source_refs=json.loads(row["source_refs"]),
                source_revision=row["source_revision"],
            )
            for row in rows
        }

    def edges(self, project_id: str, workspace_id: str) -> dict[tuple[str, str, str], DeliveryEdge]:
        rows = self._conn.execute(
            """
            SELECT * FROM delivery_edges
            WHERE project_id = ? AND workspace_id = ?
            ORDER BY rowid
            """,
            (project_id, workspace_id),
        ).fetchall()
        return {
            (row["source_ref"], row["target_ref"], row["edge_kind"]): DeliveryEdge(
                source_ref=row["source_ref"],
                target_ref=row["target_ref"],
                edge_type=row["edge_kind"],
                inferred=bool(row["inferred"]),
                source_refs=json.loads(row["source_refs"]),
            )
            for row in rows
        }

    def diagnostics(self, project_id: str, workspace_id: str) -> list[IntelligenceDiagnostic]:
        rows = self._conn.execute(
            """
            SELECT * FROM delivery_diagnostics
            WHERE project_id = ? AND workspace_id = ?
            ORDER BY row_id
            """,
            (project_id, workspace_id),
        ).fetchall()
        return [
            IntelligenceDiagnostic(
                code=IntelligenceErrorCode(row["code"]),
                message=row["message"],
                refs=json.loads(row["refs"]),
                severity=row["severity"],
            )
            for row in rows
        ]


class DurableDeliveryTraceProjector:
    """Idempotent delivery-trace projector backed by EventProjectionStore."""

    def __init__(self, store: EventProjectionStore) -> None:
        self._store = store

    def close(self) -> None:
        self._store.close()

    def ingest(self, env: ProjectEventEnvelope) -> DeliveryIngestResult:
        duplicate = not self._store.begin_event(env)
        if duplicate:
            return DeliveryIngestResult(
                project_id=env.project_id,
                workspace_id=env.workspace_id,
                event_id=env.event_id,
                accepted=True,
                duplicate=True,
            )
        if env.event_type not in PROJECT_EVENT_TYPES:
            diagnostics = [
                _diagnostic(IntelligenceErrorCode.INVALID_CONTRACT_VERSION, f"unknown event type {env.event_type!r}")
            ]
            self._store.poison_event(env, diagnostics)
            return DeliveryIngestResult(
                project_id=env.project_id,
                workspace_id=env.workspace_id,
                event_id=env.event_id,
                accepted=False,
                diagnostics=diagnostics,
            )
        try:
            nodes, edge_tuples, diagnostics = _facts_for_event(env)
            edges = [
                DeliveryEdge(
                    source_ref=src,
                    target_ref=tgt,
                    edge_type=edge_type,
                    inferred=inferred,
                    source_refs=[env.source_ref] if env.source_ref else [],
                )
                for src, tgt, edge_type, inferred in edge_tuples
            ]
            added_nodes = self._store.add_nodes(env.project_id, env.workspace_id, nodes)
            added_edges = self._store.add_edges(env.project_id, env.workspace_id, edges)
            self._store.complete_event(env, diagnostics=diagnostics)
        except Exception as exc:
            self._store.fail_event(env, str(exc))
            raise
        return DeliveryIngestResult(
            project_id=env.project_id,
            workspace_id=env.workspace_id,
            event_id=env.event_id,
            accepted=True,
            added_nodes=added_nodes,
            added_edges=added_edges,
            diagnostics=diagnostics,
        )

    def get_trace(
        self,
        project_id: str,
        root_ref: str,
        *,
        workspace_id: str | None = None,
        max_depth: int = 6,
    ) -> DeliveryTrace:
        if workspace_id is None:
            matches = self._store.workspace_ids(project_id)
            if len(matches) != 1:
                return DeliveryTrace(project_id=project_id, root_ref=root_ref)
            workspace_id = matches[0]
        nodes_by_ref = self._store.nodes(project_id, workspace_id)
        edges_by_key = self._store.edges(project_id, workspace_id)
        if not nodes_by_ref and not edges_by_key:
            return DeliveryTrace(project_id=project_id, workspace_id=workspace_id, root_ref=root_ref)

        edges_by_src: dict[str, list[DeliveryEdge]] = {}
        edges_by_tgt: dict[str, list[DeliveryEdge]] = {}
        for edge in edges_by_key.values():
            edges_by_src.setdefault(edge.source_ref, []).append(edge)
            edges_by_tgt.setdefault(edge.target_ref, []).append(edge)

        visited: set[str] = set()
        order: list[str] = []
        out_edges: list[DeliveryEdge] = []
        frontier = [(root_ref, 0)]
        while frontier:
            ref, depth = frontier.pop(0)
            if ref in visited or depth > max_depth:
                continue
            visited.add(ref)
            order.append(ref)
            for edge in edges_by_src.get(ref, []) + edges_by_tgt.get(ref, []):
                out_edges.append(edge)
                next_ref = edge.target_ref if edge.source_ref == ref else edge.source_ref
                frontier.append((next_ref, depth + 1))

        seen_edges: set[tuple[str, str, str]] = set()
        edges: list[DeliveryEdge] = []
        for edge in out_edges:
            key = (edge.source_ref, edge.target_ref, edge.edge_type)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append(edge)
        nodes = [nodes_by_ref[ref] for ref in order if ref in nodes_by_ref]
        return DeliveryTrace(
            project_id=project_id,
            workspace_id=workspace_id,
            root_ref=root_ref,
            nodes=nodes,
            edges=edges,
            diagnostics=self._store.diagnostics(project_id, workspace_id),
        )

    def diagnostics(self, project_id: str, workspace_id: str | None = None) -> list[IntelligenceDiagnostic]:
        if workspace_id is not None:
            return self._store.diagnostics(project_id, workspace_id)
        diagnostics: list[IntelligenceDiagnostic] = []
        for ws in self._store.workspace_ids(project_id):
            diagnostics.extend(self._store.diagnostics(project_id, ws))
        return diagnostics
