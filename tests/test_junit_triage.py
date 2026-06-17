"""Tests for parsing a pytest junit-xml report into the routed batch triage (no real model)."""
from __future__ import annotations

from agent.twin_control_plane.failure_classifier import ENVIRONMENT, GENUINELY_BROKEN
from agent.twin_control_plane.junit_triage import parse_junit_failures, run_junit_triage

_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="5" failures="3" errors="1">
    <testcase classname="tests.test_a" name="test_pass"/>
    <testcase classname="tests.test_a" name="test_plan_pool_1">
      <failure message="KeyError: 'plan_pool'">traceback ... KeyError: 'plan_pool'</failure>
    </testcase>
    <testcase classname="tests.test_b" name="test_plan_pool_2">
      <failure message="KeyError: 'plan_pool'">other traceback KeyError: 'plan_pool'</failure>
    </testcase>
    <testcase classname="tests.test_c" name="test_crlf">
      <failure message="AssertionError: assert 'asset ready\\r\\n' == 'asset ready\\n'">full traceback here</failure>
    </testcase>
    <testcase classname="tests.test_d" name="test_collect">
      <error message="ModuleNotFoundError: No module named 'web.atlas-next'">import error</error>
    </testcase>
  </testsuite>
</testsuites>
"""


def _write(tmp_path):
    p = tmp_path / "junit.xml"
    p.write_text(_JUNIT, encoding="utf-8")
    return str(p)


def test_parse_skips_passing_and_keeps_failures_and_errors(tmp_path):
    failures = parse_junit_failures(_write(tmp_path))
    ids = [tid for tid, _ in failures]
    assert "tests.test_a::test_pass" not in ids
    assert "tests.test_a::test_plan_pool_1" in ids
    assert "tests.test_d::test_collect" in ids        # <error> is kept too
    assert len(failures) == 4


def test_reason_carries_message_and_body(tmp_path):
    failures = dict(parse_junit_failures(_write(tmp_path)))
    reason = failures["tests.test_c::test_crlf"]
    assert "AssertionError" in reason          # message attribute
    assert "asset ready" in reason             # message carries the CRLF comparison (pytest rewrite)


def test_run_triage_clusters_and_costs(tmp_path):
    # No judge: deterministic dry run. The two plan_pool failures share one low-confidence cluster.
    result, cost = run_junit_triage(_write(tmp_path), judge_fn=None)
    assert result.total == 4
    assert cost["naive_llm_calls"] == 4
    # plan_pool (KeyError, no marker) is the only low-confidence GENUINELY_BROKEN cluster;
    # the CRLF assert and the collection error match env markers -> high confidence, not escalated.
    assert cost["routed_llm_calls"] == 1
    assert result.deterministic_counts.get(ENVIRONMENT, 0) >= 2


def test_run_triage_judges_one_rep_per_cluster(tmp_path):
    calls = {"n": 0}

    def judge(reason, test_id):
        calls["n"] += 1
        return GENUINELY_BROKEN

    result, _cost = run_junit_triage(_write(tmp_path), judge_fn=judge)
    assert calls["n"] == result.clusters == 1     # one representative judged for the plan_pool cluster
    assert result.llm_calls == 1
