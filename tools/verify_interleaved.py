"""Verify the INTERLEAVED build flow (real local LLM) — the primary safe_apply_not_applied fix.

Mirrors the new panel logic: empty -> develop -> revise -> then for EACH revised item,
generate its patch against the CURRENT file and immediately apply+verify it (single-item
autopilot) BEFORE generating the next item. Because every patch is generated against the live
file (including earlier items' applied edits), edit drift cannot occur, so no item should fail
with safe_apply_not_applied.

    python tools/verify_interleaved.py [--output-json PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.run_codegen_route_eval import _configure_app, _create_pool, _drive_item_to_verified, _post, _now  # noqa: E402
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
    rep: dict[str, Any] = {"kind": "verify_interleaved", "started_at": _now(), "steps": []}
    try:
        probe = main._phase1_llm_json("Return one valid JSON object only.", 'Return {"status":"ok"}.')
    except Exception as exc:  # noqa: BLE001
        probe = {"error": str(exc)[:160]}
    if not isinstance(probe, dict):
        rep["status"] = "blocked"; rep["blocked_reason"] = "configured_model_unavailable"; return rep

    base = Path(tempfile.mkdtemp(prefix="verify-interleaved-"))
    ws, dd = base / "ws", base / "data"
    wsid = "verify-interleaved"
    client = _configure_app(ws, dd, workspace_id=wsid)

    created = _create_pool(client, goal=GOAL, workspace=ws, workspace_id=wsid, targets=["index.html"], project_name="verify-interleaved")
    if created.get("status") == "failed" or created.get("used_fallback"):
        rep["status"] = "blocked"; rep["blocked_reason"] = "initial_plan_unusable"; rep["detail"] = created; return rep
    pool_id = str(created.get("pool_id"))
    items0 = list(((created.get("plan_pool") or {}).get("items") or []))
    if items0:
        drive = _drive_item_to_verified(client, pool_id=pool_id, item_id=str(items0[0]["item_id"]), workspace_id=wsid, tag="dev1")
        rep["steps"].append({"name": "develop_first", "result": drive.get("status")})

    revised = _post(client, f"/api/atlas/plan-pools/{pool_id}/request-revision?sync=1", {"note": REVISION_NOTE, "workspace_id": wsid})
    rev_items = list((revised.get("plan_pool") or {}).get("items") or [])
    rep["steps"].append({"name": "revise", "revised_item_count": len(rev_items)})

    # INTERLEAVED: generate THEN apply+verify, one item at a time (against current content).
    per_item = []
    for it in rev_items[:6]:
        iid = str(it["item_id"])
        # Mirror the panel: retry a content-required generation up to 2x (non-deterministic misses).
        has = False
        g = {}
        for attempt in range(1, 3):
            g = _post(client, "/api/atlas/patch-proposals/generate", {
                "pool_id": pool_id, "item_id": iid, "workspace_id": wsid, "run_id": f"gen_{iid}_{attempt}",
                "source_type": "plan_item", "force_regenerate": True})
            has = ((g.get("metadata") or {}).get("patch_content_available")) is True
            if has:
                break
        # Capture the item's nature + WHY generation produced no content (to tell a real
        # implementation item that the model missed from a genuine non-file/meta step).
        rec: dict[str, Any] = {
            "item_id": iid,
            "title": str(it.get("title") or it.get("goal") or "")[:80],
            "item_type": it.get("item_type"),
            "target_files": list(it.get("target_files") or []),
            "patch_task_kind": it.get("patch_task_kind"),
            "generated": has,
            "gen_status": g.get("status"),
            "gen_warnings": list(g.get("warnings") or [])[:6],
            "gen_reason": (((g.get("metadata") or {}).get("patch_generation") or {}).get("reason_code")),
        }
        print(f"[item] {iid} type={rec['item_type']} targets={rec['target_files']} kind={rec['patch_task_kind']} title={rec['title']!r}", flush=True)
        if not has:
            print(f"       NO CONTENT: status={rec['gen_status']} reason={rec['gen_reason']} warnings={rec['gen_warnings']}", flush=True)
        if has:
            _post(client, "/api/atlas/patch-proposals/decide", {
                "pool_id": pool_id, "item_id": iid, "workspace_id": wsid, "decision": "approved", "reason": "interleaved"})
            one = _post(client, "/api/atlas/multi-item-autopilot/run", {
                "pool_id": pool_id, "workspace_id": wsid, "item_ids": [iid],
                "policy_id": "full_auto_multi_item_v1", "dry_run": False, "require_approval": False,
                "include_context_refresh": True, "include_evaluator": True, "include_bounded_retry": True,
                "include_self_correction": True, "self_correction_max_attempts": 2,
                "max_items": 1, "max_changed_files_total": 25})
            ir = (list(one.get("item_results") or []) or [{}])[0]
            rec["apply_status"] = ir.get("status")
            rec["apply_reason"] = ir.get("reason")
            rec["autopilot_status"] = one.get("status")
            # Capture the ACTUAL executor block reason + content mode so safe_apply_not_applied is diagnosable.
            sar = ir.get("safe_apply_result") or {}
            file_results = (sar.get("safe_apply_result") or {}).get("file_results") or (sar.get("metadata") or {}).get("file_results") or []
            rec["block_reasons"] = sorted({str(fr.get("reason")) for fr in file_results if isinstance(fr, dict) and fr.get("reason")})
            rec["sar_warnings"] = list((sar.get("warnings") or []))[:5]
            md = (((g.get("plan_pool") or {}).get("items") or [{}]))
            it_meta = next((x.get("metadata") or {} for x in md if x.get("item_id") == iid), {})
            rec["content_mode"] = (it_meta.get("file_changes") and "file_changes") or (it_meta.get("edits") and "edits") or (it_meta.get("unified_diff_preview") and "unified_diff") or (it_meta.get("proposed_content") and "full_content") or "?"
            if rec["apply_status"] not in ("applied", "completed"):
                print(f"       BLOCK {iid}: status={rec['apply_status']} mode={rec['content_mode']} reasons={rec['block_reasons']} warns={rec['sar_warnings']}", flush=True)
        per_item.append(rec)
        print(f"[interleaved] {iid}: generated={rec.get('generated')} apply={rec.get('apply_status')} reason={rec.get('apply_reason')}", flush=True)

    # Save the final built file + a coherence check (does it contain the contract entities and wire
    # them in a loop?) — this measures INTEGRATION QUALITY, which apply-rate does not.
    final_html = (ws / "index.html").read_text(encoding="utf-8") if (ws / "index.html").is_file() else ""
    out_html = output_json.with_suffix(".index.html")
    try:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        out_html.write_text(final_html, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    contract = ((revised.get("plan_pool") or {}).get("metadata") or {}).get("app_interface_contract") or {}
    entity_names = [str(e.get("name") or "") for e in (contract.get("entities") or []) if str(e.get("name") or "")]
    lc = final_html.lower()
    present = [n for n in entity_names if n and n.lower() in lc]
    rep["final_html_len"] = len(final_html)
    rep["contract_entities"] = entity_names
    rep["contract_entities_present_in_final"] = present
    rep["has_game_loop"] = any(k in lc for k in ("requestanimationframe", "setinterval(", "gameloop", "function update", "function draw"))
    rep["saved_html"] = str(out_html)
    print(f"[coherence] entities={entity_names} present={present} game_loop={rep['has_game_loop']} html_len={len(final_html)}", flush=True)
    rep["per_item"] = per_item
    generated = [r for r in per_item if r.get("generated")]
    applied = [r for r in generated if str(r.get("apply_status")) in {"applied", "completed"} or r.get("apply_reason") == "safe_apply_drift_recovered"]
    not_applied = [r for r in generated if r not in applied]
    rep["summary"] = {"generated": len(generated), "applied": len(applied), "not_applied": len(not_applied)}
    rep["status"] = "ok_no_drift" if (generated and not not_applied) else ("has_failures" if generated else "no_generation")
    rep["finished_at"] = _now()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_codegen_eval" / "verify_interleaved.json")
    args = p.parse_args()
    r = run(args.output_json)
    print(json.dumps({"status": r.get("status"), "summary": r.get("summary")}, ensure_ascii=False))
