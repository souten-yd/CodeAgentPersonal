import json
from pathlib import Path

from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest
from agent.model_forge.cutover import CutoverController
from agent.model_forge.execution_bridge import ForgeModelExecutionBridge
from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.provider_base import ForgeProvider, HealthState, ProviderHealth
from agent.model_forge.provider_registry import ProviderRegistry
from agent.model_forge.schema import (
    ForgeExecutionRequest,
    ForgeExecutionResult,
    ForgeUsage,
    ProviderDescriptor,
    ProviderSupport,
    SourceClass,
)
from agent.model_forge.shadow import ShadowStore
from agent.model_forge.stage_matrix import StageMatrix
from agent.model_forge.stage_taxonomy import ForgeStage, StageMode


class _FakeProvider(ForgeProvider):
    def __init__(self) -> None:
        super().__init__(
            ProviderDescriptor(
                provider_id="fake_local",
                provider_type="fake",
                source_class=SourceClass.SELF_HOSTED,
                enabled=True,
                supports=ProviderSupport(chat_completions=True),
            )
        )
        self.calls: list[ForgeExecutionRequest] = []
        self.fail_next = False

    def _probe_health(self) -> ProviderHealth:
        return ProviderHealth(provider_id=self.provider_id, state=HealthState.READY)

    def run_and_capture(self, request: ForgeExecutionRequest) -> tuple[ForgeExecutionResult, str]:
        self.calls.append(request)
        if self.fail_next:
            self.fail_next = False
            return (
                ForgeExecutionResult(
                    request_id=request.request_id,
                    provider_id=self.provider_id,
                    model_id="fake-model",
                    route_id=request.route_id,
                    stage=request.stage,
                    contract_valid=False,
                    errors=["fake_failure"],
                ),
                "",
            )
        output = json.dumps({"plan": {"implementation_steps": [{"title": "forge"}]}})
        return (
            ForgeExecutionResult(
                request_id=request.request_id,
                provider_id=self.provider_id,
                model_id="fake-model",
                route_id=request.route_id,
                stage=request.stage,
                contract_valid=True,
                usage=ForgeUsage(output_tokens=len(output.split())),
            ),
            output,
        )

    def execute_chat_completion(self, request: ForgeExecutionRequest) -> ForgeExecutionResult:
        result, _output = self.run_and_capture(request)
        return result


class _FakeService:
    def __init__(self, root: Path, *, enabled: bool) -> None:
        self.root = root
        self.enabled = enabled
        self.registry = ProviderRegistry()
        self.provider = _FakeProvider()
        self.registry.register(self.provider)
        self.stage_matrix = StageMatrix(root / "stage_policy.json")
        self.stage_matrix.set_policy(
            ForgeStage.PLANNING,
            StageMode.SHADOW_SELECT,
            reason="test_shadow",
        )
        self.profiles = ProfileStore(root / "profiles")
        self.shadow = ShadowStore(root / "shadow")
        self.cutover_controller = CutoverController(
            self.stage_matrix,
            self.shadow,
            store_dir=root / "cutover",
        )
        self.events: list[dict] = []

    def forge_enabled(self) -> bool:
        return self.enabled

    def models(self) -> list[dict]:
        return [{"provider_id": "fake_local", "model_id": "fake-model", "source": "test"}]

    def record_execution_bridge_event(self, payload: dict) -> str:
        self.events.append(dict(payload))
        path = self.root / "events" / f"{payload['stage']}.{payload['request_id']}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)


def test_bridge_disabled_mode_returns_legacy_and_does_not_execute_forge(tmp_path) -> None:
    service = _FakeService(tmp_path, enabled=False)
    bridge = ForgeModelExecutionBridge(
        legacy_fn=lambda _s, _u: {"legacy": True},
        service_factory=lambda _s, _u: service,
        stage=ForgeStage.PLANNING,
    )

    assert bridge("system", "user") == {"legacy": True}

    assert service.provider.calls == []
    assert service.events[-1]["decision"] == "forge_disabled_legacy_primary"
    assert service.events[-1]["changes_production_routing"] is False
    assert service.events[-1]["legacy_primary"] is True


