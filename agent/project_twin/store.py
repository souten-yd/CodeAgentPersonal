"""Local transactional Twin Store — SQLite implementation of ProjectTwinPort (PDT-2).

One transaction per delta with rollback on any failure (no partial revision visibility),
idempotent delta application keyed by (project_id, idempotency_key), stale-base-revision
rejection, project-scoped reads/writes, and revision/snapshot reconstruction.

This module is the only place that touches SQLite; consumers depend on the
`ProjectTwinPort` contract, never on this class directly.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent.project_twin.contracts import (
    ImpactRequest,
    ImpactResult,
    PathTraceRequest,
    PathTraceResult,
    RuntimeObservation,
    TwinDelta,
    TwinEdge,
    TwinEvidence,
    TwinHealth,
    TwinNode,
    TwinQuery,
    TwinQueryResult,
    TwinRevision,
    TwinSnapshot,
)
from agent.project_twin.migrations import apply_migrations
from agent.project_twin.types import CONTRACT_VERSION, HISTORICAL_STATUSES
from agent.project_twin.versioning import assert_supported_version


class TwinStoreError(Exception):
    """Typed store error carrying one of the contract error codes."""

    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {message}" if message else code)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SQLITE_MEMORY_PATH = ":" + "memory" + ":"


def _default_db_path() -> Path:
    root = Path(tempfile.gettempdir()) / "kasane_project_intelligence"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"project-twin-{uuid.uuid4().hex}.sqlite3"


class SqliteProjectTwinStore:
    """SQLite-backed `ProjectTwinPort`."""

    def __init__(self, db_path: str | Path | None = None, *, now_fn: Callable[[], str] | None = None) -> None:
        self._db_path = str(db_path or _default_db_path())
        self._now = now_fn or _utcnow_iso
        # isolation_level=None -> autocommit; we control transactions explicitly with
        # BEGIN/COMMIT so one delta is exactly one transaction. check_same_thread=False
        # lets the store back a FastAPI router whose sync handlers run in a threadpool;
        # access stays logically single-threaded (one transaction per delta).
        self._conn = sqlite3.connect(self._db_path, isolation_level=None, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if self._db_path != SQLITE_MEMORY_PATH:
            try:
                self._conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.DatabaseError:
                pass
        apply_migrations(self._conn, now_iso=self._now())

    def close(self) -> None:
        self._conn.close()

    # -- internal helpers -----------------------------------------------------

    def _project_head(self, project_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT head_revision_id FROM twin_projects WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return row["head_revision_id"] if row else None

    def _project_exists(self, project_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM twin_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return row is not None

    def _ensure_project(self, project_id: str, contract_version: str) -> None:
        if not self._project_exists(project_id):
            now = self._now()
            self._conn.execute(
                "INSERT INTO twin_projects (project_id, contract_version, head_revision_id, created_at, updated_at) "
                "VALUES (?, ?, NULL, ?, ?)",
                (project_id, contract_version, now, now),
            )

    @staticmethod
    def _node_from_row(row: sqlite3.Row) -> TwinNode:
        return TwinNode(
            contract_version=CONTRACT_VERSION,
            node_id=row["node_id"],
            project_id=row["project_id"],
            domain=row["domain"],
            node_type=row["node_type"],
            canonical_ref=row["canonical_ref"],
            label=row["label"],
            properties=json.loads(row["properties"]),
            source_kind=row["source_kind"],
            source_ref=row["source_ref"],
            source_revision=row["source_revision"],
            content_revision=row["content_revision"],
            derivation=row["derivation"],
            confidence=row["confidence"],
            status=row["status"],
            evidence_refs=json.loads(row["evidence_refs"]),
            observed_at=row["observed_at"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _edge_from_row(row: sqlite3.Row) -> TwinEdge:
        return TwinEdge(
            contract_version=CONTRACT_VERSION,
            edge_id=row["edge_id"],
            project_id=row["project_id"],
            domain=row["domain"],
            source_node_id=row["source_node_id"],
            target_node_id=row["target_node_id"],
            edge_type=row["edge_type"],
            properties=json.loads(row["properties"]),
            source_kind=row["source_kind"],
            source_ref=row["source_ref"],
            source_revision=row["source_revision"],
            derivation=row["derivation"],
            confidence=row["confidence"],
            status=row["status"],
            evidence_refs=json.loads(row["evidence_refs"]),
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _revision_from_row(row: sqlite3.Row) -> TwinRevision:
        return TwinRevision(
            revision_id=row["revision_id"],
            project_id=row["project_id"],
            parent_revision_id=row["parent_revision_id"],
            source_commit=row["source_commit"],
            working_tree_hash=row["working_tree_hash"],
            trigger_type=row["trigger_type"],
            trigger_ref=row["trigger_ref"],
            parser_versions=json.loads(row["parser_versions"]),
            node_upserts=row["node_upserts"],
            edge_upserts=row["edge_upserts"],
            invalidations=row["invalidations"],
            observations_added=row["observations_added"],
            created_at=row["created_at"],
        )

    def _revision(self, revision_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM twin_revisions WHERE revision_id = ?", (revision_id,)
        ).fetchone()

    # -- ProjectTwinPort ------------------------------------------------------

    def apply_delta(self, delta: TwinDelta) -> TwinRevision:
        assert_supported_version(delta.contract_version)

        # Project isolation: every payload must belong to the delta's project.
        for item in (*delta.nodes, *delta.edges, *delta.evidence, *delta.observations):
            if item.project_id != delta.project_id:
                raise TwinStoreError(
                    "project_scope_violation",
                    f"payload project_id {item.project_id!r} != delta project_id {delta.project_id!r}",
                )

        self._ensure_project(delta.project_id, delta.contract_version)

        # Idempotency: a repeated key returns the original revision unchanged.
        existing = self._conn.execute(
            "SELECT revision_id FROM twin_delta_log WHERE project_id = ? AND idempotency_key = ?",
            (delta.project_id, delta.idempotency_key),
        ).fetchone()
        if existing is not None:
            return self._revision_from_row(self._revision(existing["revision_id"]))

        head = self._project_head(delta.project_id)
        if delta.base_revision_id is not None and delta.base_revision_id != head:
            raise TwinStoreError(
                "stale_base_revision",
                f"base {delta.base_revision_id!r} is not current head {head!r}",
            )

        now = self._now()
        revision_id = uuid.uuid4().hex
        try:
            self._conn.execute("BEGIN")
            node_upserts = self._apply_nodes(delta, revision_id, now)
            edge_upserts = self._apply_edges(delta, revision_id, now)
            invalidations = self._apply_invalidations(delta, now)
            self._apply_evidence(delta, revision_id, now)
            observations_added = self._apply_observations(delta, revision_id, now)

            self._conn.execute(
                "INSERT INTO twin_revisions (revision_id, project_id, parent_revision_id, source_commit, "
                "working_tree_hash, trigger_type, trigger_ref, parser_versions, node_upserts, edge_upserts, "
                "invalidations, observations_added, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    revision_id,
                    delta.project_id,
                    head,
                    delta.source_commit,
                    delta.working_tree_hash,
                    delta.trigger_type,
                    delta.trigger_ref,
                    json.dumps(delta.parser_versions, ensure_ascii=False, sort_keys=True),
                    node_upserts,
                    edge_upserts,
                    invalidations,
                    observations_added,
                    now,
                ),
            )
            self._conn.execute(
                "UPDATE twin_projects SET head_revision_id = ?, updated_at = ? WHERE project_id = ?",
                (revision_id, now, delta.project_id),
            )
            self._conn.execute(
                "INSERT INTO twin_delta_log (project_id, idempotency_key, revision_id, created_at) VALUES (?,?,?,?)",
                (delta.project_id, delta.idempotency_key, revision_id, now),
            )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

        return self._revision_from_row(self._revision(revision_id))

    def _apply_nodes(self, delta: TwinDelta, revision_id: str, now: str) -> int:
        count = 0
        for node in delta.nodes:
            # Close any current fact sharing the canonical ref (keep history).
            self._conn.execute(
                "UPDATE twin_nodes SET valid_to = ?, status = 'superseded', updated_at = ? "
                "WHERE project_id = ? AND canonical_ref = ? AND valid_to IS NULL",
                (now, now, node.project_id, node.canonical_ref),
            )
            self._conn.execute(
                "INSERT INTO twin_nodes (node_id, project_id, domain, node_type, canonical_ref, label, properties, "
                "source_kind, source_ref, source_revision, content_revision, derivation, confidence, status, "
                "evidence_refs, observed_at, valid_from, valid_to, created_at, updated_at, revision_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    node.node_id,
                    node.project_id,
                    node.domain,
                    node.node_type,
                    node.canonical_ref,
                    node.label,
                    json.dumps(node.properties, ensure_ascii=False),
                    node.source_kind,
                    node.source_ref,
                    node.source_revision,
                    node.content_revision,
                    node.derivation,
                    node.confidence,
                    node.status,
                    json.dumps(node.evidence_refs, ensure_ascii=False),
                    node.observed_at.isoformat() if node.observed_at else None,
                    node.valid_from.isoformat(),
                    None,
                    now,
                    now,
                    revision_id,
                ),
            )
            count += 1
        return count

    def _apply_edges(self, delta: TwinDelta, revision_id: str, now: str) -> int:
        count = 0
        for edge in delta.edges:
            self._conn.execute(
                "UPDATE twin_edges SET valid_to = ?, status = 'superseded', updated_at = ? "
                "WHERE project_id = ? AND edge_type = ? AND source_node_id = ? AND target_node_id = ? "
                "AND valid_to IS NULL",
                (now, now, edge.project_id, edge.edge_type, edge.source_node_id, edge.target_node_id),
            )
            self._conn.execute(
                "INSERT INTO twin_edges (edge_id, project_id, domain, source_node_id, target_node_id, edge_type, "
                "properties, source_kind, source_ref, source_revision, derivation, confidence, status, evidence_refs, "
                "valid_from, valid_to, created_at, updated_at, revision_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    edge.edge_id,
                    edge.project_id,
                    edge.domain,
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.edge_type,
                    json.dumps(edge.properties, ensure_ascii=False),
                    edge.source_kind,
                    edge.source_ref,
                    edge.source_revision,
                    edge.derivation,
                    edge.confidence,
                    edge.status,
                    json.dumps(edge.evidence_refs, ensure_ascii=False),
                    edge.valid_from.isoformat(),
                    None,
                    now,
                    now,
                    revision_id,
                ),
            )
            count += 1
        return count

    def _apply_invalidations(self, delta: TwinDelta, now: str) -> int:
        count = 0
        for node_id in delta.invalidate_node_ids:
            cur = self._conn.execute(
                "UPDATE twin_nodes SET valid_to = ?, status = 'invalidated', updated_at = ? "
                "WHERE project_id = ? AND node_id = ? AND valid_to IS NULL",
                (now, now, delta.project_id, node_id),
            )
            count += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        for edge_id in delta.invalidate_edge_ids:
            cur = self._conn.execute(
                "UPDATE twin_edges SET valid_to = ?, status = 'invalidated', updated_at = ? "
                "WHERE project_id = ? AND edge_id = ? AND valid_to IS NULL",
                (now, now, delta.project_id, edge_id),
            )
            count += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        return count

    def _apply_evidence(self, delta: TwinDelta, revision_id: str, now: str) -> None:
        for ev in delta.evidence:
            self._conn.execute(
                "INSERT INTO twin_evidence (evidence_id, project_id, evidence_type, source_kind, source_ref, "
                "source_revision, summary, payload_ref, content_hash, confidence, observed_at, created_at, revision_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ev.evidence_id,
                    ev.project_id,
                    ev.evidence_type,
                    ev.source_kind,
                    ev.source_ref,
                    ev.source_revision,
                    ev.summary,
                    ev.payload_ref,
                    ev.content_hash,
                    ev.confidence,
                    ev.observed_at.isoformat() if ev.observed_at else None,
                    ev.created_at.isoformat(),
                    revision_id,
                ),
            )

    def _apply_observations(self, delta: TwinDelta, revision_id: str, now: str) -> int:
        count = 0
        for obs in delta.observations:
            self._conn.execute(
                "INSERT INTO twin_observations (observation_id, project_id, run_id, collector, collector_version, "
                "observation_type, subject_refs, source_revision, timestamp, result, summary, payload_ref, evidence_ids, revision_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    obs.observation_id,
                    obs.project_id,
                    obs.run_id,
                    obs.collector,
                    obs.collector_version,
                    obs.observation_type,
                    json.dumps(obs.subject_refs, ensure_ascii=False),
                    obs.source_revision,
                    obs.timestamp.isoformat(),
                    obs.result,
                    obs.summary,
                    obs.payload_ref,
                    json.dumps(obs.evidence_ids, ensure_ascii=False),
                    revision_id,
                ),
            )
            count += 1
        return count

    @staticmethod
    def _observation_from_row(row: sqlite3.Row) -> RuntimeObservation:
        return RuntimeObservation(
            observation_id=row["observation_id"],
            project_id=row["project_id"],
            run_id=row["run_id"],
            collector=row["collector"],
            collector_version=row["collector_version"],
            observation_type=row["observation_type"],
            subject_refs=json.loads(row["subject_refs"]),
            source_revision=row["source_revision"],
            timestamp=row["timestamp"],
            result=row["result"],
            summary=row["summary"],
            payload_ref=row["payload_ref"],
            evidence_ids=json.loads(row["evidence_ids"]),
        )

    def list_observations(
        self,
        project_id: str,
        *,
        subject_ref: str | None = None,
        limit: int = 100,
    ) -> list[RuntimeObservation]:
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if subject_ref:
            clauses.append("subject_refs LIKE ?")
            params.append(f"%{subject_ref}%")
        where = " AND ".join(clauses)
        rows = self._conn.execute(
            f"SELECT * FROM twin_observations WHERE {where} ORDER BY row_id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        observations = [self._observation_from_row(row) for row in rows]
        if subject_ref:
            observations = [obs for obs in observations if subject_ref in obs.subject_refs]
        return observations

    def get_health(self, project_id: str) -> TwinHealth:
        now = self._now()
        if not self._project_exists(project_id):
            return TwinHealth(
                project_id=project_id,
                twin_revision_id=None,
                status="not_found",
                diagnostics=[{"code": "project_not_found", "detail": project_id}],
                generated_at=now,
            )
        head = self._project_head(project_id)
        node_count = self._conn.execute(
            "SELECT COUNT(*) AS c FROM twin_nodes WHERE project_id = ? AND valid_to IS NULL",
            (project_id,),
        ).fetchone()["c"]
        edge_count = self._conn.execute(
            "SELECT COUNT(*) AS c FROM twin_edges WHERE project_id = ? AND valid_to IS NULL",
            (project_id,),
        ).fetchone()["c"]
        return TwinHealth(
            project_id=project_id,
            twin_revision_id=head,
            status="ok" if head else "empty",
            node_count=node_count,
            edge_count=edge_count,
            stale=False,
            generated_at=now,
        )

    def get_snapshot(self, project_id: str, revision_id: str | None = None) -> TwinSnapshot:
        now = self._now()
        if not self._project_exists(project_id):
            raise TwinStoreError("project_not_found", project_id)

        if revision_id is None:
            node_rows = self._conn.execute(
                "SELECT * FROM twin_nodes WHERE project_id = ? AND valid_to IS NULL ORDER BY row_id",
                (project_id,),
            ).fetchall()
            edge_rows = self._conn.execute(
                "SELECT * FROM twin_edges WHERE project_id = ? AND valid_to IS NULL ORDER BY row_id",
                (project_id,),
            ).fetchall()
            head = self._project_head(project_id)
            return TwinSnapshot(
                project_id=project_id,
                twin_revision_id=head,
                nodes=[self._node_from_row(r) for r in node_rows],
                edges=[self._edge_from_row(r) for r in edge_rows],
                generated_at=now,
            )

        rev = self._revision(revision_id)
        if rev is None or rev["project_id"] != project_id:
            raise TwinStoreError("revision_not_found", revision_id)
        at = rev["created_at"]
        # Point-in-time: facts created at/before the target revision and not yet closed then.
        node_rows = self._conn.execute(
            "SELECT * FROM twin_nodes WHERE project_id = ? AND created_at <= ? "
            "AND (valid_to IS NULL OR valid_to > ?) ORDER BY row_id",
            (project_id, at, at),
        ).fetchall()
        edge_rows = self._conn.execute(
            "SELECT * FROM twin_edges WHERE project_id = ? AND created_at <= ? "
            "AND (valid_to IS NULL OR valid_to > ?) ORDER BY row_id",
            (project_id, at, at),
        ).fetchall()
        return TwinSnapshot(
            project_id=project_id,
            twin_revision_id=revision_id,
            nodes=[self._node_from_row(r) for r in node_rows],
            edges=[self._edge_from_row(r) for r in edge_rows],
            generated_at=now,
        )

    def query(self, query: TwinQuery) -> TwinQueryResult:
        now = self._now()
        head = self._project_head(query.project_id) if self._project_exists(query.project_id) else None

        include_historical = any(s in HISTORICAL_STATUSES for s in query.statuses)
        clauses = ["project_id = ?"]
        params: list[Any] = [query.project_id]
        if not include_historical:
            clauses.append("valid_to IS NULL")
        if query.node_types:
            clauses.append("node_type IN (%s)" % ",".join("?" * len(query.node_types)))
            params.extend(query.node_types)
        if query.canonical_refs:
            clauses.append("canonical_ref IN (%s)" % ",".join("?" * len(query.canonical_refs)))
            params.extend(query.canonical_refs)
        if query.statuses:
            clauses.append("status IN (%s)" % ",".join("?" * len(query.statuses)))
            params.extend(query.statuses)
        if query.text:
            clauses.append("(label LIKE ? OR canonical_ref LIKE ?)")
            params.extend([f"%{query.text}%", f"%{query.text}%"])
        clauses.append("confidence >= ?")
        params.append(query.min_confidence)

        offset = 0
        if query.cursor:
            try:
                offset = max(0, int(query.cursor))
            except ValueError:
                offset = 0

        where = " AND ".join(clauses)
        node_rows = self._conn.execute(
            f"SELECT * FROM twin_nodes WHERE {where} ORDER BY row_id LIMIT ? OFFSET ?",
            (*params, query.limit + 1, offset),
        ).fetchall()
        truncated = len(node_rows) > query.limit
        node_rows = node_rows[: query.limit]

        # Edges among the returned nodes (optionally filtered by edge_types).
        edge_rows: list[sqlite3.Row] = []
        if query.edge_types or query.max_depth >= 1:
            e_clauses = ["project_id = ?"]
            e_params: list[Any] = [query.project_id]
            if not include_historical:
                e_clauses.append("valid_to IS NULL")
            if query.edge_types:
                e_clauses.append("edge_type IN (%s)" % ",".join("?" * len(query.edge_types)))
                e_params.extend(query.edge_types)
            e_where = " AND ".join(e_clauses)
            edge_rows = self._conn.execute(
                f"SELECT * FROM twin_edges WHERE {e_where} ORDER BY row_id LIMIT ?",
                (*e_params, query.limit),
            ).fetchall()

        next_cursor = str(offset + query.limit) if truncated else None
        return TwinQueryResult(
            project_id=query.project_id,
            twin_revision_id=head,
            nodes=[self._node_from_row(r) for r in node_rows],
            edges=[self._edge_from_row(r) for r in edge_rows],
            cursor=next_cursor,
            truncated=truncated,
            generated_at=now,
        )

    def trace_path(self, request: PathTraceRequest) -> PathTraceResult:
        from agent.project_twin.analysis import GraphAnalysisService

        return GraphAnalysisService(self).trace_path(request)

    def assess_impact(self, request: ImpactRequest) -> ImpactResult:
        from agent.project_twin.analysis import GraphAnalysisService

        return GraphAnalysisService(self).assess_impact(request)
