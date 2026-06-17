"""Autonomous failure-repair loop — wire the shared-cause repair into the G3 self-improvement cycle.

The repair pieces existed (cluster a failure set by shared cause, apply a templated input fix, gate it
with assertion-preservation) but were only ever run from throwaway scripts. This makes them a first-class
autonomous capability by composing them with the EXISTING `improvement_loop`: each batchable cluster
becomes a repair GOAL, and the loop's ``execute -> verify -> keep/rollback`` runs frontier-free —

- execute  (deterministic, optionally weak-LLM): apply the contract-drift template to the cluster's test
  files, gated by ``assertion_preserving_edit`` (an edit that would touch an assertion is refused);
- verify   (deterministic, NO model): run the cluster's impacted tests;
- rollback (Git): a cluster the template does not fix is reverted, never left broken;
- safety: a cluster whose files touch the control surface (``self_protected``) is not auto-applied.

No frontier model anywhere. The only place a model could enter is a future ``synthesize_fn`` for a drift
whose shape the deterministic template does NOT match — and even then the verify/rollback gate is the
authority. All IO is injected so the loop is unit-testable with stubs and wires to real
pytest/git in production.
"""
from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from agent.twin_control_plane.improvement_loop import CycleResult, run_improvement_backlog
from agent.twin_control_plane.shared_cause_repair import (
    assertion_preserving_edit, cluster_shared_causes,
)
from agent.twin_control_plane.sync_contract_repair import repair_sync_contracts

# Never auto-edit the system's own control surface — those changes require approval (self_protected).
_CONTROL_PREFIXES = ("agent/twin_control_plane/", "agent/atlas_llm_json_adapter")
# Cluster kinds we have a deterministic template for today. Others are left for a synthesize step.
_TEMPLATED_KINDS = ("missing_key",)


@dataclass
class RepairGoal:
    goal_id: str
    signature: str
    kind: str
    test_files: list = field(default_factory=list)     # repo-relative file paths to repair
    test_ids: list = field(default_factory=list)        # pytest node ids to verify
    self_protected: bool = False
    members: int = 0


def _test_file_of(test_id: str) -> str:
    """``tests.test_x::test_y`` / ``tests/test_x.py::test_y`` -> ``tests/test_x.py``."""
    head = str(test_id).split("::", 1)[0]
    if head.endswith(".py"):
        return head
    return head.replace(".", "/") + ".py"


def _node_id(test_id: str) -> str:
    f = _test_file_of(test_id)
    name = str(test_id).split("::", 1)[1] if "::" in str(test_id) else ""
    return f"{f}::{name}" if name else f


def build_repair_goals(failures: list, *, templated_kinds: tuple = _TEMPLATED_KINDS) -> list[RepairGoal]:
    """One repair goal per batchable, templated shared-cause cluster, carrying the files to edit and the
    impacted test ids to verify. A goal touching the control surface is marked ``self_protected``."""
    goals: list[RepairGoal] = []
    for c in cluster_shared_causes(failures):
        if not c.batchable or c.kind not in templated_kinds:
            continue
        by_file: dict[str, list] = defaultdict(list)
        for test_id, _reason in c.members:
            by_file[_test_file_of(test_id)].append(_node_id(test_id))
        files = sorted(by_file)
        protected = any(f.startswith(p) for f in files for p in _CONTROL_PREFIXES)
        goals.append(RepairGoal(
            goal_id=f"repair:{c.kind}:{c.key}", signature=c.signature, kind=c.kind,
            test_files=files, test_ids=sorted(n for ns in by_file.values() for n in ns),
            self_protected=protected, members=c.size))
    return goals


def _default_run_tests(node_ids: list, *, repo_root: str = ".") -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *node_ids, "-p", "no:cacheprovider", "-q", "--timeout=120"],
        cwd=repo_root, capture_output=True, text=True)
    return proc.returncode == 0


def _default_git_checkout(paths: list, *, repo_root: str = ".") -> None:
    if paths:
        subprocess.run(["git", "checkout", "--", *paths], cwd=repo_root, check=False)


def make_repair_callables(
    *,
    repair_fn: Callable[[str], tuple] = repair_sync_contracts,
    read_fn: Optional[Callable[[str], str]] = None,
    write_fn: Optional[Callable[[str, str], None]] = None,
    run_tests_fn: Optional[Callable[[list], bool]] = None,
    git_checkout_fn: Optional[Callable[[list], None]] = None,
    repo_root: str = ".",
):
    """Build the ``(execute_fn, verify_fn, rollback_fn)`` triple the improvement loop drives. All IO is
    injectable; defaults do real file IO + pytest + git so it runs in production unchanged."""
    def _read(p: str) -> str:
        return (read_fn or (lambda q: (Path(repo_root) / q).read_text(encoding="utf-8")))(p)

    def _write(p: str, s: str) -> None:
        (write_fn or (lambda q, t: (Path(repo_root) / q).write_text(t, encoding="utf-8")))(p, s)

    run_tests = run_tests_fn or (lambda ids: _default_run_tests(ids, repo_root=repo_root))
    git_checkout = git_checkout_fn or (lambda ps: _default_git_checkout(ps, repo_root=repo_root))

    def execute_fn(goal: RepairGoal) -> dict:
        changed_files: list[str] = []
        for f in goal.test_files:
            old = _read(f)
            new, n = repair_fn(old)
            if n == 0 or new == old:
                continue
            ok, removed = assertion_preserving_edit(old, new)
            if not ok:                                  # would touch an assertion -> refuse this file
                continue
            _write(f, new)
            changed_files.append(f)
        return {"changed": bool(changed_files), "changed_files": changed_files}

    def verify_fn(_goal: RepairGoal, exec_result: dict) -> bool:
        # only verify if something changed; run the impacted tests deterministically
        return run_tests(list(_goal.test_ids))

    def rollback_fn(_goal: RepairGoal, exec_result: dict) -> None:
        git_checkout(list(exec_result.get("changed_files", [])))

    return execute_fn, verify_fn, rollback_fn


def run_failure_repair(
    failures: list,
    *,
    repair_fn: Callable[[str], tuple] = repair_sync_contracts,
    read_fn: Optional[Callable[[str], str]] = None,
    write_fn: Optional[Callable[[str, str], None]] = None,
    run_tests_fn: Optional[Callable[[list], bool]] = None,
    git_checkout_fn: Optional[Callable[[list], None]] = None,
    repo_root: str = ".",
    approved_goal_ids: Optional[set] = None,
    max_cycles: int = 50,
) -> list[CycleResult]:
    """Autonomously repair ``failures`` through the G3 loop: one cycle per batchable shared-cause cluster,
    each gated by assertion-preservation and verified by running the impacted tests, rolled back on
    failure. Frontier-free. Returns the per-cluster ``CycleResult`` list."""
    goals = build_repair_goals(failures)
    execute_fn, verify_fn, rollback_fn = make_repair_callables(
        repair_fn=repair_fn, read_fn=read_fn, write_fn=write_fn, run_tests_fn=run_tests_fn,
        git_checkout_fn=git_checkout_fn, repo_root=repo_root)
    return run_improvement_backlog(
        goals, execute_fn=execute_fn, verify_fn=verify_fn, rollback_fn=rollback_fn,
        max_cycles=max_cycles, approved_goal_ids=approved_goal_ids)
