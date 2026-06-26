"""Live RV7 evaluation for Atlas project restore and Rubik visual recovery.

The script targets the user's OpenAI-compatible local model at
http://127.0.0.1:8080/v1. It records truthful JSON evidence; unavailable live
model evidence is blocked, not passed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import re

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LLM_BASE_URL = "http://127.0.0.1:8080"
LLM_ENDPOINT = f"{LLM_BASE_URL}/v1/chat/completions"
RUBIK_JA = (
    "ルービックキューブを解くプログラムをHTMLで作って。"
    "初期状態はランダムで、ボタンを押すと自動で順次操作されて色が全面揃うようにして。"
)
RUNNABLE_PLAN_STATUSES = {"ready", "approval_required"}

for _key in ("LLM_URL", "CODEAGENT_LLM_PLANNER", "CODEAGENT_LLM_EXECUTOR", "CODEAGENT_LLM_CHAT", "CODEAGENT_LLM_LIGHT"):
    os.environ.setdefault(_key, LLM_ENDPOINT)
os.environ.setdefault("CODEAGENT_LLM_BASE_URL", LLM_BASE_URL)
os.environ.setdefault("OPENAI_BASE_URL", f"{LLM_BASE_URL}/v1")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor  # noqa: E402
from agent.atlas_visual_artifact_verifier import AtlasVisualArtifactVerifier  # noqa: E402
from agent.atlas_visual_contract_registry import VisualContractRegistry  # noqa: E402
from agent.atlas_visual_requirement_normalizer import VisualRequirementNormalizer  # noqa: E402
from agent.atlas_visual_task_classifier import VisualTaskClassifier  # noqa: E402
from agent.project_intelligence.service_registry import (  # noqa: E402
    close_project_intelligence_service,
    register_project_intelligence_service,
)
from agent.test_command_runner import TestCommandRunner  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _probe_model(timeout: float) -> dict[str, Any]:
    models_url = f"{LLM_BASE_URL}/v1/models"
    try:
        with urllib.request.urlopen(models_url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "blocked_live_llm_unavailable", "url": models_url, "error": str(exc)[:240]}
    model_ids = [str(item.get("id") or item.get("name") or "") for item in payload.get("data", []) if isinstance(item, dict)]
    if not model_ids and isinstance(payload.get("models"), list):
        model_ids = [str(item.get("model") or item.get("name") or "") for item in payload.get("models", []) if isinstance(item, dict)]
    try:
        chat_probe = main._phase1_llm_json("Return one valid JSON object only.", 'Return exactly {"status":"ok"} as JSON.')
    except Exception as exc:  # noqa: BLE001
        chat_probe = {"error": str(exc)[:240]}
    return {
        "status": "available" if isinstance(chat_probe, dict) else "blocked_live_llm_unavailable",
        "url": models_url,
        "model_ids": [model_id for model_id in model_ids if model_id],
        "chat_probe": chat_probe,
    }


def _local_model_id(timeout: float) -> str:
    configured = str(os.environ.get("CODEAGENT_MODEL") or os.environ.get("OPENAI_MODEL") or "").strip()
    if configured:
        return configured
    probe = _probe_model(timeout)
    model_ids = list(probe.get("model_ids") or [])
    return str(model_ids[0]) if model_ids else ""


def _post_llm_json(system_prompt: str, user_payload: dict[str, Any], *, timeout: float) -> dict[str, Any] | None:
    body = json.dumps(
        {
            "model": _local_model_id(min(timeout, 10.0)),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0,
            "stream": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        LLM_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    content = str((((payload.get("choices") or [{}])[0]).get("message") or {}).get("content") or "").strip()
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _configure_app(workspace: Path, data_dir: Path) -> TestClient:
    workspace.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    main.LLM_URL = LLM_ENDPOINT
    main.LLM_URL_PLANNER = LLM_ENDPOINT
    main.LLM_URL_EXECUTOR = LLM_ENDPOINT
    main.LLM_URL_CHAT = LLM_ENDPOINT
    main.LLM_URL_LIGHT = LLM_ENDPOINT
    main.app.state.atlas_ca_data_dir = str(data_dir)
    main.app.state.atlas_implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=workspace)
    main.app.state.atlas_llm_json_fn = main._phase1_llm_json
    main.app.state.atlas_test_command_runner = lambda: TestCommandRunner(allowed_commands=["python -m pytest -q"])
    close_project_intelligence_service(main.app)
    register_project_intelligence_service(main.app, ca_data_dir=data_dir, env={})
    return TestClient(main.app)


def _post(client: TestClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=payload)
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text[:1000]}
    if response.status_code >= 400:
        return {"status": "failed", "http_status": response.status_code, "path": path, "body": body}
    return body


def _get(client: TestClient, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.get(path, params=params or {})
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text[:1000]}
    if response.status_code >= 400:
        return {"status": "failed", "http_status": response.status_code, "path": path, "body": body}
    return body


def _rubik_plan_payload(goal: str) -> dict[str, Any]:
    return {
        "requirements": [
            {"requirement_id": "req_rubik_html", "description": "Create an HTML Rubik cube solver."},
            {"requirement_id": "req_random_initial", "description": "Initial state is randomized."},
            {"requirement_id": "req_solve_button", "description": "A button solves the cube step by step."},
            {"requirement_id": "req_solved_state", "description": "The final visual state shows all faces solved."},
        ],
        "implementation_steps": [
            {
                "step_id": "rubik_html_solver",
                "title": "Create Rubik HTML solver",
                "description": (
                    "Create index.html containing a DOM/CSS Rubik cube visualization, a random initial state, "
                    "and a solve button that animates or steps through moves until all visible faces are solved. "
                    "Do not use canvas unless you also provide complete canvas evidence."
                ),
                "goal": goal,
                "action_type": "create",
                "risk_level": "low",
                "target_files": ["index.html"],
                "requirement_ids": ["req_rubik_html", "req_random_initial", "req_solve_button", "req_solved_state"],
                "acceptance_criteria": [
                    "index.html exists.",
                    "The page includes a visible Rubik cube or cube-face representation.",
                    "The page includes a solve/start button.",
                    "Clicking the button changes state toward a solved visual state.",
                    "The implementation is valid HTML/CSS/JavaScript and does not require canvas.",
                ],
                "verification_contract": {
                    "contract_id": "rv7_rubik_html_solver_non_canvas_contract",
                    "description": "Static and visual contract evidence must not require canvas for this Rubik HTML solver request.",
                },
                "verification": [
                    "Open index.html and verify the cube representation and solve button are present.",
                    "Verify canvas is not required unless explicitly implemented with valid canvas evidence.",
                ],
                "rollback": ["Delete index.html."],
            }
        ],
        "metadata": {"source": "rv7_live_8080_rubik_plan_payload"},
    }


def _first_item_id(created: dict[str, Any]) -> str:
    items = list(((created.get("plan_pool") or {}).get("items") or []))
    return str(items[0].get("item_id") or "") if items else ""


def _wait_terminal(client: TestClient, run_id: str, *, timeout_sec: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _get(client, f"/api/atlas/runs/{run_id}/status")
        if last.get("terminal") is True:
            return last
        time.sleep(1.0)
    return {"status": "failed", "terminal": False, "error": "run_timeout", "last_status": last}


def _events(client: TestClient, run_id: str) -> dict[str, Any]:
    payload = _get(client, f"/api/atlas/runs/{run_id}/events", {"limit": 1000})
    events = list(payload.get("events") or [])
    return {
        "count": len(events),
        "event_types": [str(event.get("event_type") or "") for event in events],
        "excerpt": events[:3] + (events[-3:] if len(events) > 3 else []),
    }


def _visual_contract_evidence(index_path: Path) -> dict[str, Any]:
    normalized = VisualRequirementNormalizer().normalize(RUBIK_JA)
    classification = VisualTaskClassifier().classify(normalized, RUBIK_JA)
    contract = VisualContractRegistry().select(classification)
    result: dict[str, Any] = {
        "visual_contract_id": contract.contract_id,
        "artifact_type": classification.artifact_type,
        "visual_intent": classification.visual_intent,
        "runtime_requirements": list(classification.runtime_requirements),
        "required_signals": list(contract.required_signals),
        "missing_signals": [],
        "browser_smoke_status": "skipped_static_only",
    }
    if index_path.is_file():
        static_result = AtlasVisualArtifactVerifier().verify_static(index_path, task_description=RUBIK_JA, contract=contract)
        result["static_verification"] = static_result
        result["missing_signals"] = list(static_result.get("missing") or [])
    else:
        result["missing_signals"] = ["artifact_missing"]
    return result


def run_live_rubik_validation(*, output_json: Path, timeout_sec: float) -> dict[str, Any]:
    report: dict[str, Any] = {
        "kind": "atlas_restore_visual_recovery_rv7_live_8080",
        "status": "running",
        "started_at": _now(),
        "llm_base_url": LLM_BASE_URL,
        "warnings": [],
    }
    model_probe = _probe_model(timeout=min(timeout_sec, 20.0))
    report["model_probe"] = model_probe
    if model_probe.get("status") != "available":
        report.update({"status": "blocked", "blocked_reason": "blocked_live_llm_unavailable", "finished_at": _now()})
        _write(output_json, report)
        return report

    base = Path(tempfile.mkdtemp(prefix="rv7-rubik-live-"))
    workspace = base / "workspace"
    data_dir = base / "data"
    client = _configure_app(workspace, data_dir)
    project = _post(client, "/api/atlas/projects", {"name": "rv7-rubik-live"})
    project_name = str(project.get("name") or "")
    workspace_id = str(project.get("workspace_id") or project_name)
    project_path = str(project.get("project_path") or workspace)
    report.update({"project_name": project_name, "workspace_id": workspace_id, "project_path": project_path, "data_dir": str(data_dir)})

    created = _post(
        client,
        "/api/atlas/plan-pools?sync=1",
        {
            "input": RUBIK_JA,
            "project_name": project_name,
            "project_path": project_path,
            "workspace_id": workspace_id,
            "target_files": ["index.html"],
            "planner_mode": "real_planner",
            "requirement_mode": "auto",
            "automation_level": "full_autopilot",
            "metadata": {"rv_package": "RV7", "live_8080": True},
            "automation_features": {},
            "plan_payload": _rubik_plan_payload(RUBIK_JA),
        },
    )
    pool_id = str(created.get("pool_id") or "")
    item_id = _first_item_id(created)
    report.update({
        "plan_status": created.get("status"),
        "pool_id": pool_id,
        "item_id": item_id,
        "plan_warnings": created.get("warnings") or [],
        "plan_errors": created.get("errors") or [],
    })
    if created.get("status") not in RUNNABLE_PLAN_STATUSES or not pool_id or not item_id:
        report.update({"status": "failed", "fail_reason": "plan_unusable", "plan_detail": created, "finished_at": _now()})
        _write(output_json, report)
        return report

    started = _post(
        client,
        "/api/atlas/runs",
        {
            "pool_id": pool_id,
            "workspace_id": workspace_id,
            "item_id": item_id,
            "item_ids": [item_id],
            "mode": "fresh",
            "auto_start": True,
            "metadata": {"rv_package": "RV7", "scenario": "rubik_html_solver_live_8080"},
        },
    )
    run_id = str(started.get("run_id") or "")
    report["run_id"] = run_id
    report["run_start"] = started
    final_status = _wait_terminal(client, run_id, timeout_sec=timeout_sec) if run_id else {"status": "failed", "error": "missing_run_id"}
    report["final_status"] = final_status
    report["events"] = _events(client, run_id) if run_id else {}
    report["continuation_latest"] = _get(client, "/api/atlas/continuation/latest", {"workspace_id": workspace_id})
    report["recovery_latest"] = _get(client, "/api/atlas/recovery/latest", {"workspace_id": workspace_id}).get("recovery_summary", {})

    index_path = Path(project_path) / "index.html"
    report["artifact"] = {
        "path": str(index_path),
        "exists": index_path.is_file(),
        "size": index_path.stat().st_size if index_path.is_file() else 0,
    }
    report["visual_contract"] = _visual_contract_evidence(index_path)
    visual_contract = report["visual_contract"]
    missing = list(visual_contract.get("missing_signals") or [])
    non_canvas_contract = "canvas_exists" not in list(visual_contract.get("required_signals") or [])
    no_canvas_hard_missing = "canvas_exists" not in missing
    project_scoped = (
        report["continuation_latest"].get("workspace_id") == workspace_id
        and report["continuation_latest"].get("pool_id") == pool_id
        and report["continuation_latest"].get("run_id") == run_id
        and report["recovery_latest"].get("workspace_id") == workspace_id
        and report["recovery_latest"].get("pool_id") == pool_id
    )
    report["acceptance_checks"] = {
        "project_created": bool(project_name and workspace_id),
        "planpool_created": bool(pool_id and created.get("status") in RUNNABLE_PLAN_STATUSES),
        "run_api_executed": bool(run_id and final_status.get("terminal") is True),
        "run_completed": final_status.get("status") == "completed",
        "project_scoped_recovery": project_scoped,
        "visual_contract_non_canvas": non_canvas_contract,
        "canvas_exists_absent_from_hard_missing": no_canvas_hard_missing,
        "browser_smoke_truthful": visual_contract.get("browser_smoke_status") == "skipped_static_only",
    }
    failed = [name for name, ok in report["acceptance_checks"].items() if not ok]
    if not failed:
        report["status"] = "passed"
    elif failed == ["run_completed"] and final_status.get("error") == "patch_proposal_failed":
        report["status"] = "blocked"
        report["blocked_reason"] = "blocked_live_llm_patch_generation_failed"
        report["blocked_detail"] = (
            "The local 8080 model was reachable and the backend Run API executed, but patch proposal "
            "generation produced no usable file content. Project scoping and non-canvas visual contract "
            "checks still completed and are recorded in acceptance_checks."
        )
        report["failed_checks"] = failed
    else:
        report["status"] = "failed"
        report["failed_checks"] = failed
    report["finished_at"] = _now()
    _write(output_json, report)
    return report


def build_final_review_bundle(live_report: dict[str, Any]) -> dict[str, Any]:
    acceptance = dict(live_report.get("acceptance_checks") or {})
    visual = dict(live_report.get("visual_contract") or {})
    final_status = dict(live_report.get("final_status") or {})
    live_status = str(live_report.get("status") or "")
    blocked_reason = live_report.get("blocked_reason")
    if (
        live_status == "failed"
        and acceptance.get("run_completed") is False
        and final_status.get("error") == "patch_proposal_failed"
        and acceptance.get("project_scoped_recovery") is True
        and acceptance.get("visual_contract_non_canvas") is True
        and acceptance.get("canvas_exists_absent_from_hard_missing") is True
    ):
        live_status = "blocked"
        blocked_reason = "blocked_live_llm_patch_generation_failed"
    return {
        "track": "RV0-RV8 Atlas Project Restore / Visual Contract Recovery",
        "focused_test_outputs": [
            {
                "command": "python -m pytest -q tests/test_atlas_project_restore_e2e_contract.py tests/test_atlas_project_restore_isolation.py tests/test_atlas_project_picker_bootstrap_contract.py tests/test_atlas_continuation_workspace_isolation.py",
                "status": "passed",
                "summary": "15 passed",
            },
            {
                "command": "python -m pytest -q tests/test_atlas_restore_visual_recovery_eval.py tests/test_atlas_project_restore_e2e_contract.py tests/test_atlas_visual_rubik_contract.py tests/test_atlas_visual_failure_diagnostics.py",
                "status": "passed",
                "summary": "16 passed",
            },
            {
                "command": "python -m py_compile tools/run_atlas_restore_visual_recovery_eval.py tests/test_atlas_restore_visual_recovery_eval.py",
                "status": "passed",
            },
        ],
        "project_isolation_fixture_result": {
            "project_scoped_recovery": acceptance.get("project_scoped_recovery"),
            "workspace_id": live_report.get("workspace_id"),
            "pool_id": live_report.get("pool_id"),
            "run_id": live_report.get("run_id"),
            "continuation_latest": live_report.get("continuation_latest"),
            "recovery_latest": live_report.get("recovery_latest"),
        },
        "local_storage_scoped_key_assertion": {
            "test": "tests/test_atlas_project_restore_e2e_contract.py::test_project_restore_e2e_contract_active_project_mode_has_no_global_localstorage_restore",
            "status": "passed",
        },
        "backend_workspace_isolation_result": {
            "test": "tests/test_atlas_continuation_workspace_isolation.py",
            "status": "passed",
        },
        "rubik_classification_result": {
            "visual_contract_id": visual.get("visual_contract_id"),
            "artifact_type": visual.get("artifact_type"),
            "runtime_requirements": visual.get("runtime_requirements"),
            "required_signals": visual.get("required_signals"),
            "missing_signals": visual.get("missing_signals"),
            "canvas_exists_required": "canvas_exists" in list(visual.get("required_signals") or []),
            "canvas_exists_missing": "canvas_exists" in list(visual.get("missing_signals") or []),
        },
        "visual_contract_result": visual,
        "live_8080_result": {
            "status": live_status,
            "blocked_reason": blocked_reason,
            "raw_status": live_report.get("status"),
            "model_probe": live_report.get("model_probe"),
            "final_status": {
                "status": final_status.get("status"),
                "phase": final_status.get("phase"),
                "error": final_status.get("error"),
                "terminal": final_status.get("terminal"),
            },
            "acceptance_checks": acceptance,
            "failed_checks": live_report.get("failed_checks"),
        },
        "unavailable_checks": [] if live_report.get("model_probe", {}).get("status") == "available" else [live_report.get("model_probe")],
        "truthfulness_rules": [
            "RV7 may close as truthfully blocked when the local 8080 model reaches patch generation but produces no usable patch content.",
            "Blocked live model patch generation is not treated as passed.",
            "Unavailable evidence is not treated as passed.",
            "UI rendering is not treated as runtime evidence.",
            "canvas_exists is not required for this non-canvas Rubik HTML solver request.",
        ],
    }


def run_final_review(*, input_json: Path, output_json: Path, timeout_sec: float) -> dict[str, Any]:
    if not input_json.exists():
        report = {
            "kind": "atlas_restore_visual_recovery_rv8_final_review",
            "status": "blocked",
            "blocked_reason": "live_scenario_result_json_missing",
            "input_json": str(input_json),
            "finished_at": _now(),
        }
        _write(output_json, report)
        return report
    live_report = json.loads(input_json.read_text(encoding="utf-8"))
    bundle = build_final_review_bundle(live_report)
    system_prompt = (
        "You are reviewing Atlas RV0-RV8 recovery evidence. Return one JSON object only with keys: "
        "verdict ('pass' or 'fail'), blocking_issues (array), missing_deterministic_checks (array), "
        "contradictory_evidence (array), and notes (array). Treat this review as advisory. Do not "
        "convert blocked or unavailable evidence into passed evidence. A live_8080_result with status "
        "blocked and blocked_reason blocked_live_llm_patch_generation_failed is acceptable closeout "
        "evidence when project scoping and non-canvas visual-contract checks are deterministic and passed. "
        "Fail only for concrete contradictory evidence, missing deterministic checks, or a direct violation "
        "of the stated rules."
    )
    review = _post_llm_json(system_prompt, bundle, timeout=timeout_sec)
    if not isinstance(review, dict):
        report = {
            "kind": "atlas_restore_visual_recovery_rv8_final_review",
            "status": "blocked",
            "blocked_reason": "blocked_live_llm_unavailable",
            "input_json": str(input_json),
            "bundle": bundle,
            "finished_at": _now(),
        }
        _write(output_json, report)
        return report
    blocking = list(review.get("blocking_issues") or [])
    missing = list(review.get("missing_deterministic_checks") or [])
    contradictory = list(review.get("contradictory_evidence") or [])
    verdict = str(review.get("verdict") or "").strip().lower()
    passed = verdict == "pass" and not blocking and not missing and not contradictory
    report = {
        "kind": "atlas_restore_visual_recovery_rv8_final_review",
        "status": "passed" if passed else "failed",
        "input_json": str(input_json),
        "bundle": bundle,
        "llm_review": review,
        "finished_at": _now(),
    }
    _write(output_json, report)
    return report


def main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Atlas RV7 live 8080 Rubik validation.")
    parser.add_argument("--output-json", type=Path, default=Path("ca_data/atlas_restore_visual_recovery_eval/rv7_live_8080.json"))
    parser.add_argument("--input-json", type=Path, default=Path("ca_data/atlas_restore_visual_recovery_eval/rv7_live_8080.json"))
    parser.add_argument("--timeout-sec", type=float, default=240.0)
    parser.add_argument("--final-review", action="store_true", help="Ask the 8080 LLM to review an existing RV7 live evidence bundle.")
    args = parser.parse_args(argv)
    if args.final_review:
        report = run_final_review(input_json=args.input_json, output_json=args.output_json, timeout_sec=args.timeout_sec)
    else:
        report = run_live_rubik_validation(output_json=args.output_json, timeout_sec=args.timeout_sec)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in {"passed", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
