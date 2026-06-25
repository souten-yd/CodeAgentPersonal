from pathlib import Path

from agent.atlas_journal import AtlasJournal
from app.atlas.workflow_state_contract import build_read_only_workflow_state


ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")
API = (ROOT / "web" / "js" / "atlas_pipeline_api.js").read_text(encoding="utf-8")
WORKFLOW_API = (ROOT / "app" / "api" / "atlas_workflow_state.py").read_text(encoding="utf-8")


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_sc6_browser_approval_path_uses_backend_run_api() -> None:
    body = _slice(PANEL, "async function approveAndRunPipeline(", "async function approveAndRunPipelineLegacyDisabled(")

    assert "root.AtlasPipelineAPI.createRun" in body
    assert "root.AtlasPipelineAPI.getRunStatus" in PANEL
    assert "root.AtlasPipelineAPI.getRunEvents" in PANEL
    assert "root.AtlasPipelineAPI.generatePatchProposal" not in body
    assert "root.AtlasPipelineAPI.decidePatchProposal" not in body
    assert "root.AtlasPipelineAPI.runMultiItemAutopilot" not in body


def test_sc0_direct_patch_apply_verify_endpoints_exist_in_browser_api() -> None:
    assert "/api/atlas/patch-proposals/generate" in API
    assert "/api/atlas/patch-proposals/decide" in API
    assert "/api/atlas/automation/safe-apply-one-and-verify" in API
    assert "/api/atlas/multi-item-autopilot/run" in API


def test_sc0_pipeline_progress_events_are_replayable_after_cursor(tmp_path: Path) -> None:
    journal = AtlasJournal(tmp_path, workspace_id="default")
    first = journal.append_progress_event("pool_sc0", "run_sc0", {"event_type": "queued", "phase": "plan"})
    second = journal.append_progress_event("pool_sc0", "run_sc0", {"event_type": "running", "phase": "patch"})
    third = journal.append_progress_event("pool_sc0", "run_sc0", {"event_type": "verifying", "phase": "verify"})

    assert [event["sequence"] for event in (first, second, third)] == [1, 2, 3]
    replay = journal.read_progress_events("pool_sc0", "run_sc0", after_sequence=1)
    assert [event["event_type"] for event in replay] == ["running", "verifying"]
    assert journal.load_latest_progress("pool_sc0", "run_sc0")["sequence"] == 3


def test_sc0_workflow_state_endpoint_is_get_only_and_backend_read_only() -> None:
    assert '@router.get("/workflow-state/read-only")' in WORKFLOW_API
    assert '@router.post("/workflow-state/read-only")' not in WORKFLOW_API
    assert '@router.put("/workflow-state/read-only")' not in WORKFLOW_API
    assert '@router.delete("/workflow-state/read-only")' not in WORKFLOW_API

    payload = build_read_only_workflow_state(
        goal="baseline",
        project_path="project",
        phase="preview",
        status="read only",
        primary_cta_label="Inspect",
        available_actions=[{"id": "execute", "label": "Execute", "kind": "mutation"}],
    )
    assert payload["source"] == "backend_contract"
    assert payload["backend_workflow_state_authoritative"] is True
    assert payload["vue_source_of_truth"] is False
    assert payload["vue_execution_enabled"] is False
    assert payload["autonomous_execution_enabled"] is False
    assert payload["primary_cta"]["read_only"] is True
    assert payload["primary_cta"]["enabled"] is False
    assert all(action["read_only"] is True and action["enabled"] is False for action in payload["available_actions"])
