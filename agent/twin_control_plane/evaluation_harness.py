"""Real-LLM evaluation harness for Twin/Forge/Git usefulness (TFG evaluation).

Drives the REAL autonomous codegen stack (FastAPI app + the configured LLM) through a
matrix of conditions to measure the effect of the Twin Control Plane and git, separating
deterministic Twin mechanism effects from model output variance.

It is a measurement tool: it records outcomes honestly (accepted / needs_repair / blocked /
unavailable) and never fabricates success. It performs no remote git operation.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@contextmanager
def _env(overrides: dict[str, str | None]):
    """Temporarily set/clear environment variables, restoring them afterwards."""
    saved: dict[str, str | None] = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@dataclass
class EvalCondition:
    name: str
    env: dict[str, str | None] = field(default_factory=dict)
    profile_dims: dict[str, float] | None = None  # seed a Forge capability profile
    model_id: str = ""
    build_twin: bool = False  # enable ATLAS_TWIN_BUILD_PROJECT + run twice (re-run effect)


def seed_profile(root: Path, *, model_id: str, provider_id: str, dims: dict[str, float]) -> None:
    from agent.model_forge.profile_store import ProfileStore
    ProfileStore(Path(root) / "model_forge" / "profiles").record_observation(
        model_id=model_id, provider_id=provider_id, dimensions=dims, evidence_refs=["eval/seed"])


def prepare_pool(root: Path, *, pool_id: str, project_path: str, items: list[dict]) -> None:
    from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
    from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
    plan_items = [AtlasPlanItem(
        item_id=it["item_id"], pool_id=pool_id, title=it.get("title", it["item_id"]),
        goal=it["goal"], item_type="implementation", status="ready",
        risk_level=it.get("risk_level", "low"), target_files=it["target_files"],
        metadata={"action_type": it.get("action_type", "create")}) for it in items]
    pool = AtlasPlanPool(pool_id=pool_id, root_goal=items[0]["goal"] if items else "", project_path=project_path,
                         status="ready", automation_level="full_autopilot", items=plan_items)
    AtlasPlanPoolStorage(Path(root)).save_pool(pool)


def make_app(root: Path, adapter: Any):
    from app.server import create_app
    app = create_app()
    app.state.atlas_ca_data_root = str(root)
    app.state.atlas_llm_json_fn = adapter
    return app


def summarize_run(data: dict, project_path: str, target_files: list[str]) -> dict:
    """Extract the outcome + Twin evidence we measure from one /run response.

    Explicitly captures all four evaluated stages: patch generation, verification, Twin
    injection, and the repair/correction loop."""
    md = data.get("metadata") or {}
    tcp = md.get("twin_control_plane") or {}
    post = tcp.get("post_apply") or {}
    advisory = tcp.get("advisory_context") or {}
    impact = tcp.get("impact") or {}
    autopilot = data.get("autopilot_result") or {}
    item_results = autopilot.get("item_results") or []
    proposals = data.get("proposal_results") or []
    produced = [f for f in target_files if (Path(project_path) / f).exists()]

    def _item_md(it, key):
        return ((it.get("metadata") or {}).get(key) or {}).get("status")

    return {
        "status": data.get("status"),
        "stop_reason": data.get("stop_reason"),
        "changed_files": list(md.get("changed_files") or []),
        "produced_target_files": produced,
        "verification": autopilot.get("status"),
        # --- patch generation ---
        "generation": {
            "generated_count": data.get("generated_count"),
            "proposal_statuses": [p.get("status") for p in proposals],
            "patch_content_available": any(p.get("patch_content_available") for p in proposals),
        },
        # --- verification ---
        "verification_detail": {
            "item_statuses": [it.get("status") for it in item_results],
            "verification_statuses": [(it.get("verification_result") or {}).get("status") for it in item_results],
            "applied_no_verification_count": autopilot.get("applied_no_verification_count"),
        },
        # --- repair / correction loop ---
        "repair": {
            "post_apply_decision": post.get("decision"),
            "repair_compass_present": bool(post.get("repair_compass")),
            "repair_guidance_chars": len(post.get("repair_guidance") or ""),
            "bounded_retry": [_item_md(it, "bounded_retry_result") for it in item_results],
            "self_correction": [_item_md(it, "self_correction_result") for it in item_results],
            "twin_repair_attempts": md.get("twin_repair_attempts") or [],
        },
        # --- advisory Schema Guardian / StateMirror (measured, never blocks) ---
        "advisory_schema": post.get("advisory_schema") or {},
        "advisory_state": post.get("advisory_state") or {},
        "twin": {
            "mode": tcp.get("mode"),
            "engaged": tcp.get("engaged"),
            "gate_count": len(tcp.get("required_gates") or []),
            "required_gates": list(tcp.get("required_gates") or []),
            "twin_injection_level": tcp.get("twin_injection_level"),
            "compiled_instruction_present": bool(tcp.get("compiled_instruction")),
            "capability_profile_available": tcp.get("capability_profile_available"),
            "known_weaknesses": list(tcp.get("known_weaknesses") or []),
            "impact_available": bool(impact.get("available")),
            "post_apply_ran": bool(post.get("ran")),
            "post_apply_decision": post.get("decision"),
            "advisory_hint_count": int(advisory.get("hint_count") or 0),
        },
    }


def subprocess_validator(check_code: str, *, timeout: int = 60) -> Callable[[str], dict]:
    """Build a validator that runs ``check_code`` (a Python snippet) in the project dir.
    Returns ``{content_valid, detail}``; the snippet must exit 0 only when the generated
    code is functionally correct. Honestly records errors (e.g. import failure) as invalid."""
    def _validate(project_path: str) -> dict:
        import subprocess
        import sys
        try:
            proc = subprocess.run([sys.executable, "-c", check_code], cwd=project_path,
                                  capture_output=True, text=True, timeout=timeout)
            ok = proc.returncode == 0
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-1:] or [""]
            return {"content_valid": ok, "detail": tail[0][:200]}
        except Exception as exc:  # pragma: no cover - defensive
            return {"content_valid": False, "detail": f"validator_error:{type(exc).__name__}"}
    return _validate


def run_condition(
    *, adapter: Any, root: Path, condition: EvalCondition, pool_id: str,
    project_path: str, items: list[dict], request_metadata: dict | None = None,
    validator: Callable[[str], dict] | None = None,
) -> dict:
    """Execute one condition (twice when build_twin re-run), returning per-run records."""
    from fastapi.testclient import TestClient

    Path(project_path).mkdir(parents=True, exist_ok=True)
    if condition.profile_dims is not None and condition.model_id:
        seed_profile(root, model_id=condition.model_id, provider_id="local", dims=condition.profile_dims)
    prepare_pool(root, pool_id=pool_id, project_path=project_path, items=items)

    env = dict(condition.env)
    if condition.build_twin:
        env["ATLAS_TWIN_BUILD_PROJECT"] = "1"
    target_files = [f for it in items for f in it["target_files"]]
    req_md = dict(request_metadata or {})
    if condition.model_id:
        req_md["model_id"] = condition.model_id
        # Match seed_profile's provider so the capability profile is actually loaded.
        req_md["provider_id"] = "local"

    runs: list[dict] = []
    repeats = 2 if condition.build_twin else 1  # re-run pair to observe the Twin effect
    with _env(env):
        app = make_app(root, adapter)
        client = TestClient(app)
        for i in range(repeats):
            body = {"pool_id": pool_id, "project_path": project_path, "max_items": len(items),
                    "max_actions": max(3, len(items) + 2), "metadata": req_md}
            resp = client.post("/api/atlas/autonomous-codegen/run", json=body)
            data = resp.json() if resp.status_code == 200 else {"status": f"http_{resp.status_code}"}
            record = summarize_run(data, project_path, target_files)
            # Evaluate the VALIDITY of the generated content (functional correctness), not
            # just whether a file was produced.
            if validator is not None and record["produced_target_files"]:
                record["content"] = validator(project_path)
            else:
                record["content"] = {"content_valid": False,
                                     "detail": "no_target_file_produced" if validator else "no_validator"}
            runs.append(record)
            # Re-prepare the pool for the second pass (status reset to ready).
            if i + 1 < repeats:
                prepare_pool(root, pool_id=pool_id, project_path=project_path, items=items)
    return {"condition": condition.name, "runs": runs}


def build_report(project_name: str, condition_records: list[dict]) -> dict:
    """Aggregate per-condition records into a usefulness/variance summary."""
    by_name = {rec["condition"]: rec["runs"] for rec in condition_records}

    def first(name: str) -> dict:
        runs = by_name.get(name) or []
        return runs[0]["twin"] if runs else {}

    def statuses(name: str) -> list:
        return [r.get("status") for r in (by_name.get(name) or [])]

    all_runs = [r for rec in condition_records for r in rec["runs"]]

    def any_run(pred) -> bool:
        return any(pred(r) for r in all_runs)

    off, active = first("off"), first("active")
    summary = {
        # Confirms each evaluated pipeline stage was actually exercised across the matrix.
        "pipeline_coverage": {
            "generation_attempted": any_run(lambda r: bool(r.get("generation", {}).get("proposal_statuses"))),
            "generation_succeeded_at_least_once": any_run(
                lambda r: bool(r.get("generation", {}).get("patch_content_available"))),
            "verification_recorded": any_run(
                lambda r: bool(r.get("verification_detail", {}).get("item_statuses"))),
            "twin_instruction_injected": bool(active.get("compiled_instruction_present")),
            "post_apply_gate_ran": bool(active.get("post_apply_ran")),
            "repair_guidance_produced": any_run(lambda r: bool(r.get("repair", {}).get("repair_compass_present"))),
            "content_validity_checked": any_run(lambda r: "content" in r),
            "valid_content_produced_at_least_once": any_run(
                lambda r: bool(r.get("content", {}).get("content_valid"))),
            "advisory_schema_available": any_run(
                lambda r: bool(r.get("advisory_schema", {}).get("available"))),
            "advisory_state_available": any_run(
                lambda r: bool(r.get("advisory_state", {}).get("available"))),
            "advisory_state_recorded": any_run(lambda r: "advisory_state" in r),
            "twin_repair_loop_exercised": any_run(lambda r: bool(r.get("repair", {}).get("twin_repair_attempts"))),
        },
        # False-positive proxy: an advisory schema "would_block" on a content-valid run is a
        # candidate false positive (used to decide whether promotion to a blocking gate is safe).
        "advisory_schema_false_positive_candidates": sum(
            1 for r in all_runs
            if r.get("content", {}).get("content_valid")
            and r.get("advisory_schema", {}).get("would_block_if_promoted")),
        "content_validity": {
            name: {
                "valid": sum(1 for r in runs if r.get("content", {}).get("content_valid")),
                "total": len(runs),
                "details": [r.get("content", {}).get("detail") for r in runs],
            }
            for name, runs in by_name.items()
        },
        "twin_injection_verified": {
            "active_gates_present": active.get("gate_count", 0) > 0,
            "active_instruction_injected": bool(active.get("compiled_instruction_present")),
            "active_post_apply_ran": bool(active.get("post_apply_ran")),
            "off_no_instruction": not bool(off.get("compiled_instruction_present")),
            "off_not_engaged": off.get("engaged") in (False, None),
        },
        "active_vs_off": {
            "gate_count_delta": active.get("gate_count", 0) - off.get("gate_count", 0),
            "instruction_only_in_active": bool(active.get("compiled_instruction_present"))
            and not bool(off.get("compiled_instruction_present")),
        },
        "profile_effect": {
            "weak_gate_count": first("active_weak_profile").get("gate_count"),
            "strong_gate_count": first("active_strong_profile").get("gate_count"),
            "weak_weaknesses": first("active_weak_profile").get("known_weaknesses"),
        },
        "rerun_twin_effect": {},
        "variance": {name: {"statuses": statuses(name),
                            "stable": len(set(statuses(name))) <= 1}
                     for name in by_name},
    }
    rerun_runs = by_name.get("active_build_twin") or []
    if len(rerun_runs) >= 2:
        summary["rerun_twin_effect"] = {
            "run1_impact_available": rerun_runs[0]["twin"].get("impact_available"),
            "run2_impact_available": rerun_runs[1]["twin"].get("impact_available"),
            "impact_became_available_on_rerun": (not rerun_runs[0]["twin"].get("impact_available"))
            and bool(rerun_runs[1]["twin"].get("impact_available")),
        }
    return {"project": project_name, "conditions": condition_records, "summary": summary}


def default_conditions(model_id: str) -> list[EvalCondition]:
    """The comprehensive evaluation matrix."""
    return [
        EvalCondition("off", env={"ATLAS_TWIN_PIPELINE_MODE": "off"}),
        EvalCondition("active", env={"ATLAS_TWIN_PIPELINE_MODE": "active"}),
        EvalCondition("active", env={"ATLAS_TWIN_PIPELINE_MODE": "active"}),  # repeat for variance
        EvalCondition("active_weak_profile", env={"ATLAS_TWIN_PIPELINE_MODE": "active"},
                      profile_dims={"flag_reasoning": 0.2, "impact_analysis": 0.2,
                                    "contract_preservation": 0.2, "test_generation": 0.2}, model_id=model_id),
        EvalCondition("active_strong_profile", env={"ATLAS_TWIN_PIPELINE_MODE": "active"},
                      profile_dims={d: 0.9 for d in ("flag_reasoning", "impact_analysis",
                                    "contract_preservation", "test_generation")}, model_id=model_id),
        EvalCondition("active_build_twin", env={"ATLAS_TWIN_PIPELINE_MODE": "active"}, build_twin=True),
    ]


__all__ = [
    "EvalCondition", "seed_profile", "prepare_pool", "make_app", "summarize_run",
    "run_condition", "build_report", "default_conditions",
]
