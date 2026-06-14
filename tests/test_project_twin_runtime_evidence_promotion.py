"""PIBIH-7: runtime evidence promotion + historical risk memory.

A FAILED runtime/verification observation becomes an `incident` graph fact linked to its affected
refs, so future impact analysis surfaces it as a past incident (gated by include_historical_risks). A
PASSED observation becomes additive runtime evidence that supports its subjects WITHOUT marking any
inferred fact verified. Passing evidence never fabricates an incident (no false positives).
"""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.contracts import ProjectIdentity, RuntimeObservationRecord
from agent.project_twin.contracts import ImpactRequest
from agent.project_twin.facade import OpenTwinRequest, RuntimeIngestRequest
from agent.project_twin.module import DigitalTwinModuleImpl

SUBJECT = "py://app.py#f"


def _identity(root: Path) -> ProjectIdentity:
    return ProjectIdentity(project_id="p1", workspace_id="w1", project_path=str(root))


def _obs(result: str, *, oid: str, subject: str = SUBJECT, summary: str = "") -> RuntimeObservationRecord:
    return RuntimeObservationRecord(
        observation_id=oid, project_id="p1", workspace_id="w1", result=result,
        summary=summary or result, subject_refs=[subject], run_id="run1",
    )


def _twin(tmp_path: Path):
    root = tmp_path / "repo"
    (root).mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")
    twin.open_project(OpenTwinRequest(project=_identity(root)))
    return twin, root


def _impact(twin, *, include_historical: bool):
    return twin._store.assess_impact(ImpactRequest(
        project_id=twin._key("p1", "w1"), changed_refs=[SUBJECT], change_kind="body",
        min_confidence=0.0, include_historical_risks=include_historical,
    ))


def test_failed_observation_becomes_incident_linked_to_affected_ref(tmp_path: Path) -> None:
    twin, root = _twin(tmp_path)
    twin.ingest_runtime(RuntimeIngestRequest(project=_identity(root), observations=[_obs("failed", oid="o1", summary="pytest failed")]))

    snap = twin._store.get_snapshot(twin._key("p1", "w1"))
    incident_nodes = [n for n in snap.nodes if n.node_type == "incident"]
    assert any(n.canonical_ref == "incident://o1" for n in incident_nodes)
    # The incident is observed (runtime-backed), never a fabricated/verified inferred fact.
    inc = next(n for n in incident_nodes if n.canonical_ref == "incident://o1")
    assert inc.status == "observed" and inc.derivation == "runtime_observation"
    affects = [e for e in snap.edges if e.edge_type == "affects" and e.source_node_id == inc.node_id]
    assert affects, "incident must link to its affected ref"
    twin.close()


def test_impact_surfaces_past_incident_only_when_requested(tmp_path: Path) -> None:
    twin, root = _twin(tmp_path)
    twin.ingest_runtime(RuntimeIngestRequest(project=_identity(root), observations=[_obs("failed", oid="o1")]))

    with_risks = _impact(twin, include_historical=True)
    assert any(i.canonical_ref == "incident://o1" for i in with_risks.past_incidents)
    without_risks = _impact(twin, include_historical=False)
    assert without_risks.past_incidents == []
    twin.close()


def test_passed_observation_supports_without_incident_or_false_promotion(tmp_path: Path) -> None:
    twin, root = _twin(tmp_path)
    twin.ingest_runtime(RuntimeIngestRequest(project=_identity(root), observations=[_obs("passed", oid="o2")]))

    snap = twin._store.get_snapshot(twin._key("p1", "w1"))
    # A pass creates supporting runtime evidence, never an incident (no false positive).
    assert any(n.canonical_ref == "runtime_evidence://o2" for n in snap.nodes)
    assert not any(n.node_type == "incident" for n in snap.nodes)
    assert any(e.edge_type == "supports" for e in snap.edges)
    # No inferred fact is mutated to verified by a passing observation.
    assert not any(n.status == "verified" for n in snap.nodes if n.domain != "runtime")
    twin.close()


def test_unavailable_observation_does_not_create_incident(tmp_path: Path) -> None:
    twin, root = _twin(tmp_path)
    twin.ingest_runtime(RuntimeIngestRequest(project=_identity(root), observations=[_obs("unavailable", oid="o3")]))
    snap = twin._store.get_snapshot(twin._key("p1", "w1"))
    # `unavailable` is never converted into a failure/incident.
    assert not any(n.node_type == "incident" for n in snap.nodes)
    twin.close()
