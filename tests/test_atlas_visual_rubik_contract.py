from __future__ import annotations

from pathlib import Path

import pytest

from agent.atlas_visual_artifact_verifier import AtlasVisualArtifactVerifier
from agent.atlas_visual_contract_registry import VisualContractRegistry
from agent.atlas_visual_requirement_normalizer import VisualRequirementNormalizer
from agent.atlas_visual_task_classifier import VisualTaskClassifier


RUBIK_JA = (
    "ルービックキューブを解くプログラムをHTMLで作って。"
    "初期状態はランダムで、ボタンを押すと自動で順次操作されて色が全面揃うようにして。"
)
RUBIK_EN = "Create an HTML Rubik cube solver with a random initial state and a button that solves it step by step."

_normalizer = VisualRequirementNormalizer()
_classifier = VisualTaskClassifier()
_registry = VisualContractRegistry()


def _classify(text: str):
    normalized = _normalizer.normalize(text)
    return normalized, _classifier.classify(normalized, text)


def test_rubik_solver_canvas_overrequirement_current_request_does_not_explicitly_require_canvas():
    for text in (RUBIK_JA, RUBIK_EN):
        normalized, classification = _classify(text)
        contract = _registry.select(classification)
        assert "canvas_required" not in normalized.runtime_requirements
        assert "canvas_required" not in classification.runtime_requirements
        assert "canvas_exists" not in contract.required_signals


@pytest.mark.xfail(
    strict=True,
    reason="RV4 must classify Rubik HTML solver requests as interactive web app or UI component.",
)
@pytest.mark.parametrize("text", [RUBIK_JA, RUBIK_EN])
def test_rubik_solver_canvas_overrequirement_expected_interactive_classification(text: str):
    _normalized, classification = _classify(text)
    contract = _registry.select(classification)

    assert classification.artifact_type in {"interactive_web_app", "ui_component"}
    assert "browser_required" in classification.runtime_requirements
    assert "input_required" in classification.runtime_requirements
    assert "canvas_required" not in classification.runtime_requirements
    assert contract.contract_id in {"interactive_web_app_visual_v1", "ui_component_visual_v1"}
    assert "canvas_exists" not in contract.required_signals


def test_rubik_solver_canvas_overrequirement_wrong_canvas_contract_reproduces_missing_canvas(tmp_path: Path):
    html_path = tmp_path / "index.html"
    html_path.write_text(_dom_rubik_solver_html(), encoding="utf-8")
    canvas_contract = _registry.get("canvas_animation_visual_v1")
    assert canvas_contract is not None

    result = AtlasVisualArtifactVerifier().verify_static(
        html_path,
        task_description=RUBIK_JA,
        contract=canvas_contract,
    )

    assert result["status"] == "failed"
    assert result["contract_id"] == "canvas_animation_visual_v1"
    assert "canvas_exists" in result["missing"]


def test_rubik_solver_canvas_overrequirement_dom_solver_is_not_missing_canvas_for_non_canvas_contract(tmp_path: Path):
    html_path = tmp_path / "index.html"
    html_path.write_text(_dom_rubik_solver_html(), encoding="utf-8")
    app_contract = _registry.get("interactive_web_app_visual_v1")
    assert app_contract is not None

    result = AtlasVisualArtifactVerifier().verify_static(
        html_path,
        task_description=RUBIK_JA,
        contract=app_contract,
    )

    assert result["contract_id"] == "interactive_web_app_visual_v1"
    assert "canvas_exists" not in result["missing"]


@pytest.mark.xfail(
    strict=True,
    reason="RV4 must recognize explicit Japanese canvas wording for Rubik tasks.",
)
def test_explicit_canvas_rubik_request_still_requires_canvas():
    _normalized, classification = _classify("canvasでルービックキューブを描画して")
    contract = _registry.select(classification)
    assert "canvas_required" in classification.runtime_requirements
    assert contract.contract_id in {"canvas_animation_visual_v1", "canvas_game_visual_v1"}
    assert "canvas_exists" in contract.required_signals


def _dom_rubik_solver_html() -> str:
    return """<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>Rubik Solver</title>
</head>
<body>
  <main data-atlas-state="scrambled">
    <section class="cube" aria-label="rubik cube">
      <div class="face red"></div>
      <div class="face blue"></div>
      <div class="face green"></div>
      <div class="face yellow"></div>
      <div class="face white"></div>
      <div class="face orange"></div>
    </section>
    <button id="solve">solve step</button>
  </main>
  <script>
    document.getElementById('solve').addEventListener('click', () => {
      document.querySelector('main').dataset.atlasState = 'solved';
    });
  </script>
</body>
</html>
"""
