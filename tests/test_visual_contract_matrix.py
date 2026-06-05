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
from tests.visual_fixtures import AUTOVERIFY_EXPECTATIONS, STATIC_EXPECTATIONS, write_fixture


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
