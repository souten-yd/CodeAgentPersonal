"""/policies surfaces the profile-dependent runtime model and per-preset activation."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_automation_safety_profile import router


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CODEAGENT_CA_DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_policies_exposes_runtime_level_model(client: TestClient) -> None:
    body = client.get("/api/atlas/automation-safety-profile/policies").json()
    assert body["runtime_level_model"] == "profile_dependent"
    assert body["default_runtime_level"] == "level_4_self_improvement_platform"
    assert body["max_runtime_level"] == "level_8_fully_autonomous_code_agent"
    assert body["runtime_level_by_profile"]["review_only"] == "level_0_review_only"
    assert body["runtime_level_by_profile"]["autonomous_dev_agent"] == "level_8_fully_autonomous_code_agent"


def test_policies_exposes_critical_handling_by_profile(client: TestClient) -> None:
    body = client.get("/api/atlas/automation-safety-profile/policies").json()
    handling = body["critical_handling_by_profile"]
    assert handling["review_only"] == "block"
    assert handling["guarded_single_action"] == "ask"
    assert handling["supervised_bounded_auto"] == "ask"


def test_presets_carry_resolved_runtime_level(client: TestClient) -> None:
    presets = {p["id"]: p for p in client.get(
        "/api/atlas/automation-safety-profile/policies"
    ).json()["automation_profile_presets"]}

    assert presets["review_only"]["resolved_runtime_level"] == "level_0_review_only"
    assert presets["supervised_auto"]["resolved_runtime_level"] == "level_2_to_level4_supervised_bounded_auto"

    # Both autonomous presets are Level-8 profiles.
    assert presets["autonomous_custom"]["resolved_runtime_level"] == "level_8_fully_autonomous_code_agent"
    assert presets["autonomous_bounded_dev"]["resolved_runtime_level"] == "level_8_fully_autonomous_code_agent"


def test_autonomous_custom_is_bounds_required_not_active(client: TestClient) -> None:
    presets = {p["id"]: p for p in client.get(
        "/api/atlas/automation-safety-profile/policies"
    ).json()["automation_profile_presets"]}

    custom = presets["autonomous_custom"]
    assert custom["full_automation_capable"] is True
    # No envelope ⇒ Level-8 capable but loop not auto-active; bounds required per request.
    assert custom["activation_state"] == "bounds_required"
    assert custom["full_automation_active"] is False
    assert custom["enables_full_automation"] is False


def test_autonomous_bounded_dev_requires_envelope(client: TestClient) -> None:
    presets = {p["id"]: p for p in client.get(
        "/api/atlas/automation-safety-profile/policies"
    ).json()["automation_profile_presets"]}

    bounded = presets["autonomous_bounded_dev"]
    assert bounded["full_automation_capable"] is True
    assert bounded["enables_full_automation"] is True
    # At catalogue time no envelope is persisted, so it is envelope_required and not active yet.
    assert bounded["activation_state"] == "envelope_required"
    assert bounded["full_automation_active"] is False


def test_non_autonomous_presets_not_full_automation(client: TestClient) -> None:
    presets = {p["id"]: p for p in client.get(
        "/api/atlas/automation-safety-profile/policies"
    ).json()["automation_profile_presets"]}
    for pid in ("review_only", "single_action", "supervised_auto"):
        assert presets[pid]["full_automation_capable"] is False
        assert presets[pid]["full_automation_active"] is False
        assert presets[pid]["activation_state"] == "not_applicable"
