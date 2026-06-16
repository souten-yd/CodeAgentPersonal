"""Schema Guardian gated blocking promotion + StateMirror observation sources."""
from __future__ import annotations

from agent.twin_control_plane.active_integration import PipelineMode
from agent.twin_control_plane.pipeline_integration import (
    evaluate_twin_post_apply, python_schema_snapshot, resolve_block_schema,
)
from agent.twin_control_plane.schema_guardian import SchemaSnapshot
from agent.twin_control_plane.state_mirror import StateObservation, StateSurface


def _post(**kw):
    base = dict(mode=PipelineMode.ACTIVE, blocking=True, requirement="x", pool_id="p",
                changed_files=["a.py"], before_twin_revision_id="b", after_twin_revision_id="a",
                verification=[{"evidence_id": "v", "status": "passed"}])
    base.update(kw)
    return evaluate_twin_post_apply(**base)


def _snap(tmp_path, sub, content):
    d = tmp_path / sub
    d.mkdir(exist_ok=True)
    (d / "m.py").write_text(content, encoding="utf-8")
    return SchemaSnapshot.model_validate(python_schema_snapshot(str(d), ["m.py"]).model_dump())


def test_block_schema_flag_defaults_off_and_reversible(monkeypatch):
    monkeypatch.delenv("ATLAS_TWIN_BLOCK_SCHEMA", raising=False)
    assert resolve_block_schema() is False
    for on in ("1", "on", "true", "yes"):
        monkeypatch.setenv("ATLAS_TWIN_BLOCK_SCHEMA", on)
        assert resolve_block_schema() is True


def test_breaking_schema_blocks_only_when_promoted(tmp_path):
    before = _snap(tmp_path, "before", "def add(a, b):\n    return a+b\n")
    after = _snap(tmp_path, "after", "def other():\n    return 1\n")  # 'add' removed -> breaking
    # Advisory (default): records would-block but does NOT block.
    adv = _post(before_schema=before, after_schema=after, block_schema=False)
    assert adv["advisory_schema"]["would_block_if_promoted"] is True
    assert adv["gate_blocked"] is False
    # Promoted: the breaking change blocks (drives the repair loop).
    promoted = _post(before_schema=before, after_schema=after, block_schema=True)
    assert promoted["gate_blocked"] is True
    assert promoted["block_reason"] == "twin_post_apply_hard_boundary"
    assert promoted["schema_promoted_to_block"] is True


def test_additive_schema_never_blocks_even_when_promoted(tmp_path):
    after = _snap(tmp_path, "after", "def add(a, b):\n    return a+b\n")  # new file, before=None
    r = _post(before_schema=None, after_schema=after, block_schema=True)
    assert r["gate_blocked"] is False           # additive/new schema is not a breaking block
    assert r["schema_promoted_to_block"] is False


def test_state_observations_make_advisory_state_available():
    runtime = [StateObservation(path="runtime.verification.i1", value="passed",
                               surface=StateSurface.RUNTIME, evidence_status="passed", authoritative=True)]
    persisted = [StateObservation(path="persistence.a.py", value=True,
                                 surface=StateSurface.PERSISTENCE, evidence_status="passed", authoritative=True)]
    r = _post(runtime_state=runtime, persisted_state=persisted)
    assert r["advisory_state"]["available"] is True
    assert "would_block_if_promoted" in r["advisory_state"]
