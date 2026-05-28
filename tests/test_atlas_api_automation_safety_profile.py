from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_automation_safety_profile import (
    AUTOMATION_PROFILE_PRESETS,
    EXPECTED_CONFIRMATION_TEXT,
    LEGACY_CONFIRMATION_TEXT,
    router,
)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("CODEAGENT_CA_DATA_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _write_level4_checkpoint(data_root: Path) -> Path:
    checkpoint_dir = data_root / "atlas" / "level4_self_improvement_checkpoints" / "checkpoint_1"
    checkpoint_dir.mkdir(parents=True)
    checkpoint = {
        "schema_version": "atlas.level4_self_improvement_checkpoint.v1",
        "checkpoint_id": "checkpoint_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "transition_pr": "PR-ATLAS-SCALE-146",
        "next_required_pr": "PR-ATLAS-SCALE-147",
        "previous_runtime_level": "level_3_autonomous_implementation_loop_candidate",
        "runtime_level": "level_4_self_improvement_platform",
        "target_runtime_level": "level_4_self_improvement_platform",
        "transition_authorized": True,
        "transition_blocked": False,
        "blocking_reasons": [],
        "level3_candidate_path": str(data_root / "level3.json"),
        "self_improvement_draft_pr_path": str(data_root / "draft_pr.json"),
        "data_root": str(data_root),
        "level4_self_improvement_checkpoint_enabled": True,
        "self_improvement_platform_enabled": True,
        "strict_self_improvement_gates_ready": True,
        "candidate_workspace_required": True,
        "draft_pr_only": True,
        "direct_merge_forbidden": True,
        "stable_runtime_mutation_forbidden": True,
        "human_approval_required_for_self_improvement": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "stable_runtime_mutation_enabled": False,
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_applied": False,
        "verification_performed": False,
        "verification_result_fabricated": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
        "direct_merge_performed": False,
        "remote_git_push_performed": False,
        "stable_runtime_mutation_performed": False,
        "evidence_chain": {"draft_pr_number": 1000, "changed_files": ["app/atlas/example.py"]},
        "allowed_level4_actions": ["request_human_review"],
        "forbidden_level4_actions": ["direct_merge"],
    }
    path = checkpoint_dir / "manifest.json"
    path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
    return path


def test_policies_returns_six_presets_and_capability_matrix(client: TestClient) -> None:
    resp = client.get("/api/atlas/automation-safety-profile/policies")
    assert resp.status_code == 200
    data = resp.json()
    assert data["expected_confirmation_text"] == EXPECTED_CONFIRMATION_TEXT
    assert data["legacy_confirmation_text_accepted"] == LEGACY_CONFIRMATION_TEXT
    assert data["explicit_profile_selection_required"] is True

    preset_ids = [p["id"] for p in data["automation_profile_presets"]]
    assert preset_ids == [p["id"] for p in AUTOMATION_PROFILE_PRESETS]
    # UI consolidated to 5 presets (0-4). Profile 4 selects envelope from
    # Work target (work_target_envelope_map): Dev/repair → bounded_dev,
    # Self-improvement → self_improvement.
    assert preset_ids == [
        "review_only",
        "single_action",
        "supervised_auto",
        "autonomous_custom",
        "autonomous_bounded_dev",
    ]
    full_auto_presets = [p for p in data["automation_profile_presets"] if p["enables_full_automation"]]
    assert {p["id"] for p in full_auto_presets} == {"autonomous_bounded_dev"}
    profile4 = next(p for p in data["automation_profile_presets"] if p["id"] == "autonomous_bounded_dev")
    assert profile4["work_target_envelope_map"]["software_development_or_repair"] == "pre_authorized_bounded_dev_envelope"
    assert profile4["work_target_envelope_map"]["platform_self_improvement"] == "pre_authorized_self_improvement_envelope"

    capability_ids = [item["id"] for item in data["safety_profiles"]]
    assert capability_ids == [
        "review_only",
        "guarded_single_action",
        "supervised_bounded_auto",
        "autonomous_dev_agent",
    ]
    for item in data["safety_profiles"]:
        assert "allows_file_mutation" in item["capabilities"]


def test_pre_authorized_envelopes_returns_recipes(client: TestClient) -> None:
    resp = client.get("/api/atlas/automation-safety-profile/pre-authorized-envelopes")
    assert resp.status_code == 200
    data = resp.json()
    env_ids = {item["envelope_id"] for item in data["envelopes"]}
    assert env_ids == {
        "none",
        "pre_authorized_bounded_dev_envelope",
        "pre_authorized_self_improvement_envelope",
    }


def test_preview_blocks_without_explicit_selection(client: TestClient) -> None:
    resp = client.post(
        "/api/atlas/automation-safety-profile/preview",
        json={"profile": "review_only", "explicit_profile_selection": False},
    )
    assert resp.status_code == 200
    profile = resp.json()["safety_profile"]
    assert profile["status"] == "blocked"
    assert "explicit_profile_selection_required" in profile["blocking_reasons"]


def test_preview_active_for_review_only(client: TestClient) -> None:
    resp = client.post(
        "/api/atlas/automation-safety-profile/preview",
        json={"profile": "review_only", "explicit_profile_selection": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety_profile"]["status"] == "active"
    assert data["envelope"] is None
    assert data["enables_full_automation"] is False


def test_preview_bounded_dev_envelope_active(client: TestClient) -> None:
    resp = client.post(
        "/api/atlas/automation-safety-profile/preview",
        json={
            "profile": "autonomous_dev_agent",
            "explicit_profile_selection": True,
            "envelope_id": "pre_authorized_bounded_dev_envelope",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["safety_profile"]["status"] == "active"
    assert data["envelope"]["status"] == "active"
    assert data["envelope"]["autonomous_loop_execution_enabled"] is True
    assert data["enables_full_automation"] is True


def test_select_requires_confirmation_text(client: TestClient) -> None:
    resp = client.post(
        "/api/atlas/automation-safety-profile/select",
        json={
            "profile": "review_only",
            "explicit_profile_selection": True,
            "confirmation_text": "WRONG",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "confirmation_text_required"


def test_select_writes_safety_manifest(client: TestClient, tmp_path: Path) -> None:
    resp = client.post(
        "/api/atlas/automation-safety-profile/select",
        json={
            "profile": "review_only",
            "explicit_profile_selection": True,
            "confirmation_text": EXPECTED_CONFIRMATION_TEXT,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    manifest_path = Path(data["manifest_paths"]["safety_profile"])
    assert manifest_path.exists()
    assert manifest_path.is_relative_to(tmp_path)


def test_select_writes_envelope_manifest_for_bounded_dev(
    client: TestClient, tmp_path: Path
) -> None:
    resp = client.post(
        "/api/atlas/automation-safety-profile/select",
        json={
            "profile": "autonomous_dev_agent",
            "explicit_profile_selection": True,
            "envelope_id": "pre_authorized_bounded_dev_envelope",
            "confirmation_text": EXPECTED_CONFIRMATION_TEXT,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    envelope_path = Path(data["manifest_paths"]["envelope"])
    assert envelope_path.exists()
    envelope = json.loads(envelope_path.read_text())
    assert envelope["autonomous_loop_execution_enabled"] is True
    assert envelope["automatic_patch_apply_enabled"] is True
    assert envelope["envelope_id"] == "pre_authorized_bounded_dev_envelope"


def test_select_self_improvement_requires_strict_gate(
    client: TestClient, tmp_path: Path
) -> None:
    checkpoint_path = _write_level4_checkpoint(tmp_path)
    resp = client.post(
        "/api/atlas/automation-safety-profile/select",
        json={
            "profile": "autonomous_dev_agent",
            "explicit_profile_selection": True,
            "self_improvement_enabled": True,
            "self_improvement_scope": "atlas_runtime_strict",
            "envelope_id": "pre_authorized_self_improvement_envelope",
            "level4_checkpoint_path": str(checkpoint_path),
            "confirmation_text": EXPECTED_CONFIRMATION_TEXT,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"
    blocked = data["safety_profile"]["blocking_reasons"]
    assert "strict_gate_approval_required_for_self_improvement" in blocked


def test_select_self_improvement_with_strict_gate_active(
    client: TestClient, tmp_path: Path
) -> None:
    checkpoint_path = _write_level4_checkpoint(tmp_path)
    resp = client.post(
        "/api/atlas/automation-safety-profile/select",
        json={
            "profile": "autonomous_dev_agent",
            "explicit_profile_selection": True,
            "self_improvement_enabled": True,
            "self_improvement_scope": "atlas_runtime_strict",
            "envelope_id": "pre_authorized_self_improvement_envelope",
            "level4_checkpoint_path": str(checkpoint_path),
            "strict_gate_approved": True,
            "confirmation_text": EXPECTED_CONFIRMATION_TEXT,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    envelope_path = Path(data["manifest_paths"]["envelope"])
    envelope = json.loads(envelope_path.read_text())
    assert envelope["automatic_self_improvement_enabled"] is True


def test_latest_returns_persisted_manifest(client: TestClient) -> None:
    select_resp = client.post(
        "/api/atlas/automation-safety-profile/select",
        json={
            "profile": "autonomous_dev_agent",
            "explicit_profile_selection": True,
            "envelope_id": "pre_authorized_bounded_dev_envelope",
            "confirmation_text": EXPECTED_CONFIRMATION_TEXT,
        },
    )
    assert select_resp.status_code == 200

    latest_resp = client.get("/api/atlas/automation-safety-profile/latest")
    assert latest_resp.status_code == 200
    data = latest_resp.json()
    assert data["available"] is True
    assert data["safety_profile"]["status"] == "active"
    assert data["envelope"] is not None
    assert data["envelope"]["envelope_id"] == "pre_authorized_bounded_dev_envelope"


def test_start_autonomous_loop_blocked_without_envelope(client: TestClient) -> None:
    resp = client.post(
        "/api/atlas/automation-safety-profile/start-autonomous-loop",
        json={
            "request_kind": "autonomous_dev_loop",
            "loop_goal": "test",
            "requested_actions": 1,
            "requested_files": 1,
            "requested_runtime_seconds": 60,
            "requested_risk_level": "low",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"
    assert "envelope_manifest_missing" in data["blocking_reasons"]
    assert data["permit_autonomous_loop_execution"] is False


def test_start_autonomous_loop_active_after_envelope_select(
    client: TestClient,
) -> None:
    client.post(
        "/api/atlas/automation-safety-profile/select",
        json={
            "profile": "autonomous_dev_agent",
            "explicit_profile_selection": True,
            "envelope_id": "pre_authorized_bounded_dev_envelope",
            "confirmation_text": EXPECTED_CONFIRMATION_TEXT,
        },
    )
    resp = client.post(
        "/api/atlas/automation-safety-profile/start-autonomous-loop",
        json={
            "request_kind": "autonomous_dev_loop",
            "loop_goal": "improve plan UI",
            "requested_actions": 3,
            "requested_files": 5,
            "requested_runtime_seconds": 300,
            "requested_risk_level": "low",
            "requested_paths": ["app/atlas/", "web/css/"],
            "requested_commands": ["python -m pytest tests/test_atlas_workflow_state.py"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["permit_autonomous_loop_execution"] is True


def test_start_autonomous_loop_blocks_bound_violations(client: TestClient) -> None:
    client.post(
        "/api/atlas/automation-safety-profile/select",
        json={
            "profile": "autonomous_dev_agent",
            "explicit_profile_selection": True,
            "envelope_id": "pre_authorized_bounded_dev_envelope",
            "confirmation_text": EXPECTED_CONFIRMATION_TEXT,
        },
    )
    resp = client.post(
        "/api/atlas/automation-safety-profile/start-autonomous-loop",
        json={
            "request_kind": "autonomous_dev_loop",
            "loop_goal": "exceeds bounds",
            "requested_actions": 999,
            "requested_files": 999,
            "requested_runtime_seconds": 999999,
            "requested_risk_level": "high",
            "requested_paths": [".git/config"],
            "requested_commands": ["rm -rf /"],
        },
    )
    data = resp.json()
    assert data["status"] == "blocked"
    blocked = data["blocking_reasons"]
    assert "requested_actions_exceed_envelope_bound" in blocked
    assert "requested_files_exceed_envelope_bound" in blocked
    assert "requested_runtime_exceeds_envelope_bound" in blocked
    assert "requested_risk_level_exceeds_envelope_bound" in blocked
    assert "requested_path_blocked_by_envelope" in blocked
    assert "requested_command_outside_envelope_allowlist" in blocked


def test_global_default_runtime_lockout_unchanged(client: TestClient) -> None:
    """Default workflow_state shouldn't change just because an envelope is selected."""

    client.post(
        "/api/atlas/automation-safety-profile/select",
        json={
            "profile": "autonomous_dev_agent",
            "explicit_profile_selection": True,
            "envelope_id": "pre_authorized_bounded_dev_envelope",
            "confirmation_text": EXPECTED_CONFIRMATION_TEXT,
        },
    )
    latest = client.get("/api/atlas/automation-safety-profile/latest").json()
    safety_profile = latest["safety_profile"]
    # Safety profile manifest must still keep these flags False (invariants).
    for key in (
        "direct_merge_enabled",
        "remote_git_push_enabled",
        "stable_runtime_mutation_enabled",
        "self_apply_enabled",
        "self_modification_enabled",
        "execution_performed",
        "mutation_performed",
        "patch_generated",
        "patch_applied",
    ):
        assert safety_profile[key] is False, f"safety profile flag {key} must remain False"
    # Envelope manifest carries the derived activation flags.
    envelope = latest["envelope"]
    assert envelope["autonomous_loop_execution_enabled"] is True
    assert envelope["automatic_patch_apply_enabled"] is True
