from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.atlas_auto_verification_service import AtlasAutoVerificationService


ROOT = Path(__file__).resolve().parents[1]
PANEL_JS = (ROOT / "web" / "js" / "atlas_claude_panel.js").read_text(encoding="utf-8")


class _Journal:
    def append_event(self, *args, **kwargs):
        return None

    def save_plan_pool(self, pool):
        return None


class _Storage:
    def load_pool(self, _pool_id):
        raise AssertionError("not used")

    def save_pool(self, _pool):
        return None


class _Runner:
    def run_command(self, *args, **kwargs):
        return SimpleNamespace(status="passed", returncode=0, stdout="", stderr="", warnings=[], errors=[])


class _FakeSmoke:
    def verify(self, *args, **kwargs):
        return {"status": "browser_smoke_failed", "reason": "canvas_frame_not_detected:no_frame_change"}


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


def test_visual_contract_metadata_includes_contract_classification_and_signal_diagnostics(tmp_path: Path):
    html_path = tmp_path / "index.html"
    html_path.write_text("<!doctype html><html><body><p>No canvas here</p></body></html>", encoding="utf-8")
    svc = AtlasAutoVerificationService(
        journal=_Journal(),
        storage=_Storage(),
        command_runner=_Runner(),
        playwright_verifier=_FakeSmoke(),
    )

    evidence = svc._evaluate_visual(
        html_path,
        "canvasでルービックキューブを描画して",
        classification_desc="canvasでルービックキューブを描画して",
    )
    visual = svc._visual_contract_metadata(evidence)

    assert visual["contract_id"] == "canvas_animation_visual_v1"
    assert visual["artifact_type"] == "canvas_animation"
    assert "canvas_exists" in visual["required_signals"]
    assert "canvas_exists" in visual["missing_signals"]
    assert visual["classification_context"] == "canvasでルービックキューブを描画して"
    assert "canvas" in visual["source_phrases"]


def test_runtime_failure_summary_renders_visual_contract_diagnostics():
    body = _function_body(PANEL_JS, "visualFailureDetails")
    assert "visual_contract=${contractId}" in body
    assert "artifact_type=${artifactType}" in body
    assert "required=${required.join(', ')}" in body
    assert "missing=${missing.join(', ')}" in body
    assert "classification_context=${context.slice(0, 160)}" in body


def test_runtime_failure_summary_uses_missing_signals_before_legacy_missing():
    body = _function_body(PANEL_JS, "visualFailureDetails")
    assert "const missingSource = Array.isArray(visual.missing_signals) ? visual.missing_signals : visual.missing;" in body
