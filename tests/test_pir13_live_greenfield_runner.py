from __future__ import annotations

from pathlib import Path

import main
from tools import run_pir13_live_greenfield as runner


def _synthetic_greenfield_model(_system_prompt: str, _user_prompt: str) -> dict:
    implementation_steps = [
        {
            "step_id": "html",
            "title": "Create index.html",
            "description": "Create a single HTML page with a visible ready status.",
            "action_type": "create",
            "risk_level": "low",
            "target_files": ["index.html"],
            "acceptance_criteria": ["index.html contains Atlas Live Greenfield Ready."],
        }
    ]
    return {
        "status": "planned",
        "implementation_steps": implementation_steps,
        "plan": {
            "root_goal": runner.LIVE_GOAL,
            "requirements": [
                {
                    "id": "REQ-LIVE",
                    "text": "Render Atlas Live Greenfield Ready in index.html.",
                }
            ],
            "implementation_steps": implementation_steps,
        },
        "summary": "Create a live Greenfield HTML status page.",
        "proposed_fix": "Write index.html with Atlas Live Greenfield Ready.",
        "target_files": ["index.html"],
        "risk_level": "low",
        "proposed_content": (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "<head><meta charset=\"utf-8\"><title>Atlas Live Greenfield</title></head>\n"
            "<body><main><h1>Atlas Live Greenfield Ready</h1><p id=\"status\">ready</p></main></body>\n"
            "</html>\n"
        ),
        "suggested_changes": [{"path": "index.html", "action": "create"}],
        "verification_plan": ["Assert index.html contains Atlas Live Greenfield Ready."],
        "rollback_plan": ["Delete index.html."],
    }


def test_live_runner_restart_evidence_path_with_synthetic_model(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(main, "_phase1_llm_json", _synthetic_greenfield_model)

    report = runner.run_live_greenfield(tmp_path / "workspace", tmp_path / "atlas_data")

    assert report["status"] == "passed", report
    assert report["restart_evidence"]["status"] == "passed"
    assert report["artifacts"]["pool_id"]
    assert report["artifacts"]["draft_item_id"]
    assert Path(report["artifacts"]["events_path"]).is_file()
    assert runner.REQUIRED_TEXT in (tmp_path / "workspace" / "index.html").read_text(
        encoding="utf-8"
    )
