from pathlib import Path

LUMEN_JS = Path("web/js/lumen.js")


def test_steps_render_diagnostics_are_logged_before_rendering():
    source = LUMEN_JS.read_text(encoding="utf-8")
    assert "steps_count:" in source
    assert "steps_types:" in source
    assert "steps_renderers: addStepsBlock=" in source


def test_tool_result_does_not_render_system_message_card():
    source = LUMEN_JS.read_text(encoding="utf-8")
    branch = source.split("} else if (event.type === 'tool_result') {", 1)[1].split("} else if (event.type === 'chat_step'", 1)[0]
    assert "renderSystemMessage" not in branch


def test_finish_job_calls_existing_steps_renderers_only():
    source = LUMEN_JS.read_text(encoding="utf-8")
    finish = source.split("async function finishJob", 1)[1].split("function startPolling", 1)[0]
    assert "addStepsBlock(state.steps)" in finish
    assert "renderStepsToOutput(state.steps)" in finish
    assert "function addStepsBlock" not in source
    assert "function renderStepsToOutput" not in source
