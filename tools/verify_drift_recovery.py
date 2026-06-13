"""Verify the GENERAL safe-apply drift recovery with the real local LLM (autopilot path).

Mirrors the panel's approveAndRunPipeline: empty -> develop -> revise -> generate ALL revised
items -> approve -> run multi-item-autopilot. Before the fix, items whose edits drifted (because
an earlier item changed the same file) failed with safe_apply_not_applied. With the fix the
autopilot regenerates them against current content and re-applies, so they report
`safe_apply_drift_recovered` (applied) instead.

    python tools/verify_drift_recovery.py [--output-json PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
import tempfile

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.run_codegen_route_eval import _configure_app, _create_pool, _drive_item_to_verified, _post, _get, _now  # noqa: E402
import main  # noqa: E402

GOAL = (
    "Create a Space Invaders game in index.html where the player's ship is at the bottom, enemies "
    "move left/right and down, arrow keys move the ship and the space bar fires bullets."
)
REVISION_NOTE = (
    "Modify the game: add a visible score that increments when an enemy is destroyed, and show a "
    "'GAME OVER' message when an enemy reaches the player. Keep everything in index.html."
)


def run(output_json: Path) -> dict[str, Any]:
    rep: dict[str, Any] = {"kind": "verify_drift_recovery", "started_at": _now(), "steps": []}
    try:
        probe = main._phase1_llm_json("Return one valid JSON object only.", 'Return {"status":"ok"}.')
    except Exception as exc:  # noqa: BLE001
        probe = {"error": str(exc)[:160]}
    if not isinstance(probe, dict):
        rep["status"] = "blocked"; rep["blocked_reason"] = "configured_model_unavailable"; return rep

    base = Path(tempfile.mkdtemp(prefix="verify-drift-"))
    ws, dd = base / "ws", base / "data"
    wsid = "verify-drift"
    client = _configure_app(ws, dd, workspace_id=wsid)

    created = _create_pool(client, goal=GOAL, workspace=ws, workspace_id=wsid, targets=["index.html"], project_name="verify-drift")
    if created.get("status") == "failed" or created.get("used_fallback"):
        rep["status"] = "blocked"; rep["blocked_reason"] = "initial_plan_unusable"; rep["detail"] = created; return rep
    pool_id = str(created.get("pool_id"))
    items0 = list(((created.get("plan_pool") or {}).get("items") or []))
    if items0:
        drive = _drive_item_to_verified(client, pool_id=pool_id, item_id=str(items0[0]["item_id"]), workspace_id=wsid, tag="dev1")
        rep["steps"].append({"name": "develop_first", "result": drive.get("status")})

    revised = _post(client, f"/api/atlas/plan-pools/{pool_id}/request-revision?sync=1", {"note": REVISION_NOTE, "workspace_id": wsid})
    rev_items = list((revised.get("plan_pool") or {}).get("items") or [])
    rep["steps"].append({"name": "revise", "revised_item_count": len(rev_items),
                         "revision_source": (revised.get("replan_result") or {}).get("revision_source")})

    # Generate ALL revised items (against the original file) -> this is what creates the drift.
    appliable: list[str] = []
    gen = []
    for it in rev_items[:6]:
        iid = str(it["item_id"])
        r = _post(client, "/api/atlas/patch-proposals/generate", {
            "pool_id": pool_id, "item_id": iid, "workspace_id": wsid, "run_id": f"gen_{iid}",
            "source_type": "plan_item", "force_regenerate": True,
        })
        has = ((r.get("metadata") or {}).get("patch_content_available")) is True
        gen.append({"item_id": iid, "status": r.get("status"), "content": has})
        if has:
            appliable.append(iid)
        print(f"[verify] gen {iid}: {r.get('status')} content={has}", flush=True)
    rep["generated"] = gen
    rep["appliable_count"] = len(appliable)

    # Approve each generated patch proposal (Stage 3).
    for iid in appliable:
        _post(client, "/api/atlas/patch-proposals/decide", {
            "pool_id": pool_id, "item_id": iid, "workspace_id": wsid, "decision": "approved", "reason": "verify drift"})

    # Run the multi-item autopilot (apply + verify + self-correction) — the panel's Stage 4.
    run_out = _post(client, "/api/atlas/multi-item-autopilot/run", {
        "pool_id": pool_id, "workspace_id": wsid, "item_ids": appliable,
        "policy_id": "full_auto_multi_item_v1", "dry_run": False, "require_approval": False,
        "include_context_refresh": True, "include_evaluator": True, "include_bounded_retry": True,
        "include_self_correction": True, "self_correction_max_attempts": 2,
        "max_items": len(appliable), "max_changed_files_total": 25,
    })
    item_results = list(run_out.get("item_results") or [])
    summary = {"applied": 0, "drift_recovered": 0, "safe_apply_not_applied": 0, "other": 0}
    detail = []
    for ir in item_results:
        st, reason = str(ir.get("status")), str(ir.get("reason") or "")
        detail.append({"item_id": ir.get("item_id"), "status": st, "reason": reason})
        if reason == "safe_apply_drift_recovered":
            summary["drift_recovered"] += 1; summary["applied"] += 1
        elif st == "applied" or st == "completed":
            summary["applied"] += 1
        elif reason == "safe_apply_not_applied":
            summary["safe_apply_not_applied"] += 1
        else:
            summary["other"] += 1
        print(f"[verify] apply {ir.get('item_id')}: status={st} reason={reason}", flush=True)
    rep["autopilot_status"] = run_out.get("status")
    rep["item_results"] = detail
    rep["summary"] = summary
    # Success: no item left as safe_apply_not_applied (drifted items recovered or applied).
    rep["status"] = "fixed" if (item_results and summary["safe_apply_not_applied"] == 0) else "still_failing"
    rep["finished_at"] = _now()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_codegen_eval" / "verify_drift.json")
    args = p.parse_args()
    r = run(args.output_json)
    print(json.dumps({"status": r.get("status"), "summary": r.get("summary"), "autopilot_status": r.get("autopilot_status")}, ensure_ascii=False))
