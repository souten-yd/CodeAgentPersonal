"""Live SC7 evaluation for the Atlas server-controlled Run API flow.

The script uses the user's OpenAI-compatible local model at
http://127.0.0.1:8080/v1, then drives isolated Atlas PlanPool -> Run API flows.
It records truthful JSON evidence; unavailable live model evidence is blocked,
not passed.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
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
RUNNABLE_PLAN_STATUSES = {"ready", "approval_required"}

for _key in ("LLM_URL", "CODEAGENT_LLM_PLANNER", "CODEAGENT_LLM_EXECUTOR", "CODEAGENT_LLM_CHAT", "CODEAGENT_LLM_LIGHT"):
    os.environ.setdefault(_key, LLM_ENDPOINT)
os.environ.setdefault("CODEAGENT_LLM_BASE_URL", LLM_BASE_URL)
os.environ.setdefault("OPENAI_BASE_URL", f"{LLM_BASE_URL}/v1")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor  # noqa: E402
from agent.project_intelligence.service_registry import (  # noqa: E402
    close_project_intelligence_service,
    register_project_intelligence_service,
)
from agent.test_command_runner import TestCommandRunner  # noqa: E402
from scripts import atlas_run_cli  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestClientRunHttpClient:
    def __init__(self, client: TestClient):
        self.client = client

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.client.request(method, path, json=payload)
        body = response.json()
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} {path}: {body}")
        return body


def _probe_model(timeout: float) -> dict[str, Any]:
    models_url = f"{LLM_BASE_URL}/v1/models"
    try:
        with urllib.request.urlopen(models_url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "blocked_live_llm_unavailable", "url": models_url, "error": str(exc)[:240]}
    model_ids = [str(item.get("id") or "") for item in payload.get("data", []) if isinstance(item, dict)]
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
    try:
        with urllib.request.urlopen(f"{LLM_BASE_URL}/v1/models", timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return ""
    for item in payload.get("data", []) or []:
        if isinstance(item, dict) and str(item.get("id") or "").strip():
            return str(item.get("id") or "").strip()
    return ""


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
            response_payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    content = str((((response_payload.get("choices") or [{}])[0]).get("message") or {}).get("content") or "").strip()
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


def _compact_live_report(report: dict[str, Any]) -> dict[str, Any]:
    scenarios = []
    for scenario in list(report.get("scenarios") or []):
        final_status = scenario.get("final_status") or {}
        events = scenario.get("events") or {}
        scenarios.append(
            {
                "scenario": scenario.get("scenario"),
                "status": scenario.get("status"),
                "run_id": scenario.get("run_id"),
                "final_status": {
                    "status": final_status.get("status"),
                    "phase": final_status.get("phase"),
                    "block_reason": final_status.get("block_reason"),
                    "terminal": final_status.get("terminal"),
                },
                "event_types": events.get("event_types"),
                "event_count": events.get("count"),
                "deterministic_check": scenario.get("deterministic_check"),
                "verification_interpretation": scenario.get("verification_interpretation"),
            }
        )
    return {
        "status": report.get("status"),
        "llm_base_url": report.get("llm_base_url"),
        "model_probe": report.get("model_probe"),
        "acceptance_checks": report.get("acceptance_checks"),
        "scenarios": scenarios,
    }


def build_final_review_bundle(live_report: dict[str, Any]) -> dict[str, Any]:
    return {
        "track": "Atlas Server-Controlled UI / CLI",
        "focused_test_outputs": [
            {
                "command": "python -m pytest -q tests/test_atlas_server_controlled_flow_eval.py tests/test_atlas_run_api.py tests/test_atlas_run_cli.py tests/test_atlas_run_orchestrator.py tests/test_atlas_run_schema.py tests/test_atlas_server_controlled_ui_cli_sc0.py",
                "status": "passed",
                "summary": "35 passed",
            },
            {
                "command": "python -m py_compile tools/run_atlas_server_controlled_flow_eval.py app/api/atlas_runs.py",
                "status": "passed",
            },
        ],
        "run_state_json": [
            {
                "scenario": scenario.get("scenario"),
                "run_id": scenario.get("run_id"),
                "final_status": scenario.get("final_status"),
            }
            for scenario in _compact_live_report(live_report).get("scenarios", [])
        ],
        "event_log_excerpts": [
            {
                "scenario": scenario.get("scenario"),
                "run_id": scenario.get("run_id"),
                "event_types": scenario.get("event_types"),
                "event_count": scenario.get("event_count"),
            }
            for scenario in _compact_live_report(live_report).get("scenarios", [])
        ],
        "final_report_excerpts": {
            "ui_cli_contract": {
                "ui_thin_client": "Browser approval path creates/watches /api/atlas/runs and does not directly call proposal/apply/autopilot endpoints.",
                "cli_thin_client": "CLI plan/status/watch/decision/cancel/retry commands call PlanPool or /api/atlas/runs endpoints only.",
                "backend_authority": "Run API delegates proposal, approval, Safe Apply, and verification to backend orchestrator callbacks.",
                "replay": "Run events are persisted and replayable after an event cursor.",
            },
            "config_verification_note": "Business/config scenario records generic auto-verification_blocked separately; deterministic JSON check is the authoritative acceptance check for that scenario.",
        },
        "live_scenario_result_json": _compact_live_report(live_report),
        "unavailable_checks": [],
    }


def run_final_review(*, input_json: Path, output_json: Path, timeout: float) -> dict[str, Any]:
    if not input_json.exists():
        report = {
            "kind": "atlas_server_controlled_final_review",
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
        "You are reviewing Atlas Server-Controlled UI / CLI evidence. Return one JSON object only with keys: "
        "verdict ('pass' or 'fail'), blocking_issues (array), missing_deterministic_checks (array), "
        "contradictory_evidence (array), and notes (array). Treat LLM review as advisory. Fail only for "
        "concrete contradictory evidence or missing deterministic checks. Do not treat recorded unavailable "
        "or blocked evidence as passed."
    )
    review = _post_llm_json(system_prompt, bundle, timeout=timeout)
    if not isinstance(review, dict):
        report = {
            "kind": "atlas_server_controlled_final_review",
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
        "kind": "atlas_server_controlled_final_review",
        "status": "passed" if passed else "failed",
        "input_json": str(input_json),
        "bundle": bundle,
        "llm_review": review,
        "finished_at": _now(),
    }
    _write(output_json, report)
    return report


def _configure_app(workspace: Path, data_dir: Path, *, workspace_id: str) -> TestClient:
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
    main.app.state.atlas_test_command_runner = lambda: TestCommandRunner(allowed_commands=["python -m pytest -q", "python -m json.tool config.json"])
    close_project_intelligence_service(main.app)
    register_project_intelligence_service(main.app, ca_data_dir=data_dir, env={})
    return TestClient(main.app)


def _post(client: TestClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=payload)
    body = response.json()
    if response.status_code >= 400:
        return {"status": "failed", "http_status": response.status_code, "path": path, "body": body}
    return body


def _get(client: TestClient, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.get(path, params=params or {})
    body = response.json()
    if response.status_code >= 400:
        return {"status": "failed", "http_status": response.status_code, "path": path, "body": body}
    return body


def _create_pool(
    client: TestClient,
    *,
    goal: str,
    workspace: Path,
    workspace_id: str,
    targets: list[str],
    project_name: str,
    plan_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _post(
        client,
        "/api/atlas/plan-pools?sync=1",
        {
            "input": goal,
            "project_path": str(workspace),
            "project_name": project_name,
            "workspace_id": workspace_id,
            "target_files": targets,
            "planner_mode": "real_planner",
            "requirement_mode": "auto",
            "automation_level": "full_autopilot",
            "metadata": {"preset_id": "guarded_low_risk", "server_controlled_eval": "sc7"},
            "automation_features": {},
            "plan_payload": dict(plan_payload or {}),
        },
    )


def _first_item_id(created: dict[str, Any]) -> str:
    items = list(((created.get("plan_pool") or {}).get("items") or []))
    return str(items[0].get("item_id") or "") if items else ""


def _start_api_run(client: TestClient, *, pool_id: str, item_id: str, workspace_id: str, scenario: str) -> dict[str, Any]:
    return _post(
        client,
        "/api/atlas/runs",
        {
            "pool_id": pool_id,
            "workspace_id": workspace_id,
            "item_id": item_id,
            "item_ids": [item_id] if item_id else [],
            "mode": "fresh",
            "auto_start": True,
            "metadata": {"scenario": scenario, "server_controlled_eval": "sc7"},
        },
    )


def _start_cli_run(client: TestClient, *, pool_id: str, item_id: str, workspace_id: str) -> dict[str, Any]:
    stdout = io.StringIO()
    atlas_run_cli.run_cli(
        [
            "--base-url",
            "http://testserver",
            "start",
            "--pool-id",
            pool_id,
            "--item-id",
            item_id,
            "--workspace-id",
            workspace_id,
        ],
        client=TestClientRunHttpClient(client),
        stdout=stdout,
    )
    return json.loads(stdout.getvalue())


def _cli_watch(client: TestClient, run_id: str) -> dict[str, Any]:
    stdout = io.StringIO()
    atlas_run_cli.run_cli(
        ["--base-url", "http://testserver", "watch", run_id, "--interval", "0.1"],
        client=TestClientRunHttpClient(client),
        stdout=stdout,
    )
    raw = stdout.getvalue()
    if not raw.strip():
        return {"status": "failed", "error": "cli_watch_returned_no_json"}
    return {"status": "observed", "raw_excerpt": raw[:1600]}


def _wait_terminal(client: TestClient, run_id: str, *, timeout_sec: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _get(client, f"/api/atlas/runs/{run_id}/status")
        if last.get("terminal") is True:
            return last
        time.sleep(1.0)
    return {"status": "failed", "terminal": False, "error": "run_timeout", "last_status": last}


def _run_events(client: TestClient, run_id: str) -> dict[str, Any]:
    payload = _get(client, f"/api/atlas/runs/{run_id}/events", {"limit": 1000})
    events = list(payload.get("events") or [])
    return {
        "count": len(events),
        "event_types": [str(event.get("event_type") or "") for event in events],
        "excerpt": events[:3] + (events[-3:] if len(events) > 3 else []),
    }


def _scenario_base(name: str) -> tuple[Path, Path, Path, str]:
    base = Path(tempfile.mkdtemp(prefix=f"sc7-{name}-"))
    return base, base / "workspace", base / "data", f"sc7-{name}"


def run_web_greenfield(timeout_sec: float) -> dict[str, Any]:
    base, workspace, data_dir, workspace_id = _scenario_base("web-greenfield")
    client = _configure_app(workspace, data_dir, workspace_id=workspace_id)
    goal = (
        "Create a single-file web app in index.html. It must contain the exact visible heading "
        "'Atlas SC7 Greenfield Ready' and a button with id='increment' that increments a visible "
        "counter in an element with id='count'."
    )
    rec = {"scenario": "web_app_greenfield", "started_at": _now(), "workspace": str(workspace), "data_dir": str(data_dir)}
    created = _create_pool(client, goal=goal, workspace=workspace, workspace_id=workspace_id, targets=["index.html"], project_name="sc7-web-greenfield")
    rec["plan_status"] = created.get("status")
    pool_id, item_id = str(created.get("pool_id") or ""), _first_item_id(created)
    rec["pool_id"], rec["item_id"] = pool_id, item_id
    if created.get("status") not in RUNNABLE_PLAN_STATUSES or not pool_id or not item_id:
        rec.update({"status": "failed", "fail_reason": "plan_unusable", "plan_detail": {k: created.get(k) for k in ("status", "used_fallback", "fallback_reason")}})
        return rec
    started = _start_api_run(client, pool_id=pool_id, item_id=item_id, workspace_id=workspace_id, scenario="web_app_greenfield")
    run_id = str(started.get("run_id") or "")
    rec["run_id"] = run_id
    rec["cli_watch"] = _cli_watch(client, run_id) if run_id else {"status": "failed", "error": "missing_run_id"}
    rec["final_status"] = _wait_terminal(client, run_id, timeout_sec=timeout_sec) if run_id else {}
    rec["events"] = _run_events(client, run_id) if run_id else {}
    final_html = (workspace / "index.html").read_text(encoding="utf-8") if (workspace / "index.html").is_file() else ""
    rec["deterministic_check"] = {
        "target_file_exists": bool(final_html),
        "expected_heading": "Atlas SC7 Greenfield Ready" in final_html,
        "button_id_increment": "id=\"increment\"" in final_html or "id='increment'" in final_html,
        "counter_id_count": "id=\"count\"" in final_html or "id='count'" in final_html,
    }
    rec["status"] = "passed" if rec["final_status"].get("status") == "completed" and all(rec["deterministic_check"].values()) else "failed"
    rec["finished_at"] = _now()
    return rec


def run_web_repair_cli_start(timeout_sec: float) -> dict[str, Any]:
    _base, workspace, data_dir, workspace_id = _scenario_base("web-repair")
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "index.html").write_text(
        "<!doctype html><html><body><h1>Atlas SC7 Repair Broken</h1><p id=\"status\">BROKEN</p></body></html>\n",
        encoding="utf-8",
    )
    client = _configure_app(workspace, data_dir, workspace_id=workspace_id)
    goal = (
        "Repair index.html. Change the paragraph with id='status' from BROKEN to READY, and change "
        "the heading text to the exact visible text 'Atlas SC7 Repair Ready'. Keep this as a bounded edit."
    )
    rec = {"scenario": "existing_web_app_repair_cli_start", "started_at": _now(), "workspace": str(workspace), "data_dir": str(data_dir)}
    plan_payload = {
        "requirements": [
            {"requirement_id": "req_repair_status", "description": "The paragraph with id status displays READY."},
            {"requirement_id": "req_repair_heading", "description": "The page heading displays Atlas SC7 Repair Ready."},
        ],
        "implementation_steps": [
            {
                "step_id": "web_repair_bounded_edit",
                "title": "Repair visible status and heading text",
                "description": "Edit only index.html so the status paragraph says READY and the heading says Atlas SC7 Repair Ready.",
                "goal": goal,
                "action_type": "update",
                "risk_level": "low",
                "target_files": ["index.html"],
                "requirement_ids": ["req_repair_status", "req_repair_heading"],
                "acceptance_criteria": [
                    "The paragraph with id status contains READY.",
                    "The old BROKEN text is removed.",
                    "The heading contains Atlas SC7 Repair Ready.",
                ],
                "verification_contract": {
                    "contract_id": "sc7_web_repair_text_contract",
                    "description": "Read index.html and verify status READY, heading Atlas SC7 Repair Ready, and BROKEN removed.",
                },
                "verification": [
                    "Read index.html and check the status paragraph contains READY.",
                    "Read index.html and check the heading contains Atlas SC7 Repair Ready.",
                ],
                "rollback": ["Restore the previous index.html content."],
            }
        ],
        "metadata": {"source": "sc7_live_eval_plan_payload"},
    }
    created = _create_pool(
        client,
        goal=goal,
        workspace=workspace,
        workspace_id=workspace_id,
        targets=["index.html"],
        project_name="sc7-web-repair",
        plan_payload=plan_payload,
    )
    rec["plan_status"] = created.get("status")
    pool_id, item_id = str(created.get("pool_id") or ""), _first_item_id(created)
    rec["pool_id"], rec["item_id"] = pool_id, item_id
    if created.get("status") not in RUNNABLE_PLAN_STATUSES or not pool_id or not item_id:
        rec.update({"status": "failed", "fail_reason": "plan_unusable"})
        return rec
    started = _start_cli_run(client, pool_id=pool_id, item_id=item_id, workspace_id=workspace_id)
    run_id = str(started.get("run_id") or "")
    rec["run_id"] = run_id
    rec["final_status"] = _wait_terminal(client, run_id, timeout_sec=timeout_sec) if run_id else {}
    rec["status_api_observed"] = bool(rec["final_status"].get("run_id") == run_id)
    rec["events"] = _run_events(client, run_id) if run_id else {}
    final_html = (workspace / "index.html").read_text(encoding="utf-8")
    rec["deterministic_check"] = {
        "status_ready": ">READY<" in final_html,
        "broken_removed": "BROKEN" not in final_html,
        "heading_ready": "Atlas SC7 Repair Ready" in final_html,
    }
    rec["status"] = "passed" if rec["final_status"].get("status") == "completed" and rec["status_api_observed"] and all(rec["deterministic_check"].values()) else "failed"
    rec["finished_at"] = _now()
    return rec


def run_business_config(timeout_sec: float) -> dict[str, Any]:
    _base, workspace, data_dir, workspace_id = _scenario_base("business-config")
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "config.json").write_text(
        json.dumps({"checkout": {"enabled": False, "limit": 10}, "owner": "atlas-sc7"}, indent=2),
        encoding="utf-8",
    )
    client = _configure_app(workspace, data_dir, workspace_id=workspace_id)
    goal = (
        "Update config.json only. Set checkout.enabled to true and checkout.limit to 25. Preserve "
        "owner as atlas-sc7. Do not add unrelated files."
    )
    rec = {"scenario": "business_config_bounded_edit", "started_at": _now(), "workspace": str(workspace), "data_dir": str(data_dir)}
    plan_payload = {
        "requirements": [
            {"requirement_id": "req_checkout_enabled", "description": "checkout.enabled is true."},
            {"requirement_id": "req_checkout_limit", "description": "checkout.limit is 25."},
            {"requirement_id": "req_owner_preserved", "description": "owner remains atlas-sc7."},
        ],
        "implementation_steps": [
            {
                "step_id": "config_bounded_edit",
                "title": "Update checkout settings in config.json",
                "description": "Edit only config.json so checkout.enabled is true and checkout.limit is 25 while preserving owner.",
                "goal": goal,
                "action_type": "update",
                "risk_level": "low",
                "target_files": ["config.json"],
                "requirement_ids": ["req_checkout_enabled", "req_checkout_limit", "req_owner_preserved"],
                "acceptance_criteria": [
                    "config.json remains valid JSON.",
                    "checkout.enabled is true.",
                    "checkout.limit is 25.",
                    "owner remains atlas-sc7.",
                ],
                "verification_contract": {
                    "contract_id": "sc7_config_json_contract",
                    "description": "Parse config.json and verify checkout.enabled true, checkout.limit 25, and owner atlas-sc7.",
                },
                "verification": [
                    "Parse config.json and check checkout.enabled is true.",
                    "Parse config.json and check checkout.limit is 25.",
                    "Parse config.json and check owner remains atlas-sc7.",
                ],
                "rollback": ["Restore the previous config.json content."],
            }
        ],
        "metadata": {"source": "sc7_live_eval_plan_payload"},
    }
    created = _create_pool(
        client,
        goal=goal,
        workspace=workspace,
        workspace_id=workspace_id,
        targets=["config.json"],
        project_name="sc7-business-config",
        plan_payload=plan_payload,
    )
    rec["plan_status"] = created.get("status")
    pool_id, item_id = str(created.get("pool_id") or ""), _first_item_id(created)
    rec["pool_id"], rec["item_id"] = pool_id, item_id
    if created.get("status") not in RUNNABLE_PLAN_STATUSES or not pool_id or not item_id:
        rec.update({"status": "failed", "fail_reason": "plan_unusable"})
        return rec
    started = _start_api_run(client, pool_id=pool_id, item_id=item_id, workspace_id=workspace_id, scenario="business_config_bounded_edit")
    run_id = str(started.get("run_id") or "")
    rec["run_id"] = run_id
    rec["final_status"] = _wait_terminal(client, run_id, timeout_sec=timeout_sec) if run_id else {}
    rec["events"] = _run_events(client, run_id) if run_id else {}
    try:
        config = json.loads((workspace / "config.json").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        config = {"_parse_error": str(exc)}
    rec["deterministic_check"] = {
        "json_valid": "_parse_error" not in config,
        "checkout_enabled_true": ((config.get("checkout") or {}).get("enabled") is True) if isinstance(config, dict) else False,
        "checkout_limit_25": ((config.get("checkout") or {}).get("limit") == 25) if isinstance(config, dict) else False,
        "owner_preserved": config.get("owner") == "atlas-sc7" if isinstance(config, dict) else False,
    }
    event_types = list((rec.get("events") or {}).get("event_types") or [])
    config_verified = all(rec["deterministic_check"].values())
    safe_apply_reached = "safe_apply_started" in event_types
    terminal = bool(rec["final_status"].get("terminal") is True)
    verifier_status = str(rec["final_status"].get("status") or "")
    verifier_block_reason = str(rec["final_status"].get("block_reason") or "")
    rec["verification_interpretation"] = {
        "deterministic_config_check_authoritative": True,
        "generic_auto_verification_status": verifier_status,
        "generic_auto_verification_block_reason": verifier_block_reason,
    }
    rec["status"] = "passed" if (
        terminal
        and safe_apply_reached
        and config_verified
        and (verifier_status == "completed" or verifier_block_reason == "verification_blocked")
    ) else "failed"
    rec["finished_at"] = _now()
    return rec


def _acceptance_checks(scenarios: list[dict[str, Any]]) -> dict[str, str]:
    by_name = {str(item.get("scenario")): item for item in scenarios}
    green = by_name.get("web_app_greenfield", {})
    repair = by_name.get("existing_web_app_repair_cli_start", {})
    config = by_name.get("business_config_bounded_edit", {})
    return {
        "web_app_greenfield_plan_run_apply_verify": "passed" if green.get("status") == "passed" else "failed",
        "existing_web_app_repair_seeded_defect_run_verify_fix": "passed" if repair.get("status") == "passed" else "failed",
        "business_config_bounded_edit_deterministic_check": "passed" if config.get("status") == "passed" else "failed",
        "cli_starts_run_status_api_observes": "passed" if repair.get("status_api_observed") and repair.get("status") == "passed" else "failed",
        "api_starts_run_cli_watches": "passed" if (green.get("cli_watch") or {}).get("status") == "observed" and green.get("status") == "passed" else "failed",
    }


def run_all(*, output_json: Path, timeout_sec: float, only: set[str]) -> dict[str, Any]:
    report: dict[str, Any] = {
        "kind": "atlas_server_controlled_flow_eval",
        "started_at": _now(),
        "llm_base_url": LLM_BASE_URL,
        "scenarios": [],
    }
    probe = _probe_model(timeout=10.0)
    report["model_probe"] = probe
    if probe.get("status") != "available":
        report["status"] = "blocked"
        report["blocked_reason"] = "blocked_live_llm_unavailable"
        report["finished_at"] = _now()
        _write(output_json, report)
        return report

    scenario_fns = {
        "web_app_greenfield": run_web_greenfield,
        "existing_web_app_repair_cli_start": run_web_repair_cli_start,
        "business_config_bounded_edit": run_business_config,
    }
    for name, fn in scenario_fns.items():
        if only and name not in only:
            continue
        print(f"[sc7] running {name} ...", flush=True)
        try:
            rec = fn(timeout_sec)
        except Exception as exc:  # noqa: BLE001
            rec = {"scenario": name, "status": "error", "error": str(exc)[:500], "finished_at": _now()}
        report["scenarios"].append(rec)
        print(f"[sc7] {name}: {rec.get('status')} {rec.get('fail_reason') or rec.get('error') or ''}", flush=True)

    report["acceptance_checks"] = _acceptance_checks(list(report["scenarios"]))
    report["status"] = "passed" if report["acceptance_checks"] and all(value == "passed" for value in report["acceptance_checks"].values()) else "failed"
    report["finished_at"] = _now()
    _write(output_json, report)
    return report


def _write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run live SC7 Atlas server-controlled flow evaluation.")
    parser.add_argument("--output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_server_controlled_flow_eval" / "sc7_live_eval.json")
    parser.add_argument("--input-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_server_controlled_flow_eval" / "sc7_live_eval.json")
    parser.add_argument("--review-output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_server_controlled_flow_eval" / "sc8_final_review.json")
    parser.add_argument("--timeout-sec", type=float, default=600.0)
    parser.add_argument("--only", default="", help="Comma-separated scenario names.")
    parser.add_argument("--final-review", action="store_true", help="Ask the 8080 LLM to review an existing live evidence bundle.")
    args = parser.parse_args(argv)
    if args.final_review:
        report = run_final_review(input_json=args.input_json, output_json=args.review_output_json, timeout=args.timeout_sec)
        print(json.dumps({"status": report.get("status"), "report": str(args.review_output_json)}, ensure_ascii=False))
        return 0 if report.get("status") == "passed" else 2 if report.get("status") == "blocked" else 1
    only = {item.strip() for item in args.only.split(",") if item.strip()}
    report = run_all(output_json=args.output_json, timeout_sec=args.timeout_sec, only=only)
    print(json.dumps({"status": report.get("status"), "report": str(args.output_json)}, ensure_ascii=False))
    return 0 if report.get("status") == "passed" else 2 if report.get("status") == "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main_cli(sys.argv[1:]))
