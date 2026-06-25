from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")


def _slice(text: str, start_marker: str, end_marker: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def _function_body(name: str) -> str:
    marker = f"function {name}"
    start = PANEL.index(marker)
    paren = PANEL.index("(", start)
    depth = 0
    close_paren = -1
    for pos in range(paren, len(PANEL)):
        char = PANEL[pos]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_paren = pos
                break
    assert close_paren > -1
    brace = PANEL.index("{", close_paren)
    depth = 0
    for pos in range(brace, len(PANEL)):
        char = PANEL[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return PANEL[brace + 1:pos]
    raise AssertionError(f"{name} body not found")


def test_loaded_approval_path_has_no_direct_browser_orchestration_calls() -> None:
    body = _function_body("approveAndRunPipeline")
    forbidden = [
        "generatePatchProposal(",
        "decidePatchProposal(",
        "runMultiItemAutopilot(",
    ]
    for token in forbidden:
        assert token not in body
    assert "root.AtlasPipelineAPI.createRun" in body
    assert "watchBackendRun(poolId, runId, stages)" in body


def test_legacy_approval_function_is_hard_disabled_before_direct_calls() -> None:
    body = _function_body("approveAndRunPipelineLegacyDisabled")
    guard = body.index("legacy_ui_orchestration_disabled")
    for token in [
        "generatePatchProposal(",
        "decidePatchProposal(",
        "runMultiItemAutopilot(",
    ]:
        assert token in body
        assert guard < body.index(token)


def test_visible_approval_buttons_call_backend_run_path() -> None:
    approval_region = _slice(PANEL, "async function approveAndRunPipeline(", "async function approveAndRunPipelineLegacyDisabled(")
    assert "root.AtlasPipelineAPI.createRun" in approval_region
    assert "approveAndRunPipelineLegacyDisabled(" not in PANEL.replace("async function approveAndRunPipelineLegacyDisabled(", "")
