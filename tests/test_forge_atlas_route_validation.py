"""PR22: Validate Atlas phases against the benchmark-derived optimal route + injection."""
from __future__ import annotations

from agent.model_forge.atlas_route_validation import (
    AtlasPhaseObservation,
    AtlasRouteValidator,
)
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ModelProfile


def _profile():
    return ModelProfile(
        model_id="Qwen3.6-35B-A3B",
        provider_id="local_openai_compatible",
        dimension_scores={"structured_output_fidelity": 0.8, "patch_protocol_fidelity": 0.8},
        sample_count=6,
        evidence_refs=["ev://benchmark/1"],
    )


def _validate(tmp_path, observations, change_class=ChangeClass.MEDIUM):
    return AtlasRouteValidator(tmp_path).validate(
        profile=_profile(),
        provider_id="local_openai_compatible",
        model_id="Qwen3.6-35B-A3B",
        change_class=change_class,
        observations=observations,
    )


def _good_phases():
    # MEDIUM optimal route is patch_dsl (injection 3).
    return [
        AtlasPhaseObservation(phase="planning", route=ForgeRoute.SLICED_IMPACT, status="plan_ready",
                              evidence_refs=["ev://plan"]),
        AtlasPhaseObservation(phase="code_development", route=ForgeRoute.PATCH_DSL, status="patch_proposed",
                              evidence_refs=["ev://patch"]),
        AtlasPhaseObservation(phase="completion", route=ForgeRoute.CRITICAL_GATE, status="verified",
                              evidence_refs=["ev://verify"], verification_proof=True, safe_apply_proof=True),
    ]


def test_valid_atlas_run_passes(tmp_path):
    report = _validate(tmp_path, _good_phases())
    assert report.optimal_route == ForgeRoute.PATCH_DSL
    assert report.twin_injection_level == 3
    assert report.overall_valid is True
    assert report.proof_level == "atlas_route_validation_passed"
    assert report.changes_production_routing is False
    assert report.missing_phases == []


def test_unsafe_route_is_flagged(tmp_path):
    # micro_patch is not a safe candidate for LARGE -> selector overrides -> not within safe.
    phases = [
        AtlasPhaseObservation(phase="planning", route=ForgeRoute.SLICED_IMPACT, status="plan_ready",
                              evidence_refs=["ev://plan"]),
        AtlasPhaseObservation(phase="code_development", route=ForgeRoute.MICRO_PATCH, status="patch_proposed",
                              evidence_refs=["ev://patch"]),
        AtlasPhaseObservation(phase="completion", route=ForgeRoute.CRITICAL_GATE, status="verified",
                              evidence_refs=["ev://verify"], verification_proof=True, safe_apply_proof=True),
    ]
    report = _validate(tmp_path, phases, change_class=ChangeClass.LARGE)
    code = next(p for p in report.phases if p.phase == "code_development")
    assert code.route_within_safe is False
    assert any("route_not_within_safe_candidates" in i for i in code.issues)
    assert report.proof_level == "atlas_route_validation_mismatch"


def test_code_development_off_benchmark_optimal_is_flagged(tmp_path):
    phases = _good_phases()
    # direct_patch is safe for MEDIUM but not the benchmark-optimal route (patch_dsl).
    phases[1] = AtlasPhaseObservation(phase="code_development", route=ForgeRoute.DIRECT_PATCH,
                                      status="patch_proposed", evidence_refs=["ev://patch"])
    report = _validate(tmp_path, phases)
    code = next(p for p in report.phases if p.phase == "code_development")
    assert code.route_within_safe is True
    assert code.route_matches_optimal is False
    assert any("route_off_benchmark_optimal" in i for i in code.issues)
    assert report.overall_valid is False


def test_completion_without_safe_apply_proof_is_invalid(tmp_path):
    phases = _good_phases()
    phases[2] = AtlasPhaseObservation(phase="completion", route=ForgeRoute.CRITICAL_GATE, status="verified",
                                      evidence_refs=["ev://verify"], verification_proof=True, safe_apply_proof=False)
    report = _validate(tmp_path, phases)
    completion = next(p for p in report.phases if p.phase == "completion")
    assert "missing_safe_apply_proof" in completion.issues
    assert completion.valid is False


def test_missing_phase_is_pending_not_passed(tmp_path):
    only_planning = [
        AtlasPhaseObservation(phase="planning", route=ForgeRoute.SLICED_IMPACT, status="plan_ready",
                              evidence_refs=["ev://plan"]),
    ]
    report = _validate(tmp_path, only_planning)
    assert report.overall_valid is False
    assert set(report.missing_phases) == {"code_development", "completion"}
    assert report.proof_level == "atlas_route_validation_pending"


def test_report_is_persisted_and_shadow_only(tmp_path):
    report = _validate(tmp_path, _good_phases())
    assert report.changes_production_routing is False
    ref = next((r.split("report_ref:", 1)[1] for r in report.reasons if r.startswith("report_ref:")), None)
    assert ref is not None
    import json
    saved = json.loads(open(ref, encoding="utf-8").read())
    assert saved["run_id"] == report.run_id
    assert saved["changes_production_routing"] is False
