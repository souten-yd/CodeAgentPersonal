"""TwinProof test-management plan.

TwinProof *classifies* tests (impacted / stale / coverage-gap / flaky / redundant) but stops there.
This turns those classifications into a concrete, prioritized, **approval-gated** action plan — the
"what do I do about the tests now that I'm changing the code" that TwinProof should drive:

- RERUN       — tests impacted by the change must be re-run and stay green.
- UPDATE      — an impacted test that just failed asserts the changed behavior; reconcile test vs code.
- ADD_COVERAGE— a coverage gap: write a test that proves the change.
- QUARANTINE  — a flaky test: quarantine / retry rather than trust or delete.
- RETIRE      — a stale test (its subject no longer exists): retire **after approval**, never auto-delete.
- CONSOLIDATE — redundant tests: merge **after approval**.

Destructive actions (retire/consolidate) are always ``approval_required`` and advisory — consistent with
the ``stale_test_judgment`` guard ("do not auto-delete a still-relevant test"). This module never deletes,
runs, or mutates anything; it produces a plan that the orchestrator surfaces and the model/operator acts on.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from pydantic import Field

from agent.twin_control_plane.contracts import TwinControlPlaneModel
from agent.twin_control_plane.twinproof import TwinProofReport


class TestAction(StrEnum):
    RERUN = "rerun"
    UPDATE = "update"
    ADD_COVERAGE = "add_coverage"
    QUARANTINE = "quarantine"
    RETIRE = "retire"
    CONSOLIDATE = "consolidate"


TestAction.__test__ = False  # not a pytest class

# Destructive actions that must never run autonomously.
_APPROVAL_REQUIRED = {TestAction.RETIRE, TestAction.CONSOLIDATE}


class TestActionItem(TwinControlPlaneModel):
    action: TestAction
    test_refs: list[str] = Field(default_factory=list)
    approval_required: bool = False
    reason: str = ""


class TestManagementPlan(TwinControlPlaneModel):
    items: list[TestActionItem] = Field(default_factory=list)

    def refs_for(self, action: TestAction) -> list[str]:
        return [r for item in self.items if item.action == action for r in item.test_refs]

    @property
    def is_empty(self) -> bool:
        return not self.items

    def to_dict(self) -> dict:
        return {
            "items": [
                {"action": i.action.value, "test_refs": list(i.test_refs),
                 "approval_required": i.approval_required, "reason": i.reason}
                for i in self.items
            ],
            "rerun_count": len(self.refs_for(TestAction.RERUN)),
            "add_coverage_count": len(self.refs_for(TestAction.ADD_COVERAGE)),
            "retire_count": len(self.refs_for(TestAction.RETIRE)),
            "consolidate_count": len(self.refs_for(TestAction.CONSOLIDATE)),
        }


def _is_test_ref(ref: str) -> bool:
    r = str(ref or "")
    return r.startswith("test://") or r.startswith("py://tests/") or "/tests/" in r or "/test_" in r


def select_impacted_tests(impact, *, top_k: int = 50, min_confidence: float = 0.6) -> list[dict]:
    """Prioritized, BOUNDED set of tests to re-run for a change.

    The raw impact reachability over-selects on a large repo (≈34% of the suite for a leaf module,
    because transitive heuristic links connect everything). assess_impact records each impact's path
    confidence as the WEAKEST edge along the path, so heuristic-reached tests score low. This keeps only
    tests at or above ``min_confidence`` and returns the top ``top_k`` by confidence — turning a
    reachability set into an actionable selection. Returns [{"test_ref", "confidence"}], highest first."""
    if impact is None:
        return []
    items = [
        *(getattr(impact, "direct_impacts", []) or []),
        *(getattr(impact, "transitive_impacts", []) or []),
        *(getattr(impact, "recommended_tests", []) or []),
    ]
    best: dict[str, float] = {}
    for i in items:
        ref = str(getattr(i, "canonical_ref", ""))
        if not _is_test_ref(ref):
            continue
        conf = float(getattr(i, "confidence", 0.0) or 0.0)
        if conf < min_confidence:
            continue
        if ref not in best or conf > best[ref]:
            best[ref] = conf
    ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))[: max(0, top_k)]
    return [{"test_ref": r, "confidence": round(c, 4)} for r, c in ranked]


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        s = str(v).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def build_test_management_plan(report: TwinProofReport | None, *, failed_test_refs: Iterable[str] = ()) -> TestManagementPlan:
    """Turn a TwinProofReport into an actionable, approval-gated plan. ``failed_test_refs`` (tests that
    failed after the change) split the impacted set into RERUN vs UPDATE. Empty when there is no report."""
    if report is None:
        return TestManagementPlan()
    failed = set(_unique(failed_test_refs))
    impacted = _unique(report.impacted_tests)
    # Re-run the impacted tests that did NOT (yet) fail — confirm the change kept them green. Put the
    # failed-impacted ones in UPDATE instead (they assert the changed behavior).
    rerun = [t for t in impacted if t not in failed]
    update = [t for t in impacted if t in failed]

    items: list[TestActionItem] = []
    if rerun:
        items.append(TestActionItem(action=TestAction.RERUN, test_refs=rerun, approval_required=False,
                                    reason="impacted by the change; must be re-run and stay green"))
    if update:
        items.append(TestActionItem(action=TestAction.UPDATE, test_refs=update, approval_required=False,
                                    reason="impacted test failed after the change; reconcile test vs implementation"))
    if report.coverage_gaps:
        items.append(TestActionItem(action=TestAction.ADD_COVERAGE, test_refs=_unique(report.coverage_gaps),
                                    approval_required=False, reason="no test proves this change; add focused coverage"))
    if report.flaky_candidates:
        items.append(TestActionItem(action=TestAction.QUARANTINE, test_refs=_unique(report.flaky_candidates),
                                    approval_required=False, reason="flaky signal; quarantine / retry rather than trust or delete"))
    if report.stale_candidates:
        items.append(TestActionItem(action=TestAction.RETIRE, test_refs=_unique(report.stale_candidates),
                                    approval_required=True,
                                    reason="stale: the subject under test no longer exists; retire after explicit approval"))
    if report.redundant_candidates:
        items.append(TestActionItem(action=TestAction.CONSOLIDATE, test_refs=_unique(report.redundant_candidates),
                                    approval_required=True, reason="redundant coverage; consolidate after explicit approval"))
    return TestManagementPlan(items=items)


TEST_MANAGEMENT_HEADER = (
    "[Twin Test Management — advisory. Keep the RERUN tests green and add tests for the coverage gaps. "
    "Do NOT delete, retire, or merge any test marked RETIRE/CONSOLIDATE — those require explicit human "
    "approval; surface them as recommendations only.]"
)


def render_test_management_directive(plan: TestManagementPlan | None) -> str:
    """Render the plan as a bounded advisory section. Returns "" when there is nothing to do."""
    if plan is None or plan.is_empty:
        return ""
    label = {
        TestAction.RERUN: "Re-run (must stay green)",
        TestAction.UPDATE: "Reconcile (test failed after the change — fix code or test)",
        TestAction.ADD_COVERAGE: "Add coverage (write a focused test)",
        TestAction.QUARANTINE: "Quarantine (flaky)",
        TestAction.RETIRE: "Retire candidates (REQUIRE APPROVAL — do not delete now)",
        TestAction.CONSOLIDATE: "Consolidate candidates (REQUIRE APPROVAL — do not merge now)",
    }
    lines = [TEST_MANAGEMENT_HEADER]
    for item in plan.items:
        refs = ", ".join(item.test_refs[:12])
        extra = " …" if len(item.test_refs) > 12 else ""
        lines.append(f"- {label.get(item.action, item.action.value)}: {refs}{extra}")
    return "\n".join(lines)
