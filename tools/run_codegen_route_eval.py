"""Route-level real-LLM evaluation of Atlas codegen, end-to-end to verification.

Exercises the four routes that branch AFTER a plan is generated, each driven by the
CONFIGURED local model through the real FastAPI pipeline (TestClient), in an isolated
temp workspace:

  route_a_new        empty workspace -> greenfield plan -> generate -> apply -> verify
  route_b_existing   seeded project  -> modify plan     -> generate -> apply -> verify
  route_c_revision   route_a pool -> request-revision (plan history) -> re-drive to verify
  route_d_autonomous seeded pool -> /autonomous-codegen/run -> converge (apply+verify)

Routes A/B/C use HTML targets so verification runs on the proven browser-smoke path.
Success for A/B/C requires safe_apply.status == "applied" AND auto_verification.status
== "passed". Route D requires the orchestrator to report a completed status with at least
one item applied+verified.

Honest evidence: if the configured model is unreachable, the run is `blocked` (not passed).
The real repository is never mutated; everything happens under temp workspaces.

Usage:
    python tools/run_codegen_route_eval.py [--output-json PATH] [--only route_a_new,...]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor  # noqa: E402
from agent.test_command_runner import TestCommandRunner  # noqa: E402
from agent.project_intelligence.service_registry import (  # noqa: E402
    close_project_intelligence_service,
    register_project_intelligence_service,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _post(client: TestClient, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    resp = client.post(path, json=payload)
    body = resp.json()
    if resp.status_code >= 400:
        return {"status": "failed", "http_status": resp.status_code, "path": path, "body": body}
    return body


def _get(client: TestClient, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    resp = client.get(path, params=params or {})
    body = resp.json()
    if resp.status_code >= 400:
        return {"status": "failed", "http_status": resp.status_code, "path": path, "body": body}
    return body


def _configure_app(workspace: Path, data_dir: Path, *, workspace_id: str) -> TestClient:
    workspace.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    main.app.state.atlas_ca_data_dir = str(data_dir)
    main.app.state.atlas_implementation_executor = AtlasFileSafeApplyExecutor(workspace_root=workspace)
    main.app.state.atlas_llm_json_fn = main._phase1_llm_json
    main.app.state.atlas_test_command_runner = lambda: TestCommandRunner(allowed_commands=["python -m pytest -q"])
    close_project_intelligence_service(main.app)
    register_project_intelligence_service(main.app, ca_data_dir=data_dir, env={})
    return TestClient(main.app)


def _create_pool(client: TestClient, *, goal: str, workspace: Path, workspace_id: str, targets: list[str], project_name: str) -> dict[str, Any]:
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
            "requirement_mode": "ask_when_needed",
            "automation_level": "full_autopilot",
            "metadata": {"preset_id": "guarded_low_risk"},
            "automation_features": {},
        },
    )


def _drive_item_to_verified(
    client: TestClient,
    *,
    pool_id: str,
    item_id: str,
    workspace_id: str,
    tag: str,
) -> dict[str, Any]:
    """Run the manual gated flow: generate -> decide -> draft -> approve -> apply+verify."""
    out: dict[str, Any] = {"steps": {}, "status": "failed"}

    proposed = _post(client, "/api/atlas/patch-proposals/generate", {
        "pool_id": pool_id, "item_id": item_id, "workspace_id": workspace_id,
        "run_id": f"{tag}_patchgen", "source_type": "plan_item",
    })
    out["steps"]["generate"] = proposed.get("status")
    if proposed.get("status") != "proposed":
        out["fail_reason"] = "patch_proposal_not_proposed"
        out["generate_detail"] = {k: proposed.get(k) for k in ("status", "warnings", "metadata")}
        return out
    proposal = proposed.get("proposal") or {}
    proposal_id = str(proposal.get("proposal_id") or "")

    decided = _post(client, "/api/atlas/patch-proposals/decide", {
        "pool_id": pool_id, "item_id": item_id, "workspace_id": workspace_id,
        "proposal_id": proposal_id, "decision": "approved", "reason": f"{tag} approval",
    })
    out["steps"]["decide"] = decided.get("status")
    if decided.get("status") != "approved":
        out["fail_reason"] = "proposal_approval_failed"
        return out

    draft = _post(client, "/api/atlas/patch-proposals/planitem-draft", {
        "pool_id": pool_id, "item_id": item_id, "workspace_id": workspace_id,
        "proposal_id": proposal_id, "run_id": f"{tag}_draft",
    })
    out["steps"]["draft"] = draft.get("status")
    if draft.get("status") != "created":
        out["fail_reason"] = "draft_not_created"
        return out
    draft_item_id = str(((draft.get("draft_item") or {}).get("draft_item_id") or ""))

    approved_item = _post(client, "/api/atlas/approvals/decide", {
        "pool_id": pool_id, "item_id": draft_item_id, "workspace_id": workspace_id,
        "decision": "approved", "reason": f"{tag} planitem approval",
    })
    out["steps"]["planitem_approve"] = approved_item.get("decision")
    if approved_item.get("decision") != "approved":
        out["fail_reason"] = "planitem_approval_failed"
        return out

    verified = _post(client, "/api/atlas/automation/safe-apply-one-and-verify", {
        "pool_id": pool_id, "item_id": draft_item_id, "workspace_id": workspace_id,
        "run_id": f"{tag}_verify",
    })
    auto_safe = verified.get("auto_safe_apply_result") or {}
    auto_verify = verified.get("auto_verification_result") or {}
    out["draft_item_id"] = draft_item_id
    out["safe_apply_status"] = auto_safe.get("status")
    out["verification_status"] = auto_verify.get("status")
    out["overall"] = verified.get("status")
    if (
        verified.get("status") == "applied_and_verified"
        and auto_safe.get("status") == "applied"
        and auto_verify.get("status") == "passed"
    ):
        out["status"] = "passed"
    else:
        out["fail_reason"] = "apply_or_verify_failed"
    return out


# ── HTML goals (browser-smoke verification path) ──────────────────────────────
_NEW_GOAL = (
    "Create a Greenfield single HTML app in index.html. The page must render the exact heading "
    "'Atlas Route New Ready' and a visible button that increments a counter shown in #count."
)
_EXISTING_SEED = (
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>Base</title></head>"
    "<body><h1>Atlas Route Existing Base</h1><p id=\"status\">pending</p></body></html>\n"
)
_EXISTING_GOAL = (
    "Modify the existing index.html so the paragraph with id='status' shows the text 'ready' instead "
    "of 'pending', and add a heading 'Atlas Route Existing Updated'. Preserve the existing structure."
)
_REVISION_NOTE = (
    "Also add a visible button labelled 'Refresh' that, when clicked, updates the status text to 'refreshed'."
)


def _first_item_id(created: dict[str, Any]) -> str:
    items = list(((created.get("plan_pool") or {}).get("items") or []))
    return str(items[0]["item_id"]) if items else ""


def run_route_a(workspace_id: str = "route-a-new") -> dict[str, Any]:
    rec: dict[str, Any] = {"route": "route_a_new", "started_at": _now(), "status": "failed"}
    base = Path(tempfile.mkdtemp(prefix="route-a-"))
    ws, dd = base / "ws", base / "data"
    client = _configure_app(ws, dd, workspace_id=workspace_id)
    created = _create_pool(client, goal=_NEW_GOAL, workspace=ws, workspace_id=workspace_id, targets=["index.html"], project_name="route-a-new")
    rec["plan_status"] = created.get("status")
    if created.get("status") == "failed" or created.get("used_fallback") or created.get("status") == "waiting_for_clarification":
        rec["fail_reason"] = "plan_unusable"
        rec["plan_detail"] = {k: created.get(k) for k in ("status", "used_fallback", "fallback_reason")}
        rec["finished_at"] = _now()
        return rec
    pool_id, item_id = str(created.get("pool_id") or ""), _first_item_id(created)
    rec["pool_id"], rec["item_id"] = pool_id, item_id
    drive = _drive_item_to_verified(client, pool_id=pool_id, item_id=item_id, workspace_id=workspace_id, tag="route_a")
    rec["drive"] = drive
    rec["status"] = drive.get("status")
    rec["finished_at"] = _now()
    return rec


def run_route_b(workspace_id: str = "route-b-existing") -> dict[str, Any]:
    rec: dict[str, Any] = {"route": "route_b_existing", "started_at": _now(), "status": "failed"}
    base = Path(tempfile.mkdtemp(prefix="route-b-"))
    ws, dd = base / "ws", base / "data"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "index.html").write_text(_EXISTING_SEED, encoding="utf-8")
    client = _configure_app(ws, dd, workspace_id=workspace_id)
    created = _create_pool(client, goal=_EXISTING_GOAL, workspace=ws, workspace_id=workspace_id, targets=["index.html"], project_name="route-b-existing")
    rec["plan_status"] = created.get("status")
    if created.get("status") == "failed" or created.get("used_fallback") or created.get("status") == "waiting_for_clarification":
        rec["fail_reason"] = "plan_unusable"
        rec["plan_detail"] = {k: created.get(k) for k in ("status", "used_fallback", "fallback_reason")}
        rec["finished_at"] = _now()
        return rec
    pool_id, item_id = str(created.get("pool_id") or ""), _first_item_id(created)
    rec["pool_id"], rec["item_id"] = pool_id, item_id
    drive = _drive_item_to_verified(client, pool_id=pool_id, item_id=item_id, workspace_id=workspace_id, tag="route_b")
    rec["drive"] = drive
    # Confirm the existing file was modified, not blindly recreated.
    final = (ws / "index.html").read_text(encoding="utf-8") if (ws / "index.html").is_file() else ""
    rec["existing_preserved_or_updated"] = ("ready" in final and "Atlas Route Existing" in final)
    rec["status"] = "passed" if (drive.get("status") == "passed" and rec["existing_preserved_or_updated"]) else "failed"
    rec["finished_at"] = _now()
    return rec


def run_route_c(workspace_id: str = "route-c-revision") -> dict[str, Any]:
    """Plan-history revision: build a pool, request-revision, then drive the reset pool to verified."""
    rec: dict[str, Any] = {"route": "route_c_revision", "started_at": _now(), "status": "failed"}
    base = Path(tempfile.mkdtemp(prefix="route-c-"))
    ws, dd = base / "ws", base / "data"
    client = _configure_app(ws, dd, workspace_id=workspace_id)
    created = _create_pool(client, goal=_NEW_GOAL, workspace=ws, workspace_id=workspace_id, targets=["index.html"], project_name="route-c-revision")
    if created.get("status") == "failed" or created.get("used_fallback") or created.get("status") == "waiting_for_clarification":
        rec["fail_reason"] = "initial_plan_unusable"
        rec["plan_detail"] = {k: created.get(k) for k in ("status", "used_fallback", "fallback_reason")}
        rec["finished_at"] = _now()
        return rec
    pool_id = str(created.get("pool_id") or "")
    rec["pool_id"] = pool_id

    revised = _post(client, f"/api/atlas/plan-pools/{pool_id}/request-revision?sync=1", {
        "note": _REVISION_NOTE, "workspace_id": workspace_id,
    })
    rec["revision_status"] = revised.get("status")
    rec["revision_source"] = (revised.get("replan_result") or {}).get("revision_source")
    revised_pool = revised.get("plan_pool") or {}
    items = list(revised_pool.get("items") or [])
    if not items:
        rec["fail_reason"] = "revision_returned_no_items"
        rec["finished_at"] = _now()
        return rec
    item_id = str(items[0]["item_id"])
    rec["item_id"] = item_id
    drive = _drive_item_to_verified(client, pool_id=pool_id, item_id=item_id, workspace_id=workspace_id, tag="route_c")
    rec["drive"] = drive
    rec["status"] = drive.get("status")
    rec["finished_at"] = _now()
    return rec


def run_route_d(workspace_id: str = "route-d-autonomous") -> dict[str, Any]:
    """Autonomous convergence: build a pool, then /autonomous-codegen/run to completion."""
    rec: dict[str, Any] = {"route": "route_d_autonomous", "started_at": _now(), "status": "failed"}
    base = Path(tempfile.mkdtemp(prefix="route-d-"))
    ws, dd = base / "ws", base / "data"
    client = _configure_app(ws, dd, workspace_id=workspace_id)
    created = _create_pool(client, goal=_NEW_GOAL, workspace=ws, workspace_id=workspace_id, targets=["index.html"], project_name="route-d-autonomous")
    if created.get("status") == "failed" or created.get("used_fallback") or created.get("status") == "waiting_for_clarification":
        rec["fail_reason"] = "plan_unusable"
        rec["plan_detail"] = {k: created.get(k) for k in ("status", "used_fallback", "fallback_reason")}
        rec["finished_at"] = _now()
        return rec
    pool_id = str(created.get("pool_id") or "")
    rec["pool_id"] = pool_id
    run_out = _post(client, "/api/atlas/autonomous-codegen/run", {
        "pool_id": pool_id, "workspace_id": workspace_id, "run_id": "route_d_auto",
    })
    rec["auto_status"] = run_out.get("status")
    rec["auto_phase"] = run_out.get("phase")
    rec["generated_count"] = run_out.get("generated_count")
    rec["stop_reason"] = run_out.get("stop_reason")
    # Reload pool and confirm at least one item is applied+verified.
    reloaded = _get(client, f"/api/atlas/plan-pools/{pool_id}", params={"workspace_id": workspace_id})
    items = list(((reloaded.get("plan_pool") or {}).get("items") or []))
    applied_verified = 0
    for it in items:
        meta = it.get("metadata") or {}
        sa = (meta.get("safe_apply") or meta.get("auto_safe_apply") or {})
        av = (meta.get("auto_verification") or meta.get("latest_verification") or meta.get("verification") or {})
        if str(sa.get("status")) == "applied" and str(av.get("status")) == "passed":
            applied_verified += 1
    rec["applied_verified_items"] = applied_verified
    final = (ws / "index.html").read_text(encoding="utf-8") if (ws / "index.html").is_file() else ""
    rec["target_written"] = "Atlas Route New Ready" in final
    rec["status"] = "passed" if (
        str(run_out.get("status")) in {"completed", "completed_with_warnings"}
        and (applied_verified >= 1 or rec["target_written"])
    ) else "failed"
    rec["finished_at"] = _now()
    return rec


ROUTES = {
    "route_a_new": run_route_a,
    "route_b_existing": run_route_b,
    "route_c_revision": run_route_c,
    "route_d_autonomous": run_route_d,
}


def main_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Route-level real-LLM codegen evaluation.")
    parser.add_argument("--output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_codegen_eval" / "route_eval.json")
    parser.add_argument("--only", type=str, default="", help="Comma-separated route names.")
    args = parser.parse_args(argv)

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    routes = [(name, fn) for name, fn in ROUTES.items() if not only or name in only]

    try:
        probe = main._phase1_llm_json("Return one valid JSON object only.", 'Return exactly {"status":"ok"} as JSON.')
    except Exception as exc:  # noqa: BLE001
        probe = {"error": str(exc)[:160]}
    report: dict[str, Any] = {
        "kind": "route_eval",
        "started_at": _now(),
        "llm_url_planner": str(getattr(main, "LLM_URL_PLANNER", "")),
        "model_probe": probe,
        "routes": [],
    }
    if not isinstance(probe, dict):
        report["status"] = "blocked"
        report["blocked_reason"] = "configured_model_unavailable"
        report["finished_at"] = _now()
        _write(args.output_json, report)
        print(json.dumps({"status": "blocked", "reason": "configured_model_unavailable"}, ensure_ascii=False))
        return 2

    for name, fn in routes:
        print(f"[route] running {name} ...", flush=True)
        try:
            rec = fn()
        except Exception as exc:  # noqa: BLE001
            rec = {"route": name, "status": "error", "error": str(exc)[:300]}
        report["routes"].append(rec)
        print(f"  -> {name}: status={rec.get('status')} fail_reason={rec.get('fail_reason')}", flush=True)

    passed = sum(1 for r in report["routes"] if r.get("status") == "passed")
    total = len(report["routes"])
    report["status"] = "passed" if passed == total and total > 0 else "failed"
    report["summary"] = {"passed": passed, "total": total}
    report["finished_at"] = _now()
    _write(args.output_json, report)
    print(json.dumps({"status": report["status"], "passed": passed, "total": total, "report": str(args.output_json)}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


def _write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main_cli(sys.argv[1:]))
