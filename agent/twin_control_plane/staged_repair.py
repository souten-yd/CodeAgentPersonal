"""Staged repair — cheap deterministic/static first, pay for coverage only on the residual.

The user's strategy, made concrete: try to fix every failure with the CURRENT cheap capabilities
(traceback / static-call localization → weak-LLM synthesis → verify); then apply the heavier
coverage-based localization ONLY to the failures the cheap path could not fix. This bounds the expensive
step (running each test under coverage + trying several candidate functions) to the genuinely-hard
residual instead of paying it for everything.

It is a thin orchestrator because the machinery already supports it: ``synthesis_repair_loop.repair_one``
takes an injectable ``localize_fn``. Stage A passes the static localizer; Stage B passes the coverage
localizer and runs only on what Stage A left unresolved. The final residual — what even coverage +
synthesis could not fix — is the precise human queue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from agent.twin_control_plane.cause_discovery import localize_by_coverage, localize_from_test_calls
from agent.twin_control_plane.failure_repair_loop import _node_id
from agent.twin_control_plane.improvement_loop import KEPT
from agent.twin_control_plane.synthesis_repair_loop import SynthResult, repair_one

# Stage A resolves these; anything else is escalated to Stage B; Stage B's misses are the human queue.
_RESOLVED = {KEPT}


@dataclass
class StagedReport:
    stage_a: list = field(default_factory=list)      # SynthResult[] from the cheap path
    stage_b: list = field(default_factory=list)      # SynthResult[] from coverage escalation
    fixed: list = field(default_factory=list)        # test ids fixed (either stage)
    residual: list = field(default_factory=list)     # (test_id, reason) still unfixed -> human queue

    def summary(self) -> dict:
        return {
            "total": len(self.stage_a),
            "fixed_stage_a": sum(1 for r in self.stage_a if r.outcome in _RESOLVED),
            "escalated_to_b": len(self.stage_b),
            "fixed_stage_b": sum(1 for r in self.stage_b if r.outcome in _RESOLVED),
            "fixed_total": len(self.fixed),
            "residual": len(self.residual),
        }


def run_staged_repair(
    failures: list,
    *,
    llm_json_fn: Callable[[str, str], Optional[dict]],
    repo_root: str = ".",
    include=("app/", "agent/"),
    escalate_to_coverage: bool = True,
    coverage_localizer: Optional[Callable] = None,
    max_repairs: int = 100,
    **io,
) -> StagedReport:
    """Stage A (cheap: static localize → synthesize → verify) over all ``failures``; Stage B (coverage
    localize → synthesize → verify) over ONLY the ones Stage A left unfixed. Frontier-free."""
    rep = StagedReport()
    reason_by_id = {str(t): r for t, r in failures}
    stage_a_localize = io.pop("localize_fn", None)   # Stage A localizer (static by default); B overrides

    # --- Stage A: current-capability repair on everything (static/traceback localizer) ---
    for test_id, reason in list(failures)[: max(0, max_repairs)]:
        res = repair_one(test_id, reason, llm_json_fn=llm_json_fn, repo_root=repo_root,
                         include=include, localize_fn=stage_a_localize, **io)
        rep.stage_a.append(res)
        if res.outcome in _RESOLVED:
            rep.fixed.append(test_id)

    unresolved = [r for r in rep.stage_a if r.outcome not in _RESOLVED]
    if not escalate_to_coverage:
        rep.residual = [(r.test_id, reason_by_id.get(r.test_id, "")) for r in unresolved]
        return rep

    # --- Stage B: pay for coverage ONLY on the residual ---
    cov_loc = coverage_localizer or (
        lambda nid: localize_by_coverage(nid, repo_root=repo_root, include=include))
    for r in unresolved:
        test_id = r.test_id
        node = _node_id(test_id)            # coverage runs pytest -> needs the file::name node id
        res = repair_one(
            test_id, reason_by_id.get(test_id, ""), llm_json_fn=llm_json_fn, repo_root=repo_root,
            include=include, localize_fn=lambda _src, _tn, _nid=node: cov_loc(_nid), **io)
        rep.stage_b.append(res)
        if res.outcome in _RESOLVED:
            rep.fixed.append(test_id)

    fixed_set = set(rep.fixed)
    rep.residual = [(r.test_id, reason_by_id.get(r.test_id, ""))
                    for r in rep.stage_b if r.test_id not in fixed_set]
    return rep
