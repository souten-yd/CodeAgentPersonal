"""PI-12 Blueprint-to-Actual mapping hints tests.

Acceptance criteria (implementation plan PI-12):
- mapping uses public snapshots/packages (no Twin internals);
- Blueprint remains valid when the Twin store implementation changes;
- heuristically suggested mapping is never silently accepted as verified;
- mapping history follows Blueprint and Twin revisions.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent.architecture_blueprint.contracts import BlueprintElement, BlueprintRevision
from agent.architecture_blueprint.lifecycle import planner_decision
from agent.architecture_blueprint.mapping import (
    BLOCKED_BY,
    INFERRED,
    MATERIALIZED_AS,
    REALIZED_BY,
    VERIFIED,
    VERIFIED_BY,
    build_mapping_set,
    confirm_mapping,
    snapshot_from_public,
    suggest_mappings,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _revision() -> BlueprintRevision:
    return BlueprintRevision(
        blueprint_id="b", revision_id="bprev-1", project_id="p1", scope="full_project",
        selected_architecture=planner_decision("d", "t", [], "", []),
        elements=[
            BlueprintElement(element_id="e_models", canonical_ref="bp://app/models.py",
                             element_type="file", name="models.py",
                             expected_actual_refs=["file://app/models.py"], acceptance_criteria=["x"]),
            BlueprintElement(element_id="e_service", canonical_ref="bp://app/service.py",
                             element_type="file", name="service.py", acceptance_criteria=["y"]),
            BlueprintElement(element_id="e_missing", canonical_ref="bp://app/missing.py",
                             element_type="file", name="missing.py", mandatory=True,
                             acceptance_criteria=["z"]),
        ],
    )


# --- Deterministic relations -------------------------------------------------

def test_materialized_realized_blocked() -> None:
    # Public snapshot (e.g. from a TwinQueryResult), not a Twin internal object.
    snapshot = snapshot_from_public([
        {"ref": "file://app/models.py", "name": "models.py", "kind": "file"},
        {"ref": "file://app/service.py", "name": "service.py", "kind": "file"},
    ])
    hints = {h.blueprint_element_id: h for h in suggest_mappings(_revision(), snapshot, twin_revision_id="t1")}
    # exact expected ref -> materialized_as
    assert hints["e_models"].relation == MATERIALIZED_AS and hints["e_models"].actual_ref == "file://app/models.py"
    # name heuristic -> realized_by (inferred, not verified)
    assert hints["e_service"].relation == REALIZED_BY and hints["e_service"].status == INFERRED
    # mandatory unmatched -> blocked_by
    assert hints["e_missing"].relation == BLOCKED_BY and hints["e_missing"].actual_ref is None


# --- Heuristic never silently verified ---------------------------------------

def test_heuristic_mapping_is_inferred_not_verified() -> None:
    snapshot = snapshot_from_public([{"ref": "file://x.py", "name": "service.py"}])
    hints = suggest_mappings(_revision(), snapshot, twin_revision_id="t1")
    assert all(h.status == INFERRED for h in hints)
    # confirm requires evidence.
    realized = next(h for h in hints if h.relation == REALIZED_BY)
    with pytest.raises(ValueError):
        confirm_mapping(realized, [])
    verified = confirm_mapping(realized, ["runtime://obs1"])
    assert verified.status == VERIFIED and verified.relation == VERIFIED_BY
    assert verified.evidence_refs == ("runtime://obs1",)


# --- Mapping history follows Blueprint and Twin revisions --------------------

def test_mapping_carries_blueprint_and_twin_revisions() -> None:
    snapshot = snapshot_from_public([{"ref": "file://app/models.py", "name": "models.py"}])
    ms1 = build_mapping_set(_revision(), snapshot, twin_revision_id="t1")
    ms2 = build_mapping_set(_revision(), snapshot, twin_revision_id="t2")
    assert ms1.key() == ("bprev-1", "t1") and ms2.key() == ("bprev-1", "t2")
    assert all(h.twin_revision_id == "t1" for h in ms1.hints)
    assert all(h.blueprint_revision_id == "bprev-1" for h in ms1.hints)


# --- Determinism -------------------------------------------------------------

def test_mapping_is_deterministic() -> None:
    snapshot = snapshot_from_public([{"ref": "file://app/models.py", "name": "models.py"}])
    a = suggest_mappings(_revision(), snapshot, twin_revision_id="t1")
    b = suggest_mappings(_revision(), snapshot, twin_revision_id="t1")
    assert [(h.blueprint_element_id, h.relation, h.actual_ref) for h in a] == \
           [(h.blueprint_element_id, h.relation, h.actual_ref) for h in b]


# --- Decoupling: mapping does not import Twin internals ----------------------

def test_mapping_module_does_not_import_project_twin() -> None:
    src = (REPO_ROOT / "agent" / "architecture_blueprint" / "mapping.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any(m.startswith("agent.project_twin") for m in imported), \
        "Blueprint mapping must not couple to Digital Twin internals"
