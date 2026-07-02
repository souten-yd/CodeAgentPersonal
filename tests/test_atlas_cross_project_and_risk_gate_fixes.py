"""Regression tests for the 2026-07 fixes to cross-project plan bleed and over-strict risk gating.

See memory `atlas-cross-project-plan-bleed-and-risk-gate-fixes`. Covers:
- Nexus past-plan/past-requirement context is scoped to the CURRENT project (a different project's
  plan must not bleed into a new project's planning context).
- The plan quality gate does not escalate a pure quality/logic critique to a critical SAFETY event
  when the plan is confined to the sandbox (frontend, non-executable) — but still does for
  executable scope or genuine safety-keyword findings.
- The clarification-time safety-gate rerun resolves a full-auto-capable UI preset to the matching
  policy preset instead of falling back to the strictest low-only preset.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_clarification_replanning_service import AtlasClarificationReplanningService
from agent.atlas_plan_quality_gate import apply_plan_quality_gate
from agent.nexus_context_builder import NexusContextBuilder


# ── ③ Nexus scoping ──────────────────────────────────────────────────────────

def _write_requirement(root: Path, rid: str, project_path: str, goal: str) -> None:
    (root / "requirements").mkdir(parents=True, exist_ok=True)
    (root / "requirements" / f"{rid}.json").write_text(
        json.dumps({
            "requirement_id": rid,
            "project_path": project_path,
            "resolved_project_path": project_path,
            "user_input": goal,
            "interpreted_goal": goal,
            "functional_requirements": [goal],
        }),
        encoding="utf-8",
    )


def _write_plan(root: Path, pid: str, rid: str, goal: str) -> None:
    (root / "plans").mkdir(parents=True, exist_ok=True)
    (root / "plans" / f"{pid}.plan.json").write_text(
        json.dumps({
            "plan_id": pid,
            "requirement_id": rid,  # plan carries no project_path; resolved via the requirement
            "user_goal": goal,
            "implementation_steps": [goal],
        }),
        encoding="utf-8",
    )


def test_past_artifacts_are_scoped_to_current_project(tmp_path: Path) -> None:
    proj_a = str(tmp_path / "proj_a" / "work")
    proj_b = str(tmp_path / "proj_b" / "work")
    _write_requirement(tmp_path, "req_a", proj_a, "Build a Rubik's cube in HTML with drag rotate")
    _write_plan(tmp_path, "plan_a", "req_a", "Build a Rubik's cube in HTML")
    _write_requirement(tmp_path, "req_b", proj_b, "Build a retro first-person shooter in a space station")
    _write_plan(tmp_path, "plan_b", "req_b", "Build a retro first-person shooter FPS")

    builder = NexusContextBuilder(ca_data_dir=str(tmp_path))
    key_a = builder._normalize_project_key(proj_a)

    reqs = builder._collect_past_requirements(query_terms=["html"], warnings=[], current_project_key=key_a)
    plans = builder._collect_past_plans(query_terms=["html"], warnings=[], current_project_key=key_a)

    req_text = " ".join(item.content for item in reqs)
    plan_text = " ".join(item.content for item in plans)
    # Only project A's Rubik artifacts are visible; project B's FPS plan is excluded.
    assert "Rubik" in req_text and "Rubik" in plan_text
    assert "first-person shooter" not in req_text
    assert "first-person shooter" not in plan_text


def test_unscoped_collection_preserves_legacy_behavior(tmp_path: Path) -> None:
    _write_requirement(tmp_path, "req_a", str(tmp_path / "a"), "goal A")
    _write_requirement(tmp_path, "req_b", str(tmp_path / "b"), "goal B")
    builder = NexusContextBuilder(ca_data_dir=str(tmp_path))
    # No current project key -> unscoped (both projects' requirements available).
    reqs = builder._collect_past_requirements(query_terms=["goal"], warnings=[], current_project_key="")
    assert len(reqs) == 2


# ── ⑤ Plan quality gate: sandbox scope must not force a critical safety event ─────

def _critique_plan(findings, steps):
    return {
        "requirement_summary": "interactive 3D rubik cube",
        "goal": "rubik cube",
        "implementation_steps": steps,
        "adversarial_critique": {"findings": findings, "consensus_risk": "critical", "requires_revision": True},
    }


def _finding(severity, title, category="other", detail=""):
    return {"angle": "", "severity": severity, "category": category, "title": title, "detail": detail, "recommendation": ""}


def test_sandbox_frontend_critical_quality_finding_not_safety_escalated() -> None:
    out = apply_plan_quality_gate(
        _critique_plan(
            [_finding("critical", "Logical Contradiction: solved vs scramble", category="correctness")],
            [{"title": "cube", "description": "render", "acceptance_criteria": ["ok"], "action_type": "update", "target_files": ["index.html"]}],
        ),
        preset_id="autonomous_bounded_dev",
        critical_handling="ask",
    )
    assert out.get("critical_event") is None
    assert out["critique_gate"]["gate_status"] == "full_auto_continued"
    assert out["require_approval"] is False


def test_executable_scope_still_escalates_critical_finding() -> None:
    out = apply_plan_quality_gate(
        _critique_plan(
            [_finding("critical", "Logical Contradiction", category="correctness")],
            [{"title": "srv", "description": "d", "acceptance_criteria": ["ok"], "action_type": "update", "target_files": ["server.py"]}],
        ),
        preset_id="autonomous_bounded_dev",
        critical_handling="ask",
    )
    assert out["critique_gate"]["gate_status"] == "waiting_for_critical_decision"
    assert out.get("critical_event") is not None


def test_safety_keyword_finding_escalates_even_on_frontend_scope() -> None:
    out = apply_plan_quality_gate(
        _critique_plan(
            [_finding("high", "auth token leak", category="security", detail="credential exposure")],
            [{"title": "cube", "description": "d", "acceptance_criteria": ["ok"], "action_type": "update", "target_files": ["index.html"]}],
        ),
        preset_id="autonomous_bounded_dev",
        critical_handling="ask",
    )
    assert out["critique_gate"]["gate_status"] == "waiting_for_critical_decision"
    assert out["critique_gate"]["safety_sensitive"] is True


# ── ⑥ Clarification-time safety-gate rerun resolves the full-auto UI preset ───────

def _pool_with_item(risk: str) -> tuple[AtlasPlanPool, AtlasPlanItem]:
    item = AtlasPlanItem(
        item_id="item_1", pool_id="pool_x", title="Create index.html", goal="build",
        item_type="implementation", status="ready", risk_level=risk,
        target_files=["index.html"], metadata={"action_type": "create"},
    )
    pool = AtlasPlanPool(pool_id="pool_x", root_goal="rubik cube", project_path="/tmp/work",
                         status="approval_required", items=[item], metadata={})
    return pool, item


def test_rerun_safety_gate_maps_full_auto_preset_and_allows_high_risk() -> None:
    pool, item = _pool_with_item("high")
    gate = AtlasClarificationReplanningService._rerun_safety_gate(pool, item, "autonomous_bounded_dev")
    # A full-auto-capable preset must not hard-block a high-risk sandbox item at plan time.
    assert gate["decision"] == "allow"
    assert "risk_not_allowed" not in gate.get("reasons", [])
    assert "patch_proposal_approval_missing" not in gate.get("reasons", [])


def test_rerun_safety_gate_keeps_low_only_preset_strict() -> None:
    pool, item = _pool_with_item("high")
    gate = AtlasClarificationReplanningService._rerun_safety_gate(pool, item, "guarded_low_risk")
    # A genuinely low-only preset still blocks a high-risk item (unchanged behavior).
    assert gate["decision"] != "allow"
    assert "risk_not_allowed" in gate.get("reasons", [])
