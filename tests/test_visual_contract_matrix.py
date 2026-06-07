from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.atlas_auto_verification_schema import AtlasAutoVerificationRequest
from agent.atlas_auto_verification_service import AtlasAutoVerificationService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_playwright_smoke_verifier import _is_animation_task as smoke_is_animation_task
from agent.atlas_visual_artifact_verifier import _is_animation_task_description as static_is_animation_task
from agent.atlas_visual_artifact_verifier import AtlasVisualArtifactVerifier
from agent.atlas_visual_contract_registry import VisualContractRegistry
from agent.atlas_visual_requirement_normalizer import VisualRequirementNormalizer
from agent.atlas_visual_task_classifier import VisualTaskClassifier
from tests.visual_fixtures import AUTOVERIFY_EXPECTATIONS, STATIC_EXPECTATIONS, write_fixture, FIXTURES

_norm = VisualRequirementNormalizer()
_clf = VisualTaskClassifier()
_reg = VisualContractRegistry()


class _Journal:
    def append_event(self, *args, **kwargs):
        return None

    def save_plan_pool(self, pool):
        return None


class _Storage:
    def __init__(self, pool):
        self.pool = pool

    def load_pool(self, _pool_id):
        return self.pool

    def save_pool(self, pool):
        self.pool = pool


class _Runner:
    def run_command(self, *args, **kwargs):
        return SimpleNamespace(
            status="passed",
            returncode=0,
            stdout="",
            stderr="",
            warnings=[],
            errors=[],
            model_dump=lambda: {"status": "passed"},
        )


class _FakeSmoke:
    def __init__(self, result: dict):
        self.result = result

    def verify(self, *args, **kwargs):
        return dict(self.result)


@pytest.mark.parametrize("case", STATIC_EXPECTATIONS, ids=lambda case: case.name + ":" + case.task_description)
def test_static_visual_contract_matrix(case, tmp_path):
    html_path = write_fixture(tmp_path, case.name)
    result = AtlasVisualArtifactVerifier().verify_static(html_path, task_description=case.task_description)

    assert result["status"] == case.expect_status, result
    passed = {check["check"] for check in result["checks"] if check["status"] == "passed"}
    missing = set(result["missing"])
    for check in case.must_pass_checks:
        assert check in passed, result
    for check in case.must_miss_checks:
        assert check in missing, result


@pytest.mark.parametrize("case", AUTOVERIFY_EXPECTATIONS, ids=lambda case: case.name + ":" + case.task_description)
def test_auto_verification_visual_matrix(case, tmp_path):
    html_path = write_fixture(tmp_path, case.name)
    pool, item = _pool_item(tmp_path, html_path=html_path, task_description=case.task_description)
    svc = AtlasAutoVerificationService(
        journal=_Journal(),
        storage=_Storage(pool),
        command_runner=_Runner(),
        playwright_verifier=_FakeSmoke(case.smoke),
    )

    out = svc.run_after_auto_safe_apply(AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id="run_1"))

    assert out.status == case.expect_status
    if case.expect_verify_level is not None:
        assert out.metadata.get("verify_level") == case.expect_verify_level
    else:
        assert "verify_level" not in out.metadata
    for warning in case.must_have_warnings:
        assert warning in out.warnings
    for warning in case.must_not_have_warnings:
        assert warning not in out.warnings


@pytest.mark.parametrize(
    ("task_description", "expected"),
    [
        ("show an inanimate object", False),
        ("animate a color wave", True),
        ("hue rotate", True),
        ("make it move around", True),
    ],
)
def test_static_and_smoke_animation_task_keywords_are_consistent(task_description, expected):
    assert static_is_animation_task(task_description) is expected
    assert smoke_is_animation_task(task_description) is expected


