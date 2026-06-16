"""R2 — advisory Schema Guardian + StateMirror live wiring (records, never blocks)."""
from __future__ import annotations

from agent.twin_control_plane.active_integration import PipelineMode
from agent.twin_control_plane.pipeline_integration import (
    evaluate_twin_post_apply, python_schema_snapshot,
)
from agent.twin_control_plane.schema_guardian import SchemaSnapshot


def _post(**kw):
    base = dict(mode=PipelineMode.ACTIVE, blocking=True, requirement="x", pool_id="p",
                changed_files=["a.py"], before_twin_revision_id="b", after_twin_revision_id="a",
                verification=[{"evidence_id": "v", "status": "passed"}])
    base.update(kw)
    return evaluate_twin_post_apply(**base)


def test_schema_snapshot_from_python_files(tmp_path):
    (tmp_path / "m.py").write_text("def add(a, b):\n    return a + b\n\nclass C:\n    pass\n", encoding="utf-8")
    snap = python_schema_snapshot(str(tmp_path), ["m.py"])
    assert snap is not None
    names = {f.name for f in snap.fields}
    assert "add" in names and "C" in names


def test_missing_or_nonpython_yields_no_snapshot(tmp_path):
    assert python_schema_snapshot(str(tmp_path), ["nope.py"]) is None
    assert python_schema_snapshot(str(tmp_path), ["data.json"]) is None


def test_advisory_schema_recorded_but_does_not_block(tmp_path):
    # Breaking change: 'add' removed in the after snapshot.
    before = SchemaSnapshot.model_validate(python_schema_snapshot(
        str(_write(tmp_path, "before", "def add(a, b):\n    return a+b\n")), ["m.py"]).model_dump())
    after = SchemaSnapshot.model_validate(python_schema_snapshot(
        str(_write(tmp_path, "after", "def other():\n    return 1\n")), ["m.py"]).model_dump())
    r = _post(before_schema=before, after_schema=after)
    adv = r["advisory_schema"]
    assert adv["available"] is True
    # It records a would-block-if-promoted signal but the gate is NOT actually blocked.
    assert r["gate_blocked"] is False
    assert "would_block_if_promoted" in adv


def test_advisory_state_unavailable_without_observations():
    r = _post()
    assert r["advisory_state"]["available"] is False
    assert r["advisory_schema"]["available"] is False  # no schema snapshots passed


def _write(tmp_path, sub, content):
    d = tmp_path / sub
    d.mkdir(exist_ok=True)
    (d / "m.py").write_text(content, encoding="utf-8")
    return d