def test_bridge_shadow_select_records_comparison_but_returns_legacy(tmp_path) -> None:
    service = _FakeService(tmp_path, enabled=True)
    bridge = ForgeModelExecutionBridge(
        legacy_fn=lambda _s, _u: {"plan": {"implementation_steps": [{"title": "legacy"}]}},
        service_factory=lambda _s, _u: service,
        stage=ForgeStage.PLANNING,
    )

    result = bridge.generate_json(AtlasLLMJsonRequest(system_prompt="system", user_prompt="user"))

    assert result.ok is True
    assert result.data["plan"]["implementation_steps"][0]["title"] == "legacy"
    assert len(service.provider.calls) == 1
    assert service.events[-1]["decision"] == "shadow_recorded_legacy_primary"
    assert service.events[-1]["selection"]["selected_provider_id"] == "fake_local"
    assert service.events[-1]["shadow"]["comparison_ref"]
    assert Path(service.events[-1]["shadow"]["comparison_ref"]).exists()
    assert service.events[-1]["changes_production_routing"] is False


def test_bridge_cutover_returns_forge_output_with_legacy_fallback_available(tmp_path) -> None:
    service = _FakeService(tmp_path, enabled=True)
    bridge = ForgeModelExecutionBridge(
        legacy_fn=lambda _s, _u: {"plan": {"implementation_steps": [{"title": "legacy"}]}},
        service_factory=lambda _s, _u: service,
        stage=ForgeStage.PLANNING,
    )
    bridge.generate_json(AtlasLLMJsonRequest(system_prompt="system", user_prompt="user"))
    service.cutover_controller.cutover(ForgeStage.PLANNING, acknowledge=True)

    result = bridge.generate_json(AtlasLLMJsonRequest(system_prompt="system", user_prompt="user"))

    assert result.ok is True
    assert result.data["plan"]["implementation_steps"][0]["title"] == "forge"
    assert service.events[-1]["decision"] == "forge_primary_returned"
    assert service.events[-1]["legacy_primary"] is False
    assert service.events[-1]["changes_production_routing"] is True
    assert service.events[-1]["fallback"]["used"] is False
    assert "_routed_data" not in service.events[-1]


def test_bridge_cutover_falls_back_to_legacy_when_forge_fails(tmp_path) -> None:
    service = _FakeService(tmp_path, enabled=True)
    bridge = ForgeModelExecutionBridge(
        legacy_fn=lambda _s, _u: {"plan": {"implementation_steps": [{"title": "legacy"}]}},
        service_factory=lambda _s, _u: service,
        stage=ForgeStage.PLANNING,
    )
    bridge.generate_json(AtlasLLMJsonRequest(system_prompt="system", user_prompt="user"))
    service.cutover_controller.cutover(ForgeStage.PLANNING, acknowledge=True)
    service.provider.fail_next = True

    result = bridge.generate_json(AtlasLLMJsonRequest(system_prompt="system", user_prompt="user"))

    assert result.ok is True
    assert result.data["plan"]["implementation_steps"][0]["title"] == "legacy"
    assert service.events[-1]["decision"] == "forge_primary_failed_legacy_fallback"
    assert service.events[-1]["legacy_primary"] is True
    assert service.events[-1]["changes_production_routing"] is False
    assert service.events[-1]["fallback"]["used"] is True


def test_bridge_rollback_returns_to_legacy_primary(tmp_path) -> None:
    service = _FakeService(tmp_path, enabled=True)
    bridge = ForgeModelExecutionBridge(
        legacy_fn=lambda _s, _u: {"plan": {"implementation_steps": [{"title": "legacy"}]}},
        service_factory=lambda _s, _u: service,
        stage=ForgeStage.PLANNING,
    )
    bridge.generate_json(AtlasLLMJsonRequest(system_prompt="system", user_prompt="user"))
    service.cutover_controller.cutover(ForgeStage.PLANNING, acknowledge=True)
    service.cutover_controller.rollback(ForgeStage.PLANNING)

    result = bridge.generate_json(AtlasLLMJsonRequest(system_prompt="system", user_prompt="user"))

    assert result.ok is True
    assert result.data["plan"]["implementation_steps"][0]["title"] == "legacy"
    assert service.events[-1]["decision"] == "shadow_recorded_legacy_primary"
    assert service.events[-1]["cutover"]["status"] == "rolled_back"
    assert service.events[-1]["legacy_primary"] is True
    assert service.events[-1]["changes_production_routing"] is False
