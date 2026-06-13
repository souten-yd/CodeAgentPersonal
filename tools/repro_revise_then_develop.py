"""Reproduce: empty project -> develop -> revise -> develop again (real local LLM).

Mirrors the failing user scenario (Space Invaders: generate from empty, then modify and
re-develop the revised plan) to see whether patch generation AFTER a plan revision fails
SERVER-SIDE (logic/content) or succeeds (so the browser's `network_error` is transport-only).

Runs in-process via TestClient against the real model on LLM_URL (8080). Records, per item,
the generate status / patch_generation.state / whether real content was produced / elapsed
seconds / warnings / any HTTP error. Empty workspace, temp data dir; the real repo is untouched.

    python tools/repro_revise_then_develop.py [--output-json PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.run_codegen_route_eval import (  # noqa: E402
    _configure_app, _create_pool, _drive_item_to_verified, _post, _get, _now,
)
import main  # noqa: E402

GOAL = (
    "Create a Space Invaders game in index.html where the player's ship is at the bottom of the "
    "screen, enemies move from left to right and down, and upon hitting a wall they move down one "
    "row. Arrow keys move the ship; space bar fires bullets that destroy enemies."
)
REVISION_NOTE = (
    "Modify the game: add a visible score that increments when an enemy is destroyed, and show a "
    "'GAME OVER' message when an enemy reaches the player. Keep everything in index.html."
)


def _gen_one(client, *, pool_id, item_id, workspace_id, tag):
    started = time.monotonic()
    resp = _post(client, "/api/atlas/patch-proposals/generate", {
        "pool_id": pool_id, "item_id": item_id, "workspace_id": workspace_id,
        "run_id": f"{tag}_{item_id}", "source_type": "plan_item",
    })
    elapsed = round(time.monotonic() - started, 1)
    pg = ((resp.get("metadata") or {}).get("patch_generation") or {})
    return {
        "item_id": item_id,
        "elapsed_s": elapsed,
        "status": resp.get("status"),
        "pg_state": pg.get("state"),
        "pg_outcome": pg.get("outcome"),
        "patch_content_available": (resp.get("metadata") or {}).get("patch_content_available"),
        "warnings": list(resp.get("warnings") or [])[:6],
        "http_failed": resp.get("status") == "failed" and "http_status" in resp,
        "http_status": resp.get("http_status"),
    }


def run(output_json: Path) -> dict[str, Any]:
    report: dict[str, Any] = {"kind": "repro_revise_then_develop", "started_at": _now(), "steps": [], "errors": []}
    # Preflight
    try:
        probe = main._phase1_llm_json("Return one valid JSON object only.", 'Return {"status":"ok"}.')
    except Exception as exc:  # noqa: BLE001
        probe = {"error": str(exc)[:160]}
    if not isinstance(probe, dict):
        report["status"] = "blocked"; report["blocked_reason"] = "configured_model_unavailable"
        return report

    base = Path(tempfile.mkdtemp(prefix="repro-revise-"))
    ws, dd = base / "ws", base / "data"
    wsid = "repro-revise"
    client = _configure_app(ws, dd, workspace_id=wsid)

    # 1) Empty -> create plan
    created = _create_pool(client, goal=GOAL, workspace=ws, workspace_id=wsid, targets=["index.html"], project_name="repro-revise")
    report["steps"].append({"name": "create_plan", "status": created.get("status"), "used_fallback": created.get("used_fallback")})
    if created.get("status") == "failed" or created.get("used_fallback"):
        report["status"] = "blocked"; report["blocked_reason"] = "initial_plan_unusable"; report["detail"] = created
        return report
    pool_id = str(created.get("pool_id"))
    items0 = list(((created.get("plan_pool") or {}).get("items") or []))
    report["initial_item_count"] = len(items0)

    # 2) Develop the first item (creates index.html)
    if items0:
        drive = _drive_item_to_verified(client, pool_id=pool_id, item_id=str(items0[0]["item_id"]), workspace_id=wsid, tag="dev1")
        report["steps"].append({"name": "develop_first", "result": drive.get("status"), "fail_reason": drive.get("fail_reason"),
                                "safe_apply": drive.get("safe_apply_status"), "verify": drive.get("verification_status")})
        report["index_html_exists_after_dev1"] = (ws / "index.html").is_file()

    # 3) Revise (modify content)
    revised = _post(client, f"/api/atlas/plan-pools/{pool_id}/request-revision?sync=1", {"note": REVISION_NOTE, "workspace_id": wsid})
    rev_items = list((revised.get("plan_pool") or {}).get("items") or [])
    report["steps"].append({"name": "revise", "status": revised.get("status"),
                            "revision_source": (revised.get("replan_result") or {}).get("revision_source"),
                            "llm_revision_error": (revised.get("replan_result") or {}).get("llm_revision_error"),
                            "revised_item_count": len(rev_items)})

    # 4) Develop the revised plan: generate each item, capture diagnostics (the failing phase)
    gen_results = []
    for it in rev_items[:6]:
        rec = _gen_one(client, pool_id=pool_id, item_id=str(it["item_id"]), workspace_id=wsid, tag="dev2")
        gen_results.append(rec)
        print(f"[repro] revised gen {rec['item_id']}: status={rec['status']} pg={rec['pg_state']} "
              f"content={rec['patch_content_available']} {rec['elapsed_s']}s warns={rec['warnings']}", flush=True)
    report["revised_generation"] = gen_results

    produced = sum(1 for r in gen_results if r.get("patch_content_available"))
    report["revised_generation_summary"] = {"items": len(gen_results), "produced_content": produced}

    # Mirror the panel's generate-ALL-then-apply-ALL flow: now safe-apply each generated item
    # SEQUENTIALLY against the live file. If multiple items edit the same file, later items'
    # stale old_string snapshots can drift -> edit_not_applicable -> safe_apply_not_applied.
    from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor
    from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
    storage = AtlasPlanPoolStorage(dd)
    apply_results = []
    appliable = [r for r in gen_results if r.get("patch_content_available")]
    for r in appliable:
        pool2 = storage.load_pool(pool_id)
        item2 = pool2.get_item(r["item_id"])
        try:
            ares = AtlasFileSafeApplyExecutor(workspace_root=ws).apply_plan_item_safe(item=item2, pool=pool2)
        except Exception as exc:  # noqa: BLE001
            ares = {"status": "exception", "reasons": [str(exc)[:160]]}
        rec = {"item_id": r["item_id"], "targets": list(item2.target_files or []),
               "apply_status": ares.get("status"), "reasons": list(ares.get("reasons") or [])[:4],
               "content_mode": (item2.metadata or {}).get("file_changes") and "file_changes"
                               or ((item2.metadata or {}).get("edits") and "edits")
                               or ((item2.metadata or {}).get("unified_diff_preview") and "unified_diff")
                               or ((item2.metadata or {}).get("proposed_content") and "full_content") or "none"}
        apply_results.append(rec)
        print(f"[repro] apply {rec['item_id']} ({rec['content_mode']}) -> {rec['apply_status']} {rec['reasons']}", flush=True)
    report["sequential_apply"] = apply_results
    applied_ok = sum(1 for a in apply_results if a.get("apply_status") == "applied")
    drift = [a for a in apply_results if a.get("apply_status") != "applied"]
    report["sequential_apply_summary"] = {"items": len(apply_results), "applied": applied_ok, "not_applied": len(drift)}

    if drift:
        report["status"] = "reproduced_safe_apply_failure"
    elif gen_results and produced == 0:
        report["status"] = "reproduced_generation_failure"
    else:
        report["status"] = "ok_all_applied"
    report["finished_at"] = _now()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_codegen_eval" / "repro_revise.json")
    args = p.parse_args()
    rep = run(args.output_json)
    print(json.dumps({"status": rep.get("status"), "summary": rep.get("revised_generation_summary"),
                      "revise": next((s for s in rep.get("steps", []) if s.get("name") == "revise"), None)}, ensure_ascii=False))
