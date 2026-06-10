from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

import main
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
from agent.test_command_runner import TestCommandRunner


LIVE_GOAL = (
    "Create a Greenfield single HTML app in index.html. The page must render the exact heading "
    "Atlas Live Greenfield Ready and a visible ready status."
)
WORKSPACE_ID = "pir13-live"
REQUIRED_TEXT = "Atlas Live Greenfield Ready"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redacted_model_env() -> dict[str, str]:
    names = sorted(
        name
        for name in os.environ
        if any(token in name.upper() for token in ("OPENAI", "ANTHROPIC", "CODEAGENT", "LLM", "MODEL", "BASE_URL", "API_KEY"))
    )
    env: dict[str, str] = {}
    for name in names:
        if any(secret in name.upper() for secret in ("KEY", "TOKEN", "SECRET")):
            env[name] = "<set>"
        else:
            env[name] = os.environ.get(name, "")
    return env


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _post(client: TestClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = client.post(path, json=payload)
    body = response.json()
    if response.status_code >= 400:
        return {
            "status": "failed",
            "http_status": response.status_code,
            "path": path,
            "body": body,
        }
    return body


def _probe_configured_model() -> dict[str, Any]:
    probe = {
        "status": "blocked",
        "checked_at": _now(),
        "llm_url_planner": str(getattr(main, "LLM_URL_PLANNER", "")),
        "model_env": _redacted_model_env(),
        "result": None,
        "warnings": [],
    }
    fn = getattr(main, "_phase1_llm_json", None)
    if not callable(fn):
        probe["warnings"].append("phase1_llm_json_unavailable")
        return probe
    try:
        result = fn(
            "Return one valid JSON object only.",
            'Return exactly {"status":"ok"} as JSON.',
        )
    except Exception as exc:  # noqa: BLE001
        probe["warnings"].append(str(exc) or exc.__class__.__name__)
        return probe
    probe["result"] = result
    if isinstance(result, dict):
        probe["status"] = "ready"
    else:
        probe["warnings"].append("configured_model_returned_no_json")
    return probe


def _configure_app(workspace: Path, data_dir: Path) -> TestClient:
    main.app.state.atlas_ca_data_dir = str(data_dir)
    main.app.state.atlas_implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=workspace)
    main.app.state.atlas_llm_json_fn = main._phase1_llm_json
    main.app.state.atlas_test_command_runner = lambda: TestCommandRunner(
        allowed_commands=["python -m pytest -q"]
    )
    return TestClient(main.app)


