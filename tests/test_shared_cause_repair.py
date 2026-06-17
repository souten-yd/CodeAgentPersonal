"""Tests for shared-cause batch repair: single-source verification + assertion-preservation gate."""
from __future__ import annotations

from agent.twin_control_plane.shared_cause_repair import (
    assertion_preserving_edit, build_batch_repair_plan, cluster_shared_causes, extract_cause,
)


def test_extract_cause_recovers_concrete_key():
    assert extract_cause("KeyError: 'plan_pool'") == ("missing_key", "plan_pool")
    assert extract_cause("ValueError: invariant_violation:runtime_level") == ("invariant", "runtime_level")
    assert extract_cause("ValueError: apply_allowed=false patch cannot be approved") == ("policy", "apply_allowed")
    assert extract_cause("AssertionError: assert 'level_1' == 'level_0'") == ("value_mismatch", "level_1|level_0")
    assert extract_cause("IndexError: list index out of range")[0] == "exception"


def test_single_source_cluster_is_batchable():
    # 6 failures that genuinely share ONE cause (the same missing key) -> single-source, batchable.
    failures = [(f"t{i}", "KeyError: 'plan_pool'") for i in range(6)]
    clusters = cluster_shared_causes(failures)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.single_source is True and c.batchable is True
    assert c.kind == "missing_key" and c.key == "plan_pool"
    assert c.homogeneity == 1.0


def test_over_merge_guard_flags_heterogeneous_lookalike():
    # same signature shape ("assert X == X") but every member is a DIFFERENT value mismatch -> NOT
    # single-source; must not be batch-fixed.
    failures = [(f"t{i}", f"AssertionError: assert 'a{i}' == 'b{i}'") for i in range(8)]
    clusters = cluster_shared_causes(failures)
    assert len(clusters) == 1
    c = clusters[0]
    assert c.single_source is False
    assert c.batchable is False
    assert c.homogeneity < 0.9


def test_one_shared_enum_rename_is_single_source():
    # all members are the SAME enum rename -> single-source even though it is a value_mismatch.
    failures = [(f"t{i}", "AssertionError: assert 'level_1_guarded' == 'level_0_manual'") for i in range(7)]
    clusters = cluster_shared_causes(failures)
    assert clusters[0].single_source is True
    assert clusters[0].batchable is True


def test_recognised_but_too_small_is_not_batchable():
    failures = [("t1", "KeyError: 'plan_pool'"), ("t2", "KeyError: 'plan_pool'")]
    c = cluster_shared_causes(failures, min_size=5)[0]
    assert c.single_source is True
    assert c.batchable is False          # below min_size -> individual handling


def test_assertion_preserving_edit_accepts_input_only_change():
    old = "def test_x():\n    payload = {}\n    r = call(payload)\n    assert r['items'][0] == 1\n"
    new = "def test_x():\n    payload = {'items': [1]}\n    r = call(payload, sync=True)\n    assert r['items'][0] == 1\n"
    ok, removed = assertion_preserving_edit(old, new)
    assert ok is True and removed == []


def test_assertion_preserving_edit_rejects_dropped_assertion():
    old = "def test_x():\n    r = call()\n    assert r['items'][0] == 1\n    assert r['status'] == 'ok'\n"
    new = "def test_x():\n    r = call()\n    assert r['status'] == 'ok'\n"   # dropped the items assertion
    ok, removed = assertion_preserving_edit(old, new)
    assert ok is False
    assert removed and removed[0][0] == "assert"


def test_assertion_preserving_edit_rejects_weakened_assertion():
    old = "def test_x():\n    assert value == 'level_1_guarded_single_step'\n"
    new = "def test_x():\n    assert value == 'level_0_manual_only'\n"      # changed the expected value
    ok, _removed = assertion_preserving_edit(old, new)
    assert ok is False                   # the assertion's meaning changed -> not preserved


def test_assertion_preserving_edit_rejects_unparseable():
    ok, removed = assertion_preserving_edit("def test(): assert x", "def test(: assert x")
    assert ok is False and removed


def test_build_batch_repair_plan_splits_batchable_from_individual():
    failures = (
        [(f"k{i}", "KeyError: 'plan_pool'") for i in range(83)]            # batchable
        + [(f"v{i}", f"AssertionError: assert 'a{i}' == 'b{i}'") for i in range(31)]  # heterogeneous
        + [("s1", "RuntimeError: weird one-off")]                          # singleton
    )
    plan = build_batch_repair_plan(failures)
    s = plan.summary()
    assert s["batchable_clusters"] == 1
    assert s["batchable_failures"] == 83
    assert s["individual_failures"] == 32
    assert s["batchable_pct"] > 70
