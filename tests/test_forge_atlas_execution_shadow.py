from __future__ import annotations

import json
from pathlib import Path

from agent.model_forge.atlas_shadow import record_atlas_execution_shadow
from agent.model_forge.execution_bridge import ForgeModelExecutionBridge
from agent.model_forge.forge_service import ForgeService
from agent.model_forge.stage_taxonomy import ForgeStage, StageMode
from agent.twin_control_plane.proof_ledger import ProofLedgerStore


def _service(tmp_path: Path) -> ForgeService:
    service = ForgeService(tmp_path, env={})
    service.profiles.record_observation(
        model_id="weak-local",
        provider_id="anvil",
        dimensions={"structured_output_fidelity": 0.2, "edit_intent_quality": 0.8},
        evidence_refs=["evaluation/real-run-1"],
        source="real_llm_evaluation",
    )
    return service


def test_all_atlas_phases_record_method_evaluation_shadow_and_proof_ledger(tmp_path):
    service = _service(tmp_path)
    stages = (
        ForgeStage.PLANNING,
        ForgeStage.PATCH_GENERATION,
        ForgeStage.VERIFICATION_INTERPRETATION,
        ForgeStage.REPAIR,
    )
    refs = []
    for stage in stages:
        ref = record_atlas_execution_shadow(
            service,
            stage=stage,
            request_id=f"run:{stage.value}",
            task_category=f"atlas_{stage.value}",
            result_payload={"status": "passed", "secret_body": "not persisted raw"},
            result_status="passed",
        )
        refs.append(ref)
        body = json.loads(Path(ref).read_text(encoding="utf-8"))
        assert body["decision"] == "shadow_recorded_legacy_primary"
        assert body["changes_production_routing"] is False
        assert body["active_auto_enabled"] is False
        assert body["method_variant"]
        assert body["evaluation_refs"] == ["evaluation/real-run-1"]
        assert "secret_body" not in json.dumps(body)
        assert body["result_digest"].startswith("sha256:")

    ledger = ProofLedgerStore(tmp_path / "twin_control_plane" / "proof_ledger").load("forge_shadow")
    assert len(ledger.entries) == 4
    assert {entry.forge_stage for entry in ledger.entries} == {stage.value for stage in stages}
    assert all(entry.method_variant and entry.forge_evaluation_refs for entry in ledger.entries)
    assert all(entry.accepted is False for entry in ledger.entries)
    assert len(refs) == 4


def test_unavailable_profile_is_recorded_as_unavailable_not_passed(tmp_path):
    service = ForgeService(tmp_path, env={})
    ref = record_atlas_execution_shadow(
        service,
        stage=ForgeStage.VERIFICATION_INTERPRETATION,
        request_id="verify-no-profile",
        task_category="atlas_verification",
        result_payload={"status": "passed"},
        result_status="passed",
    )
    body = json.loads(Path(ref).read_text(encoding="utf-8"))
    assert body["evaluation_refs"] == []
    assert body["unavailable_reasons"] == ["model_evaluation_profile:unavailable"]


def test_non_shadow_stage_policy_does_not_record_or_auto_activate(tmp_path):
    service = _service(tmp_path)
    service.stage_matrix.set_policy(
        ForgeStage.REPAIR,
        StageMode.AUTO_SELECT,
        allow_production_routing=True,
        reason="test_explicit_cutover",
    )
    ref = record_atlas_execution_shadow(
        service,
        stage=ForgeStage.REPAIR,
        request_id="active-policy",
        task_category="repair",
        result_payload={"status": "failed"},
    )
    assert ref == ""
    assert not (tmp_path / "model_forge" / "atlas_shadow" / "repair").exists()


def test_execution_bridge_preserves_legacy_output_and_adds_plan_shadow(tmp_path):
    service = _service(tmp_path)
    bridge = ForgeModelExecutionBridge(
        legacy_fn=lambda _system, _user: {"plan": ["legacy"]},
        service_factory=lambda _system, _user: service,
        stage=ForgeStage.PLANNING,
        task_category="plan_pool_create",
    )
    result = bridge("system", "user")
    assert result == {"plan": ["legacy"]}
    artifacts = list((tmp_path / "model_forge" / "atlas_shadow" / "planning").glob("*.json"))
    assert len(artifacts) == 1
    body = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert body["decision"] == "shadow_recorded_legacy_primary"
    assert body["changes_production_routing"] is False


def test_shadow_recording_failure_never_changes_legacy_output():
    class BrokenObservationService:
        def forge_enabled(self):
            return False

        def record_atlas_execution_shadow(self, **_payload):
            raise OSError("disk unavailable")

        def record_execution_bridge_event(self, _payload):
            return "event.json"

    bridge = ForgeModelExecutionBridge(
        legacy_fn=lambda _system, _user: {"answer": "legacy"},
        service_factory=lambda _system, _user: BrokenObservationService(),
        stage=ForgeStage.PLANNING,
    )
    assert bridge("system", "user") == {"answer": "legacy"}


def test_atlas_pipeline_has_verification_and_repair_shadow_hooks():
    source = (Path(__file__).resolve().parents[1] / "app" / "api" / "atlas_pipeline.py").read_text(encoding="utf-8")
    assert "ForgeStage.PATCH_GENERATION" in source
    assert "ForgeStage.VERIFICATION_INTERPRETATION" in source
    assert "task_category=\"atlas_verification\"" in source
    assert "ForgeStage.REPAIR" in source
    assert "task_category=\"atlas_self_correction\"" in source
