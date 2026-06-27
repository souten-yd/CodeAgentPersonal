from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL_JS = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    marker = f"function {name}"
    start = source.index(marker)
    paren = source.index("(", start)
    depth = 0
    close_paren = -1
    for pos in range(paren, len(source)):
        char = source[pos]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                close_paren = pos
                break
    assert close_paren > -1
    brace = source.index("{", close_paren)
    depth = 0
    for pos in range(brace, len(source)):
        char = source[pos]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1:pos]
    raise AssertionError(f"{name} body not found")


def test_project_restore_cross_contamination_recovery_keys_are_project_scoped():
    assert "const STORAGE_LAST_POOL_ID_KEY = 'atlas_claude_last_pool_id';" in PANEL_JS
    assert "const STORAGE_LAST_RUN_ID_KEY = 'atlas_claude_last_run_id';" in PANEL_JS
    assert "const STORAGE_LAST_EVENT_SEQUENCE_KEY = 'atlas_claude_last_event_sequence';" in PANEL_JS
    assert "function projectScopedStorageKey" in PANEL_JS
    assert "function projectInstanceId" in PANEL_JS
    assert "const instance = String(projectInstanceId() || '').trim();" in PANEL_JS
    assert "return instance ? `${workspace}:${instance}` : workspace;" in PANEL_JS
    assert "`atlas_claude:${encodeURIComponent(scope)}:${suffix}`" in PANEL_JS
    assert "function setProjectScopedHint" in PANEL_JS
    assert "function getProjectScopedHint" in PANEL_JS
    assert "function removeProjectScopedHints" in PANEL_JS


def test_project_restore_cross_contamination_activate_can_restore_global_pool_without_project():
    body = _function_body(PANEL_JS, "activate")
    assert "if (projectName())" in body
    assert "loadProject(projectName())" in body
    assert "getProjectScopedHint(STORAGE_LAST_POOL_ID_KEY)" in body
    assert "renderPlanPoolMarkdown(lastPoolId)" in body
    assert "restoreLatestRun(lastPoolId)" in body


def test_project_restore_cross_contamination_runtime_progress_writes_scoped_hints():
    body = _function_body(PANEL_JS, "applyRuntimeProgressEvent")
    assert "setProjectScopedHint(STORAGE_LAST_POOL_ID_KEY, effectivePoolId)" in body
    assert "setProjectScopedHint(STORAGE_LAST_RUN_ID_KEY, runId)" in body
    assert "setProjectScopedHint(STORAGE_LAST_EVENT_SEQUENCE_KEY, String(sequence))" in body


def test_selected_project_without_pool_clears_visible_plan_before_empty_prompt():
    body = _function_body(PANEL_JS, "loadProject")
    assert "dom.transcript.innerHTML = ''" in body
    assert "state.transcript = []" in body
    assert "getContinuationLatest(wsId, projectInstanceId())" in body
    assert "removeProjectScopedHints(state.activeProject.workspaceId || target)" in body
    assert "pushSystemMessage('指示を入力してください')" in body


def test_project_restore_cross_contamination_selected_project_uses_scoped_recovery_keys():
    assert "function projectScopedStorageKey" in PANEL_JS
    assert "function setProjectScopedHint" in PANEL_JS
    assert "function getProjectScopedHint" in PANEL_JS
    assert "function removeProjectScopedHints" in PANEL_JS
    assert "localStorage.setItem(STORAGE_LAST_POOL_ID_KEY" not in PANEL_JS
    assert "localStorage.getItem(STORAGE_LAST_RUN_ID_KEY" not in PANEL_JS


def test_legacy_global_recovery_hint_is_read_only_no_project_fallback():
    helper_body = _function_body(PANEL_JS, "getProjectScopedHint")
    assert "if (key) return localStorage.getItem(key) || '';" in helper_body
    assert "return localStorage.getItem(baseKey) || '';" in helper_body
    assert "localStorage.setItem(baseKey" not in PANEL_JS


def test_deleted_recreated_project_restore_uses_project_instance_id():
    assert "projectInstanceId: project.projectInstanceId || project.project_instance_id || ''" in PANEL_JS
    assert "project_instance_id: projectInstanceId()" in PANEL_JS
    assert "getPlanRuntimeStatus(poolId, workspaceId(), projectInstanceId())" in PANEL_JS
    assert "getPlanPool(poolId, workspaceId(), projectInstanceId())" in PANEL_JS
    assert "getPlanPoolMarkdown(poolId, workspaceId(), projectInstanceId())" in PANEL_JS
    assert "getLatestMultiItemAutopilotResult({ pool_id: poolId, workspace_id: workspaceId(), project_instance_id: projectInstanceId() })" in PANEL_JS
    assert "clearProjectHints" in PANEL_JS
