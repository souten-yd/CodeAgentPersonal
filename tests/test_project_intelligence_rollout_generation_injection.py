"""PIBIH-4: Project Intelligence generation-context injection (rollout-aware).

Generation previously built twin context and then returned a *baseline* package, so the rich Twin
context never reached the Patch Proposal / Repair prompts. These tests pin the rollout behavior:

- off: baseline, no rich sections, no telemetry;
- shadow: baseline returned (inputs unchanged) but a comparison artifact is recorded;
- active: the generation package is populated with symbols, behavior paths, preserve-behaviors,
  convergence gaps, recommended verification, and source excerpts from the twin.

The coordinator remains advisory — it returns a context package and never decides apply/verify.
"""

from __future__ import annotations

from agent.project_intelligence.contracts import (
    ContextItem,
    ContextManifest,
    GenerationContextRequest,
    ProjectIdentity,
    SourceExcerpt,
)
from agent.project_intelligence.coordinator import ProjectIntelligenceCoordinator
from agent.project_intelligence.rollout import ENV_ENABLED, ENV_SHADOW, RolloutConfig
from agent.project_twin.facade import TwinContextPackage, TwinProjectState, TwinReadiness


def _ci(ref: str, *, kind: str = "", summary: str = "", status: str = "inferred", source_refs=None, reason: str = "") -> ContextItem:
    return ContextItem(ref=ref, kind=kind, summary=summary, status=status, confidence=0.6,
                       source_refs=list(source_refs or []), inclusion_reason=reason)


class _FakeTwin:
    """A ready twin returning a deterministic rich context package."""

    def __init__(self, ready: bool = True) -> None:
        self._ready = ready

    def open_project(self, request) -> TwinProjectState:
        return TwinProjectState(
            project=request.project,
            readiness=TwinReadiness.READY if self._ready else TwinReadiness.DISABLED,
            twin_revision_id="rev-1",
            available_capabilities=["context"],
        )

    def build_context(self, request) -> TwinContextPackage:
        manifest = ContextManifest(
            manifest_id="m", project_id=request.project_id, workspace_id=request.workspace_id,
            phase=request.phase, token_budget=request.token_budget, used_tokens=10, truncated=False,
            rollout_mode="active",
        )
        return TwinContextPackage(
            project_id=request.project_id, workspace_id=request.workspace_id, twin_revision_id="rev-1",
            phase=request.phase,
            symbols=[_ci("py://m.py#f", kind="function", summary="f")],
            interfaces=[_ci("py://m.py#API", kind="interface", summary="API", reason="API.run()")],
            behavior_paths=[_ci("path://1", summary="ui->api", source_refs=["a", "b"])],
            preserve_behaviors=[
                _ci("preserve://keep", summary="keep this", status="inferred", source_refs=["x"]),
                _ci("preserve://gap", summary="missing thing", status="missing", source_refs=["y"]),
            ],
            tests=[_ci("test://t.py::test_f", summary="test_f", reason="covers f")],
            source_material=[SourceExcerpt(ref="py://m.py#f", path="m.py", start_line=1, end_line=3, excerpt="def f(): ...")],
            uncertainties=[_ci("u://1", reason="heuristic")],
            manifest=manifest,
        )


def _identity() -> ProjectIdentity:
    return ProjectIdentity(project_id="p1", workspace_id="w1", project_path="/tmp/p1")


def _generation() -> GenerationContextRequest:
    return GenerationContextRequest(project=_identity(), plan_pool_id="pp", plan_item_id="pi", target_refs=["py://m.py#f"])


def _coord(env: dict) -> ProjectIntelligenceCoordinator:
    return ProjectIntelligenceCoordinator(digital_twin=_FakeTwin(), rollout=RolloutConfig.from_env(env))


def test_off_generation_is_baseline_no_injection() -> None:
    coord = ProjectIntelligenceCoordinator(digital_twin=_FakeTwin(), rollout=RolloutConfig.off())
    pkg = coord.prepare_generation_context(_generation())
    assert pkg.context_manifest.rollout_mode == "off"
    assert pkg.actual_symbols == []
    assert pkg.target_files == []
    assert pkg.behavior_paths == []
    assert coord.telemetry.records() == []


def test_shadow_generation_records_comparison_but_returns_baseline() -> None:
    coord = _coord({ENV_ENABLED: "1", ENV_SHADOW: "1"})
    pkg = coord.prepare_generation_context(_generation())
    # Inputs unchanged: baseline package, no rich injection.
    assert pkg.actual_symbols == []
    assert pkg.target_files == []
    assert pkg.context_manifest.rollout_mode == "shadow"
    # But a shadow comparison artifact is recorded for generation.
    artifacts = coord.telemetry.comparison_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0].phase == "generation"
    assert artifacts[0].rollout_mode == "shadow"


def test_active_generation_injects_rich_twin_context() -> None:
    coord = _coord({ENV_ENABLED: "1"})
    pkg = coord.prepare_generation_context(_generation())

    assert pkg.context_manifest.rollout_mode == "active"
    assert pkg.actual_twin_revision_id == "rev-1"
    assert [s.ref for s in pkg.actual_symbols] == ["py://m.py#f"]
    assert [i.ref for i in pkg.required_interfaces] == ["py://m.py#API"]
    assert [b.path_id for b in pkg.behavior_paths] == ["path://1"]
    assert pkg.behavior_paths[0].steps == ["a", "b"]
    assert pkg.preserve_behaviors == ["preserve://keep", "preserve://gap"]
    # Only missing/contradicted preserve-behaviors become convergence gaps.
    assert [g.gap_id for g in pkg.convergence_gaps] == ["preserve://gap"]
    assert [v.requirement_id for v in pkg.verification_requirements] == ["test://t.py::test_f"]
    assert [f.path for f in pkg.target_files] == ["m.py"]
    # prohibited divergences = preserve-behaviors that are present (not gaps).
    assert pkg.prohibited_divergences == ["preserve://keep"]


def test_active_generation_with_unready_twin_falls_back_to_baseline() -> None:
    coord = ProjectIntelligenceCoordinator(digital_twin=_FakeTwin(ready=False), rollout=RolloutConfig.from_env({ENV_ENABLED: "1"}))
    pkg = coord.prepare_generation_context(_generation())
    # Unavailable twin is never fabricated into rich context; tagged active but empty.
    assert pkg.context_manifest.rollout_mode == "active"
    assert pkg.actual_symbols == []
    assert pkg.target_files == []


def test_generator_bridge_surfaces_rich_context_to_proposal() -> None:
    # End-to-end: the rich coordinator package now flows through the Atlas generator bridge into the
    # generation context dict the Patch Proposal consumes (previously empty because the coordinator
    # returned a baseline package).
    from agent.project_intelligence.adapters.atlas_generation import AtlasGeneratorBridge

    coord = _coord({ENV_ENABLED: "1"})
    bridge = AtlasGeneratorBridge(coord)
    res = bridge.build_generation_context(
        request=_generation(), legacy_context={"target": "m.py"},
        base_revision="r", current_actual_revision="r",
    )
    assert res.mode == "active" and res.used_intelligence is True and res.blocked is False
    ctx = res.context
    assert [s["ref"] for s in ctx["actual_symbols"]] == ["py://m.py#f"]
    assert [b["path_id"] for b in ctx["behavior_paths"]] == ["path://1"]
    assert ctx["preserve_behaviors"] == ["preserve://keep", "preserve://gap"]
    assert [v["requirement_id"] for v in ctx["verification_requirements"]] == ["test://t.py::test_f"]
    assert ctx["prohibited_divergences"] == ["preserve://keep"]
