"""Element-level real-LLM evaluation of Atlas patch generation, per patch type.

Drives `AtlasPatchProposalService.propose_for_item` with the CONFIGURED local model
(`main._phase1_llm_json`) and then applies the produced proposal through
`AtlasFileSafeApplyExecutor`, isolating each patch *intent* in its own temp workspace:

  create  -> brand new file (full_content)
  replace -> rewrite an existing file wholesale (full_content)
  edit    -> surgical old->new replacement, preserve surroundings
  insert  -> add new code anchored after an existing snippet
  delete  -> remove a block/lines from an existing file (action_type=update)
  diff    -> change requested as a unified diff
  append  -> add a trailing section, preserve existing content

For each scenario we record: whether the LLM was called, the content_mode it chose,
the safe-apply status/reasons, deterministic must_contain / must_absent checks against
the resulting file, and an LLM-as-judge verdict (requirement vs produced file).

This is honest live evidence: if the configured model is unreachable, the run is
recorded as `blocked` (NOT passed). Everything happens in temp workspaces; the real
repository is never mutated.

Usage:
    python tools/run_codegen_patchtype_eval.py [--output-json PATH] [--only NAME,NAME]
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

import main  # noqa: E402  (configured-model llm_json_fn lives here)
from agent.atlas_file_safe_apply_executor import AtlasFileSafeApplyExecutor  # noqa: E402
from agent.atlas_journal import AtlasJournal  # noqa: E402
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest  # noqa: E402
from agent.atlas_patch_proposal_service import AtlasPatchProposalService  # noqa: E402
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool  # noqa: E402
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Scenario catalogue ────────────────────────────────────────────────────────
# Each scenario isolates ONE patch intent. `seed` pre-creates files so the service
# sees an existing target (steering the prompt toward edits/insert) or an empty
# workspace (steering toward full_content). `must_contain` / `must_absent` are
# deterministic post-apply assertions on the resulting target file.

_SEED_APP = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def multiply(a, b):\n"
    "    return a * b\n"
    "\n"
    "def legacy_unused():\n"
    "    # obsolete helper kept only for history\n"
    "    return 'legacy'\n"
)

SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "create_new_file",
        "intent": "create",
        "action_type": "create",
        "targets": ["index.html"],
        "title": "Create counter page",
        "goal": (
            "Create index.html: a complete standalone HTML page with the exact heading "
            "'Atlas Patch Eval' and a button labelled 'Add' that increments a numeric counter "
            "shown in an element with id='count', starting at 0. Use a real inline <script> with "
            "working click handling. No placeholders."
        ),
        "acceptance": ["Heading 'Atlas Patch Eval' renders", "Clicking Add increments #count"],
        "must_contain": ["Atlas Patch Eval", "count"],
        "judge": "The page shows heading 'Atlas Patch Eval' and a working Add button that increments a counter in #count.",
    },
    {
        "name": "full_replace",
        "intent": "replace",
        "action_type": "update",
        "seed": {"index.html": "<!doctype html><html><body><h1>Old Placeholder</h1></body></html>\n"},
        "targets": ["index.html"],
        "title": "Replace landing page",
        "goal": (
            "Rewrite index.html completely so it shows the exact heading 'Replaced Landing' and a "
            "paragraph 'status: ready'. The previous 'Old Placeholder' heading MUST be gone."
        ),
        "acceptance": ["Heading 'Replaced Landing' renders", "'Old Placeholder' no longer present"],
        "must_contain": ["Replaced Landing", "ready"],
        "must_absent": ["Old Placeholder"],
        "judge": "index.html now shows 'Replaced Landing' and a ready status, and the old placeholder is gone.",
    },
    {
        "name": "edit_replace",
        "intent": "edit",
        "action_type": "update",
        "seed": {"app.py": _SEED_APP},
        "targets": ["app.py"],
        "title": "Fix add() semantics",
        "goal": (
            "In app.py, change ONLY the add(a, b) function so it returns a - b (subtraction) instead "
            "of a + b. Do NOT modify multiply() or legacy_unused(). Preserve all other code exactly."
        ),
        "acceptance": ["add returns a - b", "multiply and legacy_unused unchanged"],
        "must_contain": ["a - b", "def multiply", "def legacy_unused"],
        "judge": "Only add() was changed to return a - b; multiply() and legacy_unused() are preserved verbatim.",
    },
    {
        "name": "insert_block",
        "intent": "insert",
        "action_type": "update",
        "seed": {"app.py": _SEED_APP},
        "targets": ["app.py"],
        "title": "Add subtract() helper",
        "goal": (
            "In app.py, ADD a new function subtract(a, b) that returns a - b, inserted after the "
            "existing add() function. Do NOT modify or remove any existing function."
        ),
        "acceptance": ["subtract(a, b) exists and returns a - b", "existing functions preserved"],
        "must_contain": ["def subtract", "def add", "def multiply", "def legacy_unused"],
        "judge": "A new subtract() returning a - b was added; all pre-existing functions remain intact.",
    },
    {
        "name": "delete_block",
        "intent": "delete",
        "action_type": "update",
        "seed": {"app.py": _SEED_APP},
        "targets": ["app.py"],
        "title": "Remove obsolete helper",
        "goal": (
            "In app.py, REMOVE the entire legacy_unused() function (its def line and body). Keep add() "
            "and multiply() exactly as they are. The identifier 'legacy_unused' must no longer appear."
        ),
        "acceptance": ["legacy_unused removed", "add and multiply preserved"],
        "must_contain": ["def add", "def multiply"],
        "must_absent": ["legacy_unused"],
        "judge": "The legacy_unused() function was fully removed while add() and multiply() are preserved.",
    },
    {
        "name": "unified_diff",
        "intent": "diff",
        "action_type": "update",
        "seed": {"config.py": "DEBUG = False\nNAME = 'atlas'\nRETRIES = 3\n"},
        "targets": ["config.py"],
        "title": "Toggle DEBUG via diff",
        "goal": (
            "In config.py, change the line 'DEBUG = False' to 'DEBUG = True'. Express the change as a "
            "unified_diff patch (return a 'unified_diff_preview' with proper @@ hunks). Keep NAME and "
            "RETRIES unchanged."
        ),
        "acceptance": ["DEBUG = True", "NAME and RETRIES unchanged"],
        "must_contain": ["DEBUG = True", "NAME = 'atlas'", "RETRIES = 3"],
        "must_absent": ["DEBUG = False"],
        "judge": "config.py now has DEBUG = True with NAME and RETRIES unchanged.",
    },
    {
        "name": "append_section",
        "intent": "append",
        "action_type": "update",
        "seed": {"NOTES.md": "# Project Notes\n\nExisting baseline content line.\n"},
        "targets": ["NOTES.md"],
        "title": "Append changelog section",
        "goal": (
            "Append a new section to the END of NOTES.md: a '## Changelog' heading followed by one "
            "bullet '- initial eval entry'. PRESERVE all existing content above it unchanged."
        ),
        "acceptance": ["Changelog section appended", "existing content preserved"],
        "must_contain": ["# Project Notes", "Existing baseline content line", "## Changelog", "initial eval entry"],
        "judge": "A '## Changelog' section with the initial entry was appended while the original notes are preserved.",
    },
]


def _detect_content_mode(item_metadata: dict[str, Any]) -> str:
    fcs = item_metadata.get("file_changes")
    if isinstance(fcs, list) and fcs:
        modes = sorted({str(fc.get("content_mode") or "?") for fc in fcs if isinstance(fc, dict)})
        return "file_changes:" + ",".join(modes)
    if isinstance(item_metadata.get("edits"), list) and item_metadata.get("edits"):
        return "edits"
    if item_metadata.get("unified_diff_preview") or item_metadata.get("patch"):
        return "unified_diff"
    if item_metadata.get("proposed_content"):
        return "full_content"
    return "none"


_JUDGE_SYSTEM = (
    "You are a strict senior code reviewer. Given a requirement and the resulting file content, "
    "judge whether the requirement is fully and correctly satisfied with real, working, complete "
    "code (no placeholders, no stubs, no truncation). Return ONLY a JSON object: "
    '{"verdict":"pass"|"fail","score":0-100,"reasons":["..."]}'
)


def _judge(requirement: str, target: str, content: str) -> dict[str, Any]:
    fn = getattr(main, "_phase1_llm_json", None)
    if not callable(fn):
        return {"verdict": "unavailable", "score": 0, "reasons": ["judge_llm_unavailable"]}
    user = (
        f"Requirement:\n{requirement}\n\nFile: {target}\n--- BEGIN CONTENT ---\n"
        f"{content[:8000]}\n--- END CONTENT ---\n\nReturn the JSON verdict only."
    )
    try:
        out = fn(_JUDGE_SYSTEM, user)
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "error", "score": 0, "reasons": [str(exc)[:160]]}
    if not isinstance(out, dict):
        return {"verdict": "error", "score": 0, "reasons": ["judge_returned_no_json"]}
    verdict = str(out.get("verdict") or "").lower()
    return {
        "verdict": verdict if verdict in {"pass", "fail"} else "fail",
        "score": int(out.get("score") or 0) if str(out.get("score") or "").lstrip("-").isdigit() else 0,
        "reasons": [str(r)[:200] for r in (out.get("reasons") or [])][:6],
    }


def run_scenario(scn: dict[str, Any]) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "name": scn["name"],
        "intent": scn["intent"],
        "started_at": _now(),
        "llm_called": False,
        "proposal_status": None,
        "content_mode": None,
        "apply_status": None,
        "apply_reasons": [],
        "deterministic_ok": None,
        "deterministic_failures": [],
        "judge": None,
        "result": "fail",
        "errors": [],
    }
    tmp = tempfile.mkdtemp(prefix=f"ptype-{scn['name']}-")
    ws = Path(tmp) / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    ca = Path(tmp) / "ca"
    for rel, content in (scn.get("seed") or {}).items():
        (ws / rel).parent.mkdir(parents=True, exist_ok=True)
        (ws / rel).write_text(content, encoding="utf-8")

    item = AtlasPlanItem(
        item_id="i",
        pool_id="p",
        title=scn["title"],
        goal=scn["goal"],
        item_type="implementation",
        status="ready",
        risk_level="low",
        target_files=list(scn["targets"]),
        acceptance_criteria=list(scn.get("acceptance") or []),
        done_definition=list(scn.get("acceptance") or []),
        metadata={"action_type": scn["action_type"], "acceptance_criteria": list(scn.get("acceptance") or [])},
    )
    pool = AtlasPlanPool(
        pool_id="p",
        root_goal=scn["goal"],
        project_path=str(ws),
        status="ready",
        automation_level="full_autopilot",
        items=[item],
        metadata={"original_user_request": scn["goal"]},
    )
    storage = AtlasPlanPoolStorage(ca)
    journal = AtlasJournal(ca)
    storage.save_pool(pool)
    journal.save_plan_pool(pool)

    service = AtlasPatchProposalService(journal=journal, storage=storage, llm_json_fn=main._phase1_llm_json)
    try:
        result = service.propose_for_item(
            AtlasPatchProposalRequest(pool_id="p", item_id="i", source_type="plan_item")
        )
    except Exception as exc:  # noqa: BLE001
        rec["errors"].append(f"propose_exception:{exc}")
        rec["finished_at"] = _now()
        return rec

    rec["llm_called"] = True
    rec["proposal_status"] = result.status

    # Authoritative post-mark pool (content wired onto the item by mark_item_from_patch_proposal).
    try:
        pool2 = AtlasPlanPool.model_validate(result.plan_pool) if result.plan_pool else storage.load_pool("p")
    except Exception:  # noqa: BLE001
        pool2 = storage.load_pool("p")
    item2 = pool2.get_item("i")
    if item2 is None:
        rec["errors"].append("item_missing_after_proposal")
        rec["finished_at"] = _now()
        return rec
    rec["content_mode"] = _detect_content_mode(item2.metadata or {})

    apply_res = AtlasFileSafeApplyExecutor(workspace_root=ws).apply_plan_item_safe(item=item2, pool=pool2)
    rec["apply_status"] = apply_res.get("status")
    rec["apply_reasons"] = list(apply_res.get("reasons") or [])
    rec["apply_summary"] = apply_res.get("summary")

    target_path = ws / scn["targets"][0]
    final = target_path.read_text(encoding="utf-8") if target_path.is_file() else ""
    rec["final_len"] = len(final)

    failures: list[str] = []
    for needle in scn.get("must_contain") or []:
        if needle not in final:
            failures.append(f"missing:{needle}")
    for needle in scn.get("must_absent") or []:
        if needle in final:
            failures.append(f"present:{needle}")
    rec["deterministic_failures"] = failures
    rec["deterministic_ok"] = (rec["apply_status"] == "applied") and not failures

    rec["judge"] = _judge(scn["judge"], scn["targets"][0], final)

    rec["result"] = "pass" if (rec["deterministic_ok"] and rec["judge"].get("verdict") == "pass") else "fail"
    rec["finished_at"] = _now()
    return rec


def main_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Per-patch-type real-LLM codegen evaluation.")
    parser.add_argument("--output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_codegen_eval" / "patchtype_eval.json")
    parser.add_argument("--only", type=str, default="", help="Comma-separated scenario names to run.")
    args = parser.parse_args(argv)

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    scenarios = [s for s in SCENARIOS if not only or s["name"] in only]

    # Preflight: configured model must answer JSON, else record blocked (not passed).
    probe = None
    try:
        probe = main._phase1_llm_json("Return one valid JSON object only.", 'Return exactly {"status":"ok"} as JSON.')
    except Exception as exc:  # noqa: BLE001
        probe = {"error": str(exc)[:160]}
    report: dict[str, Any] = {
        "kind": "patchtype_eval",
        "started_at": _now(),
        "llm_url_planner": str(getattr(main, "LLM_URL_PLANNER", "")),
        "model_probe": probe,
        "scenarios": [],
    }
    if not isinstance(probe, dict):
        report["status"] = "blocked"
        report["blocked_reason"] = "configured_model_unavailable"
        report["finished_at"] = _now()
        _write(args.output_json, report)
        print(json.dumps({"status": "blocked", "reason": "configured_model_unavailable"}, ensure_ascii=False))
        return 2

    for scn in scenarios:
        print(f"[patchtype] running {scn['name']} ({scn['intent']}) ...", flush=True)
        rec = run_scenario(scn)
        report["scenarios"].append(rec)
        print(
            f"  -> result={rec['result']} apply={rec['apply_status']} mode={rec['content_mode']} "
            f"judge={(rec['judge'] or {}).get('verdict')} det_fail={rec['deterministic_failures']}",
            flush=True,
        )

    passed = sum(1 for r in report["scenarios"] if r["result"] == "pass")
    total = len(report["scenarios"])
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
