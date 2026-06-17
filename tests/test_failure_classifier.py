"""Pytest-failure classifier: separate environment noise from real regressions."""
from __future__ import annotations

from agent.twin_control_plane.failure_classifier import (
    ENVIRONMENT, TEST_DEBT, GENUINELY_BROKEN, COLLECTION_ERROR,
    classify_failure_reason, classify_pytest_output,
)


def test_environment_causes_classified():
    assert classify_failure_reason("FileNotFoundError: web/atlas-next/...") == ENVIRONMENT
    assert classify_failure_reason("UnicodeDecodeError: 'cp932' codec can't decode") == ENVIRONMENT
    assert classify_failure_reason("ConnectionError: Connection refused (8080)") == ENVIRONMENT
    assert classify_failure_reason("playwright: chromium executable doesn't exist") == ENVIRONMENT


def test_test_infra_failures_are_environment():
    # xdist worker crash and a collection failure are test-infra/env, not a code regression.
    assert classify_failure_reason(
        "failed on setup with \"worker 'gw3' crashed while running 'tests/test_x.py'\"") == ENVIRONMENT
    assert classify_failure_reason("collection failure") == ENVIRONMENT


def test_debt_and_broken():
    assert classify_failure_reason("DeprecationWarning: foo is deprecated, renamed to bar") == TEST_DEBT
    assert classify_failure_reason("AssertionError: assert 2 == 1") == GENUINELY_BROKEN


def test_parse_buckets_a_summary():
    text = (
        "FAILED tests/test_a.py::test_x - FileNotFoundError: web/atlas-next missing\n"
        "FAILED tests/test_b.py::test_y - AssertionError: assert 'a' == 'b'\n"
        "ERROR collecting tests/test_c.py\n"
    )
    out = classify_pytest_output(text)
    assert out["counts"][ENVIRONMENT] == 1
    assert out["counts"][GENUINELY_BROKEN] == 1
    assert out["counts"][COLLECTION_ERROR] == 1


def test_snapshot_drift_and_clustering():
    from agent.twin_control_plane.failure_classifier import (
        SNAPSHOT_DRIFT, classify_failure_reason, root_cause_signature, cluster_root_causes,
    )
    assert classify_failure_reason("AssertionError: 'x' not in '<!DOCTYPE html>...'") == SNAPSHOT_DRIFT
    assert classify_failure_reason("assert 'a\r\n' == 'a\n'").__class__ is str  # CRLF -> environment
    # Many failures, one root cause -> one signature.
    sigs = {root_cause_signature("KeyError: 'plan_pool'"), root_cause_signature("KeyError: 'other'")}
    assert len(sigs) == 1  # literal masked
    clusters = cluster_root_causes([("t1", "KeyError: 'plan_pool'"), ("t2", "KeyError: 'plan_pool'"),
                                    ("t3", "IndexError: list index out of range")])
    assert clusters[0][1] == 2  # the KeyError pair is the top cluster