# ---------------------------------------------------------------------------
# Contract-aware verifier negative tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("task_description", "contract_id", "must_not_require"),
    [
        # Static page must NOT require animation_signal
        ("display a simple static page", "static_html_visual_v1", ["animation_signal"]),
        # Animated DOM must NOT require canvas_exists
        ("animate rainbow text fading", "animated_dom_visual_v1", ["canvas_exists"]),
        # Chart must NOT require animation_signal or game_loop_runs
        ("bar chart showing sales", "chart_visualization_v1", ["animation_signal", "game_loop_runs"]),
        # Canvas animation must NOT require game_loop_runs or hud_exists
        ("canvas animation of particles", "canvas_animation_visual_v1", ["game_loop_runs", "hud_exists"]),
    ],
)
def test_contract_does_not_require_unrelated_signals(task_description, contract_id, must_not_require):
    c = _reg.get(contract_id)
    assert c is not None
    for signal in must_not_require:
        assert signal not in c.required_signals, (
            f"Contract {contract_id} should not require {signal} for '{task_description}'"
        )


def test_registry_selects_specialized_contracts_for_known_visual_tasks():
    cases = {
        "display a static page": "static_html_visual_v1",
        "animate text colors": "animated_dom_visual_v1",
        "canvas particle animation no game": "canvas_animation_visual_v1",
        "bar chart visualization": "chart_visualization_v1",
        "canvas browser game with score and collision": "canvas_game_visual_v1",
    }
    for task, expected in cases.items():
        n = _norm.normalize(task)
        cls = _clf.classify(n, task)
        c = _reg.select(cls)
        assert c.contract_id == expected, f"Expected {expected} for '{task}'"


def test_static_html_contract_used_for_static_page(tmp_path):
    """Static page fixture gets static contract and passes — animation_signal is not required."""
    html_path = tmp_path / "index.html"
    html_path.write_text(FIXTURES["static_page_no_animation"], encoding="utf-8")
    n = _norm.normalize("display a simple static page")
    cls = _clf.classify(n, "display a simple static page")
    contract = _reg.select(cls)
    assert contract.contract_id == "static_html_visual_v1"
    result = AtlasVisualArtifactVerifier().verify_static(
        html_path, task_description="display a simple static page", contract=contract
    )
    assert result["status"] == "passed", result
    assert result.get("contract_id") == "static_html_visual_v1"
    # No animation signal required — should not appear in missing
    assert "animation_signal" not in result.get("missing", [])


def test_animated_dom_contract_does_not_require_canvas(tmp_path):
    """Animated DOM fixture passes with animated_dom contract — canvas is not required."""
    html_path = tmp_path / "index.html"
    html_path.write_text(FIXTURES["color_named_keyframes"], encoding="utf-8")
    contract = _reg.get("animated_dom_visual_v1")
    assert contract is not None
    result = AtlasVisualArtifactVerifier().verify_static(
        html_path, task_description="rainbow color animation", contract=contract
    )
    # canvas_exists must not be required by animated_dom contract
    assert "canvas_exists" not in result.get("missing", [])


def test_chart_contract_used_for_chart_fixture(tmp_path):
    """Chart fixture gets chart contract — animation signals are not required."""
    html_path = tmp_path / "index.html"
    html_path.write_text(FIXTURES["chart_bar"], encoding="utf-8")
    n = _norm.normalize("bar chart showing sales data")
    cls = _clf.classify(n, "bar chart showing sales data")
    contract = _reg.select(cls)
    assert contract.contract_id == "chart_visualization_v1"
    result = AtlasVisualArtifactVerifier().verify_static(
        html_path, task_description="bar chart", contract=contract
    )
    assert result.get("contract_id") == "chart_visualization_v1"
    # animation_signal is optional in universal contract — should NOT be required
    missing = result.get("missing", [])
    assert "animation_signal" not in missing


def test_ui_form_contract_used_for_form_fixture(tmp_path):
    """Form fixture gets UI contract — no game/canvas signals required."""
    html_path = tmp_path / "index.html"
    html_path.write_text(FIXTURES["ui_form"], encoding="utf-8")
    n = _norm.normalize("form with inputs and submit button")
    cls = _clf.classify(n, "form with inputs and submit button")
    contract = _reg.select(cls)
    assert contract.contract_id == "ui_component_visual_v1"
    result = AtlasVisualArtifactVerifier().verify_static(
        html_path, task_description="form", contract=contract
    )
    # Game signals must not be required
    missing = result.get("missing", [])
    assert "canvas_exists" not in missing
    assert "game_loop_runs" not in missing


