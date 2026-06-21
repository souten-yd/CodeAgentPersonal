from __future__ import annotations

from pathlib import Path

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.model_forge.twin_assist_contracts import TwinAssistRunRequest
from agent.model_forge.twin_assist_runner import TwinAssistRunner
from agent.model_forge.twin_assist_taxonomy import TwinAssistMode

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "twin_assist"


def test_runner_uses_real_atlas_proposal_path_for_baseline_and_assisted(tmp_path):
    prompts: list[str] = []

    def factory(data_root, _live_llm):
        def deterministic_llm(system_prompt, _user_prompt):
            prompts.append(system_prompt)
            return {
                "title": "Preserve parse contract",
                "target_files": ["contract.py"],
                "proposed_content": "__all__ = ['parse_token']\n\ndef parse_token(value: str) -> str:\n    return value.strip()\n",
                "risk_level": "low",
                "verification_plan": ["test_contract.py"],
                "implemented_symbols": ["parse_token"],
            }

        return AtlasPatchProposalService(
            journal=AtlasJournal(data_root),
            storage=AtlasPlanPoolStorage(data_root),
            llm_json_fn=deterministic_llm,
        )

    report = TwinAssistRunner(tmp_path / "evidence", service_factory=factory).run(TwinAssistRunRequest(
        provider_id="local-8080",
        model_id="weak-model",
        case_ids=["public_contract_preservation"],
        assist_modes=[TwinAssistMode.CONSTRAINTS_AND_REFS],
        project_fixture_root=str(FIXTURE_ROOT),
    ))

    comparison = report.comparisons[0]
    assert comparison.baseline is not None
    assert comparison.baseline.status == "passed"
    assert comparison.assisted[0].status == "passed"
    assert len(prompts) == 2
    assert "Twin Control Plane" not in prompts[0]
    assert "Twin Control Plane" in prompts[1]
    assert "parse_token" in prompts[1]
    assert Path(report.evidence_refs[0]).is_file()
    assert not (FIXTURE_ROOT / "public_contract_preservation" / "contract.py").read_text(encoding="utf-8").endswith("strip()\n")


def test_runner_marks_missing_fixture_unavailable_not_passed(tmp_path):
    report = TwinAssistRunner(tmp_path / "evidence").run(TwinAssistRunRequest(
        provider_id="local-8080",
        model_id="weak-model",
        case_ids=["public_contract_preservation"],
        assist_modes=[TwinAssistMode.CONSTRAINTS_AND_REFS],
        project_fixture_root=str(tmp_path / "missing"),
    ))
    comparison = report.comparisons[0]
    assert comparison.baseline.status == "unavailable"
    assert comparison.assisted[0].status == "unavailable"
    assert report.status == "unavailable"


def test_local_only_blocks_external_provider_before_service_call(tmp_path):
    called = False

    def forbidden_factory(_data_root, _llm):
        nonlocal called
        called = True
        raise AssertionError("service must not be created")

    report = TwinAssistRunner(tmp_path / "evidence", service_factory=forbidden_factory).run(TwinAssistRunRequest(
        provider_id="openrouter",
        model_id="external-model",
        case_ids=["public_contract_preservation"],
        assist_modes=[TwinAssistMode.CONSTRAINTS_AND_REFS],
        project_fixture_root=str(FIXTURE_ROOT),
    ))
    assert called is False
    assert report.status == "unavailable"
    assert report.comparisons[0].baseline.unavailable_reasons == ["external_provider_blocked_in_local_only"]
