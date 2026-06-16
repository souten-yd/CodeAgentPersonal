"""Autonomous self-improvement cycle — the G3 execution loop.

Strings the pieces into one frontier-free cycle: pick the top goal (deterministic backlog from
`goal_generator`), honor the safety boundaries, execute it through the existing codegen path, verify
DETERMINISTICALLY (run the impacted tests — no model), and roll back via Git if verification fails.

Design constraints (the standing policy):
- deterministic-first: goal selection, verification and rollback are deterministic; the only model use
  is inside ``execute_fn`` (code generation, which inherently needs an LLM — the local weak one).
- safety is structural, not model-based: a goal that touches the system's own control modules
  (``self_protected``) is never auto-applied — it returns NEEDS_APPROVAL; and a failed verification
  triggers a Git rollback, so a bad change never sticks.

The orchestration here takes injected callables so it is unit-testable with stubs and wires to the real
codegen orchestrator / verification runner / git steward in production.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

# Outcomes of one cycle.
KEPT = "kept"                    # executed, verification passed, change kept
ROLLED_BACK = "rolled_back"      # executed, verification failed, change reverted
NEEDS_APPROVAL = "needs_approval"  # self-protected target — not auto-applied
SKIPPED = "skipped"              # nothing to do / execution produced no change
ERROR = "error"                  # execution/verification raised (rolled back, never fatal)


@dataclass
class CycleResult:
    goal_id: str
    outcome: str
    detail: str = ""
    changed: bool = False
    verified: bool = False
    evidence: dict = field(default_factory=dict)


def run_improvement_cycle(
    goal,
    *,
    execute_fn: Callable[[object], dict],
    verify_fn: Callable[[object, dict], bool],
    rollback_fn: Callable[[object, dict], None],
    approved: bool = False,
) -> CycleResult:
    """Run one improvement cycle for ``goal``.

    ``execute_fn(goal) -> {"changed": bool, "changed_files": [...], ...}`` performs the change (via the
    codegen path + Safe Apply). ``verify_fn(goal, exec_result) -> bool`` runs the deterministic check
    (impacted tests). ``rollback_fn(goal, exec_result)`` reverts via Git. None of them is allowed to be
    skipped: a self-protected goal stops before execution; a failed verify always rolls back."""
    gid = str(getattr(goal, "goal_id", "") or "goal")

    # 1. Safety boundary — never auto-modify the system's own control surface.
    if getattr(goal, "self_protected", False) and not approved:
        return CycleResult(goal_id=gid, outcome=NEEDS_APPROVAL,
                           detail="target is a self-protected control module; requires explicit approval")

    # 2. Execute (the only step that uses a model — code generation).
    try:
        exec_result = execute_fn(goal) or {}
    except Exception as exc:  # noqa: BLE001 — never fatal; nothing was kept.
        return CycleResult(goal_id=gid, outcome=ERROR, detail=f"execute_error:{type(exc).__name__}:{str(exc)[:120]}")

    if not exec_result.get("changed"):
        return CycleResult(goal_id=gid, outcome=SKIPPED, detail="execution produced no change",
                           evidence=dict(exec_result))

    # 3. Deterministic verification (impacted tests — no model).
    try:
        ok = bool(verify_fn(goal, exec_result))
    except Exception as exc:  # noqa: BLE001 — a verification error is treated as a failure -> rollback.
        ok = False
        exec_result = {**exec_result, "verify_error": f"{type(exc).__name__}:{str(exc)[:120]}"}

    if ok:
        return CycleResult(goal_id=gid, outcome=KEPT, detail="verification passed; change kept",
                           changed=True, verified=True, evidence=dict(exec_result))

    # 4. Rollback (Git) — a failed change never sticks.
    try:
        rollback_fn(goal, exec_result)
        detail = "verification failed; change rolled back"
    except Exception as exc:  # noqa: BLE001
        detail = f"verification failed; ROLLBACK ERROR {type(exc).__name__}:{str(exc)[:120]}"
    return CycleResult(goal_id=gid, outcome=ROLLED_BACK, detail=detail, changed=True, verified=False,
                       evidence=dict(exec_result))


def run_improvement_backlog(
    goals: list,
    *,
    execute_fn: Callable[[object], dict],
    verify_fn: Callable[[object, dict], bool],
    rollback_fn: Callable[[object, dict], None],
    max_cycles: int = 5,
    approved_goal_ids: Optional[set] = None,
) -> list[CycleResult]:
    """Run cycles for the highest-priority goals (already ranked by ``goal_generator``), up to
    ``max_cycles``. Each cycle is independent and self-contained; a self-protected goal is approved only
    if its id is in ``approved_goal_ids``. Stops at ``max_cycles`` so an autonomous run is bounded."""
    approved = approved_goal_ids or set()
    results: list[CycleResult] = []
    for goal in list(goals)[: max(0, max_cycles)]:
        results.append(run_improvement_cycle(
            goal, execute_fn=execute_fn, verify_fn=verify_fn, rollback_fn=rollback_fn,
            approved=str(getattr(goal, "goal_id", "")) in approved))
    return results