def test_canvas_animation_contract_used_for_canvas_fixture(tmp_path):
    """Canvas balls fixture gets canvas animation contract — game signals not required."""
    html_path = tmp_path / "index.html"
    html_path.write_text(FIXTURES["canvas_balls"], encoding="utf-8")
    n = _norm.normalize("canvas animation of bouncing balls")
    cls = _clf.classify(n, "canvas animation of bouncing balls")
    contract = _reg.select(cls)
    assert contract.contract_id == "canvas_animation_visual_v1"
    # game_loop_runs must NOT be in required_signals for non-game canvas animation.
    assert "game_loop_runs" not in contract.required_signals


def test_pipeline_persists_contract_id_in_metadata(tmp_path):
    """End-to-end: auto-verification persists visual_contract_id in pool metadata."""
    html_path = tmp_path / "index.html"
    task_desc = "animate rainbow colors on the page"
    html_path.write_text(FIXTURES["color_named_keyframes"], encoding="utf-8")
    pool, item = _pool_item(tmp_path, html_path=html_path, task_description=task_desc)
    svc = AtlasAutoVerificationService(
        journal=_Journal(),
        storage=_Storage(pool),
        command_runner=_Runner(),
        playwright_verifier=_FakeSmoke({"status": "browser_smoke_passed"}),
    )
    out = svc.run_after_auto_safe_apply(
        AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id="run_1")
    )
    # Contract ID must be persisted
    assert out.metadata.get("visual_contract_id"), "visual_contract_id missing from metadata"
    # Classification must be persisted
    classification = out.metadata.get("visual_classification", {})
    assert classification.get("artifact_type"), "artifact_type missing from classification"


def test_non_game_task_does_not_receive_game_repair_guidance(tmp_path):
    """End-to-end: non-game animated task never receives game/canvas repair guidance."""
    html_path = tmp_path / "index.html"
    task_desc = "animate text with rainbow colors"
    html_path.write_text(FIXTURES["static_plain"], encoding="utf-8")  # fails verification
    pool, item = _pool_item(tmp_path, html_path=html_path, task_description=task_desc)
    svc = AtlasAutoVerificationService(
        journal=_Journal(),
        storage=_Storage(pool),
        command_runner=_Runner(),
        playwright_verifier=_FakeSmoke({"status": "browser_smoke_failed", "reason": "motion_not_detected"}),
    )
    out = svc.run_after_auto_safe_apply(
        AtlasAutoVerificationRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id="run_1")
    )
    # The selected contract must NOT be canvas_game
    contract_id = out.metadata.get("visual_contract_id", "")
    assert contract_id != "canvas_game_visual_v1", (
        f"Non-game task received canvas_game contract: {contract_id}"
    )
    # Repair profile must NOT be canvas_game_repair
    repair_profile = out.metadata.get("visual_contract_repair_profile", "")
    assert repair_profile != "canvas_game_repair", (
        f"Non-game task received canvas_game_repair profile: {repair_profile}"
    )


def _pool_item(tmp_path: Path, *, html_path: Path, task_description: str):
    rel = html_path.relative_to(tmp_path).as_posix()
    item = AtlasPlanItem(
        item_id="item_1",
        pool_id="pool_1",
        title="Visual artifact",
        goal=task_description,
        item_type="implementation",
        risk_level="low",
        status="ready",
        target_files=[rel],
        done_definition=[task_description],
        metadata={
            "safe_apply": {"status": "applied", "changed_files": [rel]},
            "original_step_payload": {"acceptance_criteria": [task_description]},
        },
    )
    pool = AtlasPlanPool(
        pool_id="pool_1",
        root_goal=task_description,
        project_path=str(tmp_path),
        items=[item],
    )
    return pool, item
