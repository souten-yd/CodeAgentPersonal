"""Concrete Digital Twin facade foundation (PIR-1).

This module adapts the existing durable Project Twin store behind the public
``DigitalTwinModule`` facade. It is intentionally minimal: source snapshotting and
deep analyzers land in later PIR packages, but this facade now owns durable
revision, query, context, runtime-ingest, and workspace-isolation behavior.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from agent.project_intelligence.contracts import (
    ContextItem,
    ContextManifest,
    IntelligenceDiagnostic,
    IntelligenceErrorCode,
    ProjectIdentity,
    RuntimeObservationRecord,
)
from agent.project_twin.contracts import (
    StaticAnalysisRequest,
    RuntimeObservation,
    TwinDelta,
    TwinNode,
    TwinQuery as StoreTwinQuery,
)
from agent.project_twin.facade import (
    DigitalTwinModule,
    OpenTwinRequest,
    ProjectEventEnvelope,
    RebuildTwinRequest,
    RefreshTwinRequest,
    RuntimeIngestRequest,
    RuntimeIngestResult,
    TwinContextPackage,
    TwinContextRequest,
    TwinEventResult,
    TwinHealthReport,
    TwinHealthRequest,
    TwinProjectState,
    TwinQueryRequest,
    TwinQueryResult,
    TwinQueryResultItem,
    TwinReadiness,
    TwinRefreshResult,
)
from agent.project_twin.behavioral_graph import BehavioralAnalyzer
from agent.project_twin.store import SQLITE_MEMORY_PATH, SqliteProjectTwinStore, TwinStoreError
from agent.project_twin.lifecycle import LastBuildRecord, build_project_state
from agent.project_twin.source_adapter import ProjectSourceAdapter, SourceSnapshot, SourceSnapshotError
from agent.project_twin.static_graph import StaticStructuralAnalyzer


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _diag(code: IntelligenceErrorCode, message: str) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(code=code, message=message, severity="info")


def _last_build_from_dict(payload: dict) -> LastBuildRecord:
    return LastBuildRecord(
        twin_revision_id=str(payload["twin_revision_id"]),
        source_revision=payload.get("source_revision"),
        working_tree_hash=str(payload.get("working_tree_hash") or ""),
        parser_versions=dict(payload.get("parser_versions") or {}),
    )


class DigitalTwinModuleImpl(DigitalTwinModule):
    """Durable concrete Digital Twin facade.

    The legacy store is project-keyed, so the concrete facade scopes each workspace
    under a private internal project key. Public DTOs still return the original
    project/workspace IDs.
    """

    rollout_mode = "concrete"

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        store: SqliteProjectTwinStore | None = None,
        source_adapter: ProjectSourceAdapter | None = None,
        last_build_path: str | Path | None = None,
        static_analyzer: StaticStructuralAnalyzer | None = None,
        behavioral_analyzer: BehavioralAnalyzer | None = None,
    ) -> None:
        self._store = store or SqliteProjectTwinStore(db_path)
        self._source_adapter = source_adapter or ProjectSourceAdapter()
        self._static_analyzer = static_analyzer or StaticStructuralAnalyzer()
        self._behavioral_analyzer = behavioral_analyzer or BehavioralAnalyzer()
        if last_build_path is not None:
            self._last_build_path = Path(last_build_path)
        elif db_path is not None and str(db_path) != SQLITE_MEMORY_PATH:
            self._last_build_path = Path(str(db_path) + ".last_build.json")
        else:
            self._last_build_path = None

    def close(self) -> None:
        self._store.close()

    @staticmethod
    def _key(project_id: str, workspace_id: str) -> str:
        return f"{project_id}\x1f{workspace_id}"

    def _health(self, project_id: str, workspace_id: str):
        return self._store.get_health(self._key(project_id, workspace_id))

    def _last_builds(self) -> dict[str, dict]:
        if self._last_build_path is None or not self._last_build_path.exists():
            return {}
        try:
            payload = json.loads(self._last_build_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _last_build(self, project_id: str, workspace_id: str) -> LastBuildRecord | None:
        payload = self._last_builds().get(self._key(project_id, workspace_id))
        if not isinstance(payload, dict):
            return None
        try:
            return _last_build_from_dict(payload)
        except (KeyError, TypeError, ValueError):
            return None

    def _write_last_build(
        self,
        project_id: str,
        workspace_id: str,
        *,
        revision_id: str,
        source_revision: str | None,
        working_tree_hash: str,
        parser_versions: dict[str, str],
    ) -> None:
        if self._last_build_path is None:
            return
        payload = self._last_builds()
        payload[self._key(project_id, workspace_id)] = {
            "twin_revision_id": revision_id,
            "source_revision": source_revision,
            "working_tree_hash": working_tree_hash,
            "parser_versions": dict(sorted(parser_versions.items())),
            "updated_at": _now().isoformat(),
        }
        self._last_build_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._last_build_path.with_suffix(self._last_build_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self._last_build_path)

    @staticmethod
    def _source_identity(request_project: ProjectIdentity, snapshot: SourceSnapshot) -> ProjectIdentity:
        return request_project.model_copy(
            update={
                "repository_identity": snapshot.project.repository_identity,
                "branch_or_worktree": snapshot.project.branch_or_worktree,
                "source_revision": snapshot.project.source_revision,
                "working_tree_hash": snapshot.project.working_tree_hash,
            }
        )

    def _marker_node(self, project_id: str, workspace_id: str, *, kind: str, ref: str | None = None) -> TwinNode:
        internal = self._key(project_id, workspace_id)
        now = _now()
        return TwinNode(
            node_id=f"node:{uuid.uuid4().hex}",
            project_id=internal,
            domain="structural",
            node_type=kind,
            canonical_ref=ref or f"project://{project_id}/{workspace_id}",
            label=ref or project_id,
            properties={"public_project_id": project_id, "workspace_id": workspace_id},
            source_kind="project_intelligence",
            source_ref=ref or project_id,
            derivation="deterministic_static",
            confidence=0.6,
            status="declared",
            valid_from=now,
            created_at=now,
            updated_at=now,
        )

    def _apply_marker(
        self,
        project_id: str,
        workspace_id: str,
        *,
        trigger_type: str,
        trigger_ref: str | None = None,
        base_revision_id: str | None = None,
        changed_paths: list[str] | None = None,
    ):
        nodes = [self._marker_node(project_id, workspace_id, kind="project", ref=f"project://{project_id}")]
        for path in changed_paths or []:
            nodes.append(self._marker_node(project_id, workspace_id, kind="file", ref=f"file://{path}"))
        return self._store.apply_delta(
            TwinDelta(
                project_id=self._key(project_id, workspace_id),
                base_revision_id=base_revision_id,
                idempotency_key=f"{trigger_type}:{trigger_ref or ''}:{uuid.uuid4().hex}",
                trigger_type=trigger_type,
                trigger_ref=trigger_ref,
                nodes=nodes,
            )
        )

    def _source_snapshot(self, project: ProjectIdentity, changed_paths: list[str] | None = None) -> SourceSnapshot:
        return self._source_adapter.snapshot(
            project.project_path,
            workspace_id=project.workspace_id,
            requested_changed_paths=changed_paths,
        )

    def _source_delta(
        self,
        *,
        project: ProjectIdentity,
        snapshot: SourceSnapshot,
        base_revision_id: str | None,
        trigger_type: str,
        trigger_ref: str | None,
        full_rebuild: bool,
        changed_paths: list[str],
    ) -> TwinDelta:
        internal = self._key(project.project_id, project.workspace_id)
        request = StaticAnalysisRequest(
            project_id=internal,
            project_path=str(snapshot.root),
            changed_paths=changed_paths,
            full_rebuild=full_rebuild,
            base_revision_id=base_revision_id,
        )
        static = self._static_analyzer.analyze(request)
        behavioral = self._behavioral_analyzer.analyze(request)
        parser_versions = dict(snapshot.parser_manifest)
        parser_versions.update(static.parser_versions)
        parser_versions.update(behavioral.parser_versions)
        delta = TwinDelta(
            project_id=internal,
            base_revision_id=base_revision_id,
            idempotency_key=f"{trigger_type}:{trigger_ref or ''}:{snapshot.project.source_revision or ''}:"
            f"{snapshot.project.working_tree_hash}:{','.join(sorted(changed_paths)) or 'full'}:{uuid.uuid4().hex}",
            trigger_type=trigger_type,
            trigger_ref=trigger_ref,
            source_commit=snapshot.project.source_revision,
            working_tree_hash=snapshot.project.working_tree_hash,
            parser_versions=parser_versions,
            nodes=[*static.delta.nodes, *behavioral.delta.nodes],
            edges=[*static.delta.edges, *behavioral.delta.edges],
            diagnostics=[*static.diagnostics, *behavioral.diagnostics],
        )
        scope = None if full_rebuild or not changed_paths else set(changed_paths)
        if base_revision_id is not None:
            current = self._store.get_snapshot(internal)
            new_node_refs = {node.canonical_ref for node in delta.nodes}
            new_edge_ids = {edge.edge_id for edge in delta.edges}
            for node in current.nodes:
                if scope is not None and node.source_ref not in scope:
                    continue
                if node.canonical_ref not in new_node_refs:
                    delta.invalidate_node_ids.append(node.node_id)
            for edge in current.edges:
                if scope is not None and edge.source_ref not in scope:
                    continue
                if edge.edge_id not in new_edge_ids:
                    delta.invalidate_edge_ids.append(edge.edge_id)
        return delta

    def _apply_source_refresh(
        self,
        *,
        project: ProjectIdentity,
        snapshot: SourceSnapshot,
        trigger_type: str,
        trigger_ref: str | None,
        expected_revision_id: str | None,
        full_rebuild: bool,
        changed_paths: list[str],
    ):
        before = self._health(project.project_id, project.workspace_id)
        base = expected_revision_id if expected_revision_id is not None else before.twin_revision_id
        delta = self._source_delta(
            project=project,
            snapshot=snapshot,
            base_revision_id=base,
            trigger_type=trigger_type,
            trigger_ref=trigger_ref,
            full_rebuild=full_rebuild,
            changed_paths=changed_paths,
        )
        rev = self._store.apply_delta(delta)
        self._write_last_build(
            project.project_id,
            project.workspace_id,
            revision_id=rev.revision_id,
            source_revision=snapshot.project.source_revision,
            working_tree_hash=snapshot.project.working_tree_hash,
            parser_versions=delta.parser_versions,
        )
        return before, rev, delta, snapshot.diagnostics

    def open_project(self, request: OpenTwinRequest) -> TwinProjectState:
        try:
            snapshot = self._source_snapshot(request.project)
        except SourceSnapshotError:
            snapshot = None
        if snapshot is not None:
            project = self._source_identity(request.project, snapshot)
            last = self._last_build(project.project_id, project.workspace_id)
            state = build_project_state(
                project,
                last,
                current_parser_versions=snapshot.parser_manifest,
                available_capabilities=["source_snapshot", "durable_revision", "query", "context", "runtime_ingest"],
            )
            if state.readiness != TwinReadiness.READY:
                before, rev, delta, diagnostics = self._apply_source_refresh(
                    project=project,
                    snapshot=snapshot,
                    trigger_type="project.opened",
                    trigger_ref=request.correlation_id or project.project_path,
                    expected_revision_id=None,
                    full_rebuild=True,
                    changed_paths=[],
                )
                return TwinProjectState(
                    project=project,
                    readiness=TwinReadiness.READY,
                    twin_revision_id=rev.revision_id,
                    parser_versions=delta.parser_versions,
                    available_capabilities=["source_snapshot", "durable_revision", "query", "context", "runtime_ingest"],
                    diagnostics=diagnostics,
                )
            return state

        health = self._health(request.project.project_id, request.project.workspace_id)
        if health.twin_revision_id is None:
            rev = self._apply_marker(
                request.project.project_id,
                request.project.workspace_id,
                trigger_type="project.opened",
                trigger_ref=request.correlation_id or request.project.project_path,
            )
            revision_id = rev.revision_id
        else:
            revision_id = health.twin_revision_id
        return TwinProjectState(
            project=request.project,
            readiness=TwinReadiness.READY,
            twin_revision_id=revision_id,
            available_capabilities=["durable_revision", "query", "context", "runtime_ingest"],
        )

    def refresh(self, request: RefreshTwinRequest) -> TwinRefreshResult:
        before = self._health(request.project.project_id, request.project.workspace_id)
        try:
            snapshot = self._source_snapshot(request.project, request.changed_paths or None)
        except SourceSnapshotError:
            snapshot = None
        if snapshot is not None:
            project = self._source_identity(request.project, snapshot)
            changed_paths = list(dict.fromkeys([*request.changed_paths, *snapshot.changed_paths]))
            full_rebuild = request.full_rebuild or before.twin_revision_id is None
            try:
                before, rev, delta, diagnostics = self._apply_source_refresh(
                    project=project,
                    snapshot=snapshot,
                    trigger_type=request.trigger_type,
                    trigger_ref=request.trigger_ref,
                    expected_revision_id=request.expected_revision_id,
                    full_rebuild=full_rebuild,
                    changed_paths=[] if full_rebuild else changed_paths,
                )
                affected = [f"file://{path}" for path in changed_paths]
                return TwinRefreshResult(
                    project_id=project.project_id,
                    workspace_id=project.workspace_id,
                    previous_revision_id=before.twin_revision_id,
                    twin_revision_id=rev.revision_id,
                    readiness=TwinReadiness.READY,
                    changed_node_count=rev.node_upserts,
                    changed_edge_count=rev.edge_upserts,
                    invalidation_count=rev.invalidations,
                    affected_refs=affected,
                    diagnostics=diagnostics,
                )
            except TwinStoreError as exc:
                return TwinRefreshResult(
                    project_id=project.project_id,
                    workspace_id=project.workspace_id,
                    previous_revision_id=before.twin_revision_id,
                    twin_revision_id=before.twin_revision_id,
                    readiness=TwinReadiness.DEGRADED,
                    diagnostics=[_diag(IntelligenceErrorCode.STALE_TWIN_REVISION, str(exc))],
                )

        try:
            rev = self._apply_marker(
                request.project.project_id,
                request.project.workspace_id,
                trigger_type=request.trigger_type,
                trigger_ref=request.trigger_ref,
                base_revision_id=request.expected_revision_id,
                changed_paths=request.changed_paths,
            )
            return TwinRefreshResult(
                project_id=request.project.project_id,
                workspace_id=request.project.workspace_id,
                previous_revision_id=before.twin_revision_id,
                twin_revision_id=rev.revision_id,
                readiness=TwinReadiness.READY,
                changed_node_count=rev.node_upserts,
                changed_edge_count=rev.edge_upserts,
                invalidation_count=rev.invalidations,
                affected_refs=[f"file://{p}" for p in request.changed_paths],
            )
        except TwinStoreError as exc:
            return TwinRefreshResult(
                project_id=request.project.project_id,
                workspace_id=request.project.workspace_id,
                previous_revision_id=before.twin_revision_id,
                twin_revision_id=before.twin_revision_id,
                readiness=TwinReadiness.DEGRADED,
                diagnostics=[_diag(IntelligenceErrorCode.STALE_TWIN_REVISION, str(exc))],
            )

    def rebuild(self, request: RebuildTwinRequest) -> TwinRefreshResult:
        return self.refresh(
            RefreshTwinRequest(
                project=request.project,
                trigger_type="rebuild",
                trigger_ref=request.reason,
                correlation_id=request.correlation_id,
                full_rebuild=True,
            )
        )

    def ingest_event(self, event: ProjectEventEnvelope) -> TwinEventResult:
        try:
            rev = self._apply_marker(
                event.project_id,
                event.workspace_id,
                trigger_type=event.event_type,
                trigger_ref=event.event_id,
            )
            return TwinEventResult(
                project_id=event.project_id,
                workspace_id=event.workspace_id,
                event_id=event.event_id,
                accepted=True,
                twin_revision_id=rev.revision_id,
            )
        except TwinStoreError as exc:
            return TwinEventResult(
                project_id=event.project_id,
                workspace_id=event.workspace_id,
                event_id=event.event_id,
                accepted=False,
                diagnostics=[_diag(IntelligenceErrorCode.STORE_UNAVAILABLE, str(exc))],
            )

    def ingest_runtime(self, request: RuntimeIngestRequest) -> RuntimeIngestResult:
        internal = self._key(request.project.project_id, request.project.workspace_id)
        observations: list[RuntimeObservation] = []
        diagnostics: list[IntelligenceDiagnostic] = []
        for obs in request.observations:
            if obs.project_id != request.project.project_id or obs.workspace_id != request.project.workspace_id:
                diagnostics.append(
                    _diag(IntelligenceErrorCode.PROJECT_SCOPE_VIOLATION, f"observation {obs.observation_id}")
                )
                continue
            observations.append(
                RuntimeObservation(
                    observation_id=obs.observation_id,
                    project_id=internal,
                    run_id=obs.run_id,
                    collector=obs.collector,
                    collector_version=obs.collector_version,
                    observation_type=obs.observation_type,
                    subject_refs=list(obs.subject_refs),
                    timestamp=obs.timestamp,
                    result=obs.result,
                    summary=obs.summary,
                    payload_ref=obs.payload_ref,
                    evidence_ids=list(obs.evidence_refs),
                )
            )
        if not observations:
            health = self._health(request.project.project_id, request.project.workspace_id)
            return RuntimeIngestResult(
                project_id=request.project.project_id,
                workspace_id=request.project.workspace_id,
                ingested_count=0,
                unavailable_count=0,
                twin_revision_id=health.twin_revision_id,
                diagnostics=diagnostics,
            )
        before = self._health(request.project.project_id, request.project.workspace_id)
        rev = self._store.apply_delta(
            TwinDelta(
                project_id=internal,
                base_revision_id=before.twin_revision_id,
                idempotency_key=f"runtime:{request.correlation_id or uuid.uuid4().hex}",
                trigger_type="runtime_observation.recorded",
                observations=observations,
            )
        )
        return RuntimeIngestResult(
            project_id=request.project.project_id,
            workspace_id=request.project.workspace_id,
            ingested_count=len(observations),
            unavailable_count=sum(1 for obs in request.observations if obs.result == "unavailable"),
            twin_revision_id=rev.revision_id,
            diagnostics=diagnostics,
        )

    def query(self, request: TwinQueryRequest) -> TwinQueryResult:
        internal = self._key(request.project_id, request.workspace_id)
        result = self._store.query(
            StoreTwinQuery(
                project_id=internal,
                revision_id=request.revision_id,
                canonical_refs=list(request.refs),
                text=request.text,
                statuses=request.statuses,
                max_depth=request.max_depth,
                limit=request.limit,
            )
        )
        return TwinQueryResult(
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            twin_revision_id=result.twin_revision_id,
            kind=request.kind,
            items=[
                TwinQueryResultItem(
                    ref=node.canonical_ref,
                    kind=node.node_type,
                    summary=node.label,
                    status=node.status,
                    confidence=node.confidence,
                    source_refs=[node.source_ref],
                )
                for node in result.nodes
            ],
            truncated=result.truncated,
            next_cursor=result.cursor,
        )

    def build_context(self, request: TwinContextRequest) -> TwinContextPackage:
        query = self.query(
            TwinQueryRequest(
                project_id=request.project_id,
                workspace_id=request.workspace_id,
                refs=list(request.target_refs),
                text=request.objective or None,
                limit=max(1, min(100, request.token_budget // 50)),
            )
        )
        items = [
            ContextItem(
                ref=item.ref,
                kind=item.kind,
                summary=item.summary,
                status=item.status,
                confidence=item.confidence,
                source_refs=item.source_refs,
                inclusion_reason="durable twin query",
            )
            for item in query.items
        ]
        return TwinContextPackage(
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            twin_revision_id=query.twin_revision_id,
            phase=request.phase,
            symbols=items,
            manifest=ContextManifest(
                manifest_id=f"twin:{query.twin_revision_id or 'empty'}:{request.phase}",
                project_id=request.project_id,
                workspace_id=request.workspace_id,
                phase=request.phase,
                actual_twin_revision_id=query.twin_revision_id,
                included_refs=[item.ref for item in items],
                token_budget=request.token_budget,
                used_tokens=len(items) * 50,
                truncated=query.truncated,
                rollout_mode="concrete",
            ),
        )

    def health(self, request: TwinHealthRequest) -> TwinHealthReport:
        health = self._health(request.project_id, request.workspace_id)
        readiness = TwinReadiness.READY if health.twin_revision_id else TwinReadiness.ABSENT
        return TwinHealthReport(
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            readiness=readiness,
            twin_revision_id=health.twin_revision_id,
            node_count=health.node_count,
            edge_count=health.edge_count,
            diagnostics=[
                _diag(IntelligenceErrorCode.PROJECT_NOT_FOUND, d.get("detail", "project not found"))
                for d in health.diagnostics
            ],
        )

