import json
from pathlib import Path

from app.atlas.self_modification_risk_classifier import (
    classify_self_modification_risk,
    load_self_modification_risk_classification,
    write_self_modification_risk_classification,
)


def _write_proposal(tmp_path: Path, *, overrides: dict[str, object] | None = None) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    proposal_dir = data_root / "atlas" / "self_improvement_proposals" / "proposal_1"
    proposal_dir.mkdir(parents=True)
    proposal: dict[str, object] = {
        "schema_version": "atlas.self_improvement_proposal.v1",
        "proposal_id": "proposal_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "track_pr": "PR-ATLAS-SCALE-140",
        "next_required_pr": "PR-ATLAS-SCALE-141",
        "source_level3_candidate_path": str(data_root / "candidate.json"),
        "source_runtime_level": "level_3_autonomous_implementation_loop_candidate",
        "data_root": str(data_root),
        "target_repo": "KasaneCore",
        "target_area": "atlas_runtime",
        "problem_statement": "Need self-improvement risk classification.",
        "proposed_direction": "Classify before patch preview.",
        "acceptance_criteria": ["classification only"],
        "risk_level": "strict",
        "proposal_authorized": True,
        "proposal_blocked": False,
        "blocking_reasons": [],
        "self_improvement_proposal_mode_enabled": True,
        "proposal_only": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "draft_pr_only": True,
        "strict_self_modification_gate_required": True,
        "risk_classifier_required_before_patch_preview": True,
        "allowed_proposal_actions": ["record_problem", "request_human_review"],
        "forbidden_proposal_actions": ["generate_patch", "apply_patch", "direct_merge"],
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_applied": False,
        "verification_performed": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    if overrides:
        proposal.update(overrides)
    path = proposal_dir / "manifest.json"
    path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    return data_root, path


def test_classify_self_modification_risk_marks_runtime_strict(tmp_path: Path) -> None:
    data_root, proposal_path = _write_proposal(tmp_path)

    result = classify_self_modification_risk(proposal_path=proposal_path, data_root=data_root)

    assert result["classification_authorized"] is True
    assert result["classification"] == "strict"
    assert result["strict_gate_required"] is True
    assert result["classification_only"] is True
    assert result["patch_preview_enabled"] is False
    assert result["self_modification_enabled"] is False
    assert result["self_apply_enabled"] is False
    assert result["automatic_patch_generation_enabled"] is False
    assert result["automatic_patch_apply_enabled"] is False
    assert result["direct_merge_enabled"] is False
    assert result["remote_git_push_enabled"] is False
    assert result["execution_performed"] is False
    assert result["mutation_performed"] is False


def test_classify_self_modification_risk_keeps_docs_medium(tmp_path: Path) -> None:
    data_root, proposal_path = _write_proposal(
        tmp_path,
        overrides={"target_area": "atlas_docs", "risk_level": "medium"},
    )

    result = classify_self_modification_risk(proposal_path=proposal_path, data_root=data_root)

    assert result["classification_authorized"] is True
    assert result["classification"] == "medium"
    assert result["strict_gate_required"] is False
    assert "rollback_notes" in result["required_next_gates"]


def test_classify_self_modification_risk_blocks_untrusted_proposal(tmp_path: Path) -> None:
    data_root, proposal_path = _write_proposal(
        tmp_path,
        overrides={
            "proposal_authorized": False,
            "proposal_blocked": True,
            "self_improvement_proposal_mode_enabled": False,
            "blocking_reasons": ["fixture_blocked"],
        },
    )

    result = classify_self_modification_risk(proposal_path=proposal_path, data_root=data_root)

    assert result["classification_authorized"] is False
    assert "self_improvement_proposal_authorization_required" in result["blocking_reasons"]


def test_classify_self_modification_risk_blocks_mutating_proposal_flags(tmp_path: Path) -> None:
    data_root, proposal_path = _write_proposal(
        tmp_path,
        overrides={"patch_generated": True, "self_apply_enabled": True},
    )

    result = classify_self_modification_risk(proposal_path=proposal_path, data_root=data_root)

    assert result["classification_authorized"] is False
    assert "patch_generated_must_be_false" in result["blocking_reasons"]
    assert "self_apply_enabled_must_be_false" in result["blocking_reasons"]


def test_write_and_load_self_modification_risk_classification(tmp_path: Path) -> None:
    data_root, proposal_path = _write_proposal(tmp_path)
    result = classify_self_modification_risk(proposal_path=proposal_path, data_root=data_root)

    path = write_self_modification_risk_classification(data_root=data_root, result=result)
    loaded = load_self_modification_risk_classification(manifest_path=path, data_root=data_root)

    assert loaded["classification_id"] == result["classification_id"]
    assert loaded["classification_only"] is True


def test_no_network_or_process_execution_in_self_modification_classifier_source() -> None:
    text = Path("app/atlas/self_modification_risk_classifier.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
