"""Concrete Digital Twin facade foundation (PIR-1).

This module adapts the existing durable Project Twin store behind the public
``DigitalTwinModule`` facade. It is intentionally minimal: source snapshotting and
deep analyzers land in later PIR packages, but this facade now owns durable
revision, query, context, runtime-ingest, and workspace-isolation behavior.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from agent.project_intelligence.contracts import (
    ContextItem,
    ContextManifest,
    IntelligenceDiagnostic,
    IntelligenceErrorCode,
    RuntimeObservationRecord,
)
from agent.project_twin.contracts import (
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
from agent.project_twin.store import SqliteProjectTwinStore, TwinStoreError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _diag(code: IntelligenceErrorCode, message: str) -> IntelligenceDiagnostic:
    return IntelligenceDiagnostic(code=code, message=message, severity="info")


class DigitalTwinModuleImpl(DigitalTwinModule):
    """Durable concrete Digital Twin facade.

    The legacy store is project-keyed, so the concrete facade scopes each workspace
    under a private internal project key. Public DTOs still return the original
    project/workspace IDs.
    """

    rollout_mode = "concrete"

    def __init__(self, db_path: str | Path | None = None, *, store: SqliteProjectTwinStore | None = None) -> None:
        self._store = store or SqliteProjectTwinStore(db_path)

    def close(self) -> None:
        self._store.close()

    @staticmethod
    def _key(project_id: str, workspace_id: str) -> str:
        return f"{project_id}\x1f{workspace_id}"

    def _health(self, project_id: str, workspace_id: str):
        return self._store.get_health(self._key(project_id, workspace_id))

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

    def open_project(self, request: OpenTwinRequest) -> TwinProjectState:
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

