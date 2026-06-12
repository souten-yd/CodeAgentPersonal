from pathlib import Path

from agent.model_forge import (
    AdoptionState,
    ArenaCandidateSpec,
    ArenaRunner,
    ForgeExecutionRequest,
    ForgeExecutionResult,
    ForgeProvider,
    ForgeRoute,
    ForgeStage,
    PrivacyMode,
    ProviderDescriptor,
    ProviderRegistry,
    SourceClass,
    SourceMode,
)


class _Stub(ForgeProvider):
    def __init__(self, descriptor, text="output"):
        super().__init__(descriptor)
        self._text = text
        self.calls = 0

    def execute_chat_completion(self, request: ForgeExecutionRequest) -> ForgeExecutionResult:
        self.calls += 1
        return ForgeExecutionResult(
            request_id=request.request_id, provider_id=self.provider_id, model_id="m",
            route_id=request.route_id, stage=request.stage, contract_valid=True,
        )

    def run_and_capture(self, request):
        return self.execute_chat_completion(request), self._text


def _registry():
    reg = ProviderRegistry()
    reg.register(_Stub(ProviderDescriptor(provider_id="local", provider_type="t", source_class=SourceClass.LOCAL, enabled=True), text="local-out"))
    reg.register(_Stub(ProviderDescriptor(provider_id="ext", provider_type="t", source_class=SourceClass.EXTERNAL_CLOUD, enabled=True), text="ext-out"))
    return reg


def _specs():
    return [
        ArenaCandidateSpec(provider_id="local", model_id="m-local", route_id=ForgeRoute.PATCH_DSL),
        ArenaCandidateSpec(provider_id="ext", model_id="m-ext", route_id=ForgeRoute.TEST_FIRST),
    ]


def test_arena_runs_candidates_and_defaults_to_not_applied(tmp_path: Path) -> None:
    reg = _registry()
    runner = ArenaRunner(reg, store_dir=tmp_path, id_factory=lambda: "run1")
    record = runner.run(
        stage=ForgeStage.PATCH_GENERATION, specs=_specs(),
        source_mode=SourceMode.HYBRID, privacy_mode=PrivacyMode.FULL_SOURCE_ALLOWED,
        preset_id="web_app_standard",
        preset_ids=["web_app_standard", "repair_standard"],
        benchmark_depth="standard",
    )
    assert record.arena_run_id == "arena_run1"
    assert record.preset_ids == ["web_app_standard", "repair_standard"]
    assert record.benchmark_depth == "standard"
    assert len(record.candidates) == 2
    # Every candidate is not_applied — Arena never applies.
    assert all(c.adoption_state == AdoptionState.NOT_APPLIED for c in record.candidates)
    # Raw outputs + metadata persisted; no workspace source involved.
    run_dir = tmp_path / "arena_run1"
    assert (run_dir / "arena.json").exists()
    assert (run_dir / "cand_arena_run1_0.result.json").exists()
    assert (run_dir / "cand_arena_run1_0.raw.txt").read_text(encoding="utf-8") == "local-out"


def test_policy_blocked_candidate_is_recorded_not_executed(tmp_path: Path) -> None:
    reg = _registry()
    local = reg.get("local")
    ext = reg.get("ext")
    runner = ArenaRunner(reg, store_dir=tmp_path, id_factory=lambda: "run2")
    # Local Only: the external candidate must be blocked by policy, not executed.
    record = runner.run(
        stage=ForgeStage.PATCH_GENERATION, specs=_specs(),
        source_mode=SourceMode.LOCAL_ONLY, privacy_mode=PrivacyMode.NO_EXTERNAL_CODE,
    )
    assert local.calls == 1
    assert ext.calls == 0  # external never executed under Local Only
    blocked = next(c for c in record.candidates if c.provider_id == "ext")
    blocked_result = (tmp_path / "arena_run2" / f"{blocked.candidate_id}.result.json")
    assert "policy_blocked" in blocked_result.read_text(encoding="utf-8")


def test_runner_works_without_disk_store() -> None:
    record = ArenaRunner(_registry(), id_factory=lambda: "mem").run(
        stage=ForgeStage.REVIEW, specs=_specs()[:1],
        source_mode=SourceMode.LOCAL_PREFERRED, privacy_mode=PrivacyMode.SYMBOL_SUMMARY_ONLY,
    )
    assert len(record.candidates) == 1
    assert record.candidates[0].adoption_state == AdoptionState.NOT_APPLIED
