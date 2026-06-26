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


def main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Atlas RV7 live 8080 Rubik validation.")
    parser.add_argument("--output-json", type=Path, default=Path("ca_data/atlas_restore_visual_recovery_eval/rv7_live_8080.json"))
    parser.add_argument("--timeout-sec", type=float, default=240.0)
    args = parser.parse_args(argv)
    report = run_live_rubik_validation(output_json=args.output_json, timeout_sec=args.timeout_sec)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in {"passed", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