def run_live_greenfield(workspace: Path, data_dir: Path) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "status": "running",
        "started_at": _now(),
        "workspace": str(workspace.resolve()),
        "data_dir": str(data_dir.resolve()),
        "workspace_id": WORKSPACE_ID,
        "goal": LIVE_GOAL,
        "steps": [],
        "artifacts": {},
        "warnings": [],
        "errors": [],
    }

    model_probe = _probe_configured_model()
    report["model_probe"] = model_probe
    if model_probe.get("status") != "ready":
        report["status"] = "blocked"
        report["blocked_reason"] = "configured_model_unavailable"
        report["finished_at"] = _now()
        return report

    client = _configure_app(workspace, data_dir)
    created = _post(
        client,
        "/api/atlas/plan-pools?sync=1",
        {
            "input": LIVE_GOAL,
            "project_path": str(workspace),
            "project_name": "pir13-live-greenfield",
            "workspace_id": WORKSPACE_ID,
            "planner_mode": "real_planner",
            "requirement_mode": "ask_when_needed",
        },
    )
    report["steps"].append({"name": "plan_pool", "response": created})
    if created.get("status") == "failed":
        report["status"] = "failed"
        report["errors"].append("plan_pool_http_failed")
        report["finished_at"] = _now()
        return report
    if created.get("used_fallback") or created.get("fallback_reason"):
        report["status"] = "blocked"
        report["blocked_reason"] = "live_planner_fallback_used"
        report["finished_at"] = _now()
        return report
    if created.get("status") == "waiting_for_clarification":
        report["status"] = "blocked"
        report["blocked_reason"] = "live_planner_requested_clarification"
        report["finished_at"] = _now()
        return report
    items = list(((created.get("plan_pool") or {}).get("items") or []))
    if not items:
        report["status"] = "failed"
        report["errors"].append("live_planner_returned_no_items")
        report["finished_at"] = _now()
        return report
    pool_id = str(created["pool_id"])
    source_item_id = str(items[0]["item_id"])
    report["artifacts"]["pool_id"] = pool_id
    report["artifacts"]["source_item_id"] = source_item_id

    proposed = _post(
        client,
        "/api/atlas/patch-proposals/generate",
        {
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": WORKSPACE_ID,
            "run_id": "pir13_live_patchgen",
            "source_type": "plan_item",
        },
    )
    report["steps"].append({"name": "patch_proposal", "response": proposed})
    if proposed.get("status") != "proposed":
        report["status"] = "failed"
        report["errors"].append("live_patch_proposal_not_proposed")
        report["finished_at"] = _now()
        return report
    proposal = proposed.get("proposal") or {}
    proposal_risk = str(proposal.get("risk_level") or "").lower()
    proposal_targets = [str(path).replace("\\", "/") for path in list(proposal.get("target_files") or [])]
    if proposal_risk != "low" or "index.html" not in proposal_targets:
        report["status"] = "blocked"
        report["blocked_reason"] = "live_proposal_outside_single_html_low_risk_scope"
        report["finished_at"] = _now()
        return report
    proposal_id = str((proposal.get("proposal_id") or ""))
    report["artifacts"]["proposal_id"] = proposal_id
    report["artifacts"]["proposal_json_path"] = proposed.get("proposal_json_path", "")
    report["artifacts"]["proposal_md_path"] = proposed.get("proposal_md_path", "")

    approved_proposal = _post(
        client,
        "/api/atlas/patch-proposals/decide",
        {
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": WORKSPACE_ID,
            "proposal_id": proposal_id,
            "decision": "approved",
            "reason": "PIR-13 live configured-model Greenfield scenario approval.",
        },
    )
    report["steps"].append({"name": "proposal_approval", "response": approved_proposal})
    if approved_proposal.get("status") != "approved":
        report["status"] = "failed"
        report["errors"].append("live_proposal_approval_failed")
        report["finished_at"] = _now()
        return report

    draft = _post(
        client,
        "/api/atlas/patch-proposals/planitem-draft",
        {
            "pool_id": pool_id,
            "item_id": source_item_id,
            "workspace_id": WORKSPACE_ID,
            "proposal_id": proposal_id,
            "run_id": "pir13_live_draft",
        },
    )
    report["steps"].append({"name": "draft", "response": draft})
    if draft.get("status") != "created":
        report["status"] = "failed"
        report["errors"].append("live_draft_not_created")
        report["finished_at"] = _now()
        return report
    draft_item_id = str(((draft.get("draft_item") or {}).get("draft_item_id") or ""))
    report["artifacts"]["draft_item_id"] = draft_item_id
    report["artifacts"]["draft_json_path"] = (draft.get("metadata") or {}).get("draft_json_path", "")
    report["artifacts"]["draft_md_path"] = (draft.get("metadata") or {}).get("draft_md_path", "")

    approved_item = _post(
        client,
        "/api/atlas/approvals/decide",
        {
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": WORKSPACE_ID,
            "decision": "approved",
            "reason": "Approve the PIR-13 live Greenfield PlanItem for Safe Apply.",
        },
    )
    report["steps"].append({"name": "planitem_approval", "response": approved_item})
    if approved_item.get("decision") != "approved":
        report["status"] = "failed"
        report["errors"].append("live_planitem_approval_failed")
        report["finished_at"] = _now()
        return report

    verified = _post(
        client,
        "/api/atlas/automation/safe-apply-one-and-verify",
        {
            "pool_id": pool_id,
            "item_id": draft_item_id,
            "workspace_id": WORKSPACE_ID,
            "run_id": "pir13_live_verify",
        },
    )
    report["steps"].append({"name": "safe_apply_and_verify", "response": verified})
    auto_safe = verified.get("auto_safe_apply_result") or {}
    auto_verify = verified.get("auto_verification_result") or {}
    report["artifacts"]["change_snapshot"] = auto_safe.get("change_snapshot") or {}
    report["artifacts"]["events_path"] = str(
        data_dir
        / "atlas"
        / "workspaces"
        / WORKSPACE_ID
        / "plan_pools"
        / pool_id
        / "pipeline_runs"
        / "pir13_live_verify"
        / "events.ndjson"
    )
    html = workspace / "index.html"
    html_text = html.read_text(encoding="utf-8") if html.is_file() else ""
    if (
        verified.get("status") == "applied_and_verified"
        and auto_safe.get("status") == "applied"
        and auto_verify.get("status") == "passed"
        and REQUIRED_TEXT in html_text
    ):
        report["status"] = "passed"
    else:
        report["status"] = "failed"
        report["errors"].append("live_greenfield_acceptance_failed")
    report["finished_at"] = _now()
    return report


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the PIR-13 live configured-model Greenfield gate.")
    parser.add_argument("--workspace", type=Path, default=None, help="Temporary project workspace. Defaults to a new temp directory.")
    parser.add_argument("--data-dir", type=Path, default=None, help="Atlas data directory. Defaults beside the workspace.")
    parser.add_argument("--output-json", type=Path, default=None, help="Path for the evidence report JSON.")
    parser.add_argument(
        "--allow-blocked-exit-zero",
        action="store_true",
        help="Exit 0 when the configured model is unavailable. This records evidence only; it does not pass the live gate.",
    )
    return parser.parse_args(argv)


def main_cli(argv: list[str]) -> int:
    args = parse_args(argv)
    temp_root: tempfile.TemporaryDirectory[str] | None = None
    if args.workspace is None:
        temp_root = tempfile.TemporaryDirectory(prefix="pir13-live-greenfield-")
        workspace = Path(temp_root.name) / "workspace"
    else:
        workspace = args.workspace
    data_dir = args.data_dir or workspace.parent / "atlas_data"
    if args.output_json is not None:
        output_json = args.output_json
    elif temp_root is not None:
        output_json = REPO_ROOT / "ca_data" / "atlas" / "pir13_live_greenfield_report.json"
    else:
        output_json = data_dir / "pir13_live_greenfield_report.json"
    try:
        report = run_live_greenfield(workspace, data_dir)
        _write_report(output_json, report)
        print(json.dumps({"status": report.get("status"), "report": str(output_json)}, ensure_ascii=False))
        if report.get("status") == "passed":
            return 0
        if report.get("status") == "blocked":
            return 0 if args.allow_blocked_exit_zero else 2
        return 1
    finally:
        if temp_root is not None:
            temp_root.cleanup()


if __name__ == "__main__":
    raise SystemExit(main_cli(sys.argv[1:]))
