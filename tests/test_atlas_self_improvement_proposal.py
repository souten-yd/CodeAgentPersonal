import json
from pathlib import Path

from app.atlas.self_improvement_proposal import (
    create_self_improvement_proposal,
    load_self_improvement_proposal,
    write_self_improvement_proposal,
)


def _write_level3_candidate(tmp_path: Path, *, overrides: dict[str, object] | None = None) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    candidate_dir = data_root / "atlas" / "level3_autonomous_loop_candidates" / "candidate_1"
    candidate_dir.mkdir(parents=True)
    candidate: dict[str, object] = {
        "schema_version": "atlas.level3_autonomous_loop_candidate.v1",
        "candidate_id": "candidate_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "transition_pr": "PR-ATLAS-SCALE-139",
        "next_required_pr": "PR-ATLAS-SCALE-140",
        "previous_runtime_level": "level_2_guarded_bounded_loop",
        "runtime_level": "level_3_autonomous_implementation_loop_candidate",
        "target_runtime_level": "level_3_autonomous_implementation_loop_candidate",
        "candidate_authorized": True,
        "candidate_blocked": False,
        "blocking_reasons": [],
        "level2_checkpoint_path": str(data_root / "checkpoint.json"),
        "data_root": str(data_root),
        "level3_autonomous_loop_candidate_enabled": True,
        "autonomous_loop_execution_enabled": False,
        "autonomous_execution_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "self_modification_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "backend_authoritative": True,
        "draft_pr_only": True,
        "human_approval_required_for_apply": True,
        "human_approval_required_for_retry": True,
        "dry_run_required_before_apply": True,
        "stop_gate_required": True,
        "artifact_capture_required": True,
        "verification_allowlist_required": True,
        "max_iterations": 2,
        "max_retries": 1,
        "max_changed_files": 1,
        "max_runtime_minutes": 20,
        "max_risk_level": "low",
        "verification_commands": ["pytest", "atlas_smoke"],
        "allowed_candidate_actions": ["plan_from_requirement", "request_human_approval"],
        "forbidden_candidate_actions": ["execute_command", "apply_patch", "direct_merge"],
        "execution_performed": False,
        "mutation_performed": False,
        "verification_performed": False,
        "retry_performed": False,
        "rollback_performed": False,
        "restore_performed": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    if overrides:
        candidate.update(overrides)
    path = candidate_dir / "manifest.json"
    path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    return data_root, path


def test_create_self_improvement_proposal_authorizes_proposal_only(tmp_path: Path) -> None:
    data_root, candidate_path = _write_level3_candidate(tmp_path)

    proposal = create_self_improvement_proposal(
        level3_candidate_path=candidate_path,
        data_root=data_root,
        target_repo="KasaneCore",
        target_area="atlas_runtime",
        problem_statement="Atlas needs stricter self-improvement planning before patch preview.",
        proposed_direction="Record a proposal-only artifact before any self-modification classifier or preview.",
        acceptance_criteria=["proposal artifact is created", "no patch is generated"],
        approval_status="approved",
        explicit_decision="approve",
    )

    assert proposal["proposal_authorized"] is True
    assert proposal["self_improvement_proposal_mode_enabled"] is True
    assert proposal["proposal_only"] is True
    assert proposal["target_repo"] == "KasaneCore"
    assert proposal["self_modification_enabled"] is False
    assert proposal["self_apply_enabled"] is False
    assert proposal["automatic_patch_generation_enabled"] is False
    assert proposal["automatic_patch_apply_enabled"] is False
    assert proposal["direct_merge_enabled"] is False
    assert proposal["remote_git_push_enabled"] is False
    assert proposal["execution_performed"] is False
    assert proposal["mutation_performed"] is False
    assert proposal["patch_generated"] is False


def test_create_self_improvement_proposal_blocks_without_approval(tmp_path: Path) -> None:
    data_root, candidate_path = _write_level3_candidate(tmp_path)

    proposal = create_self_improvement_proposal(
        level3_candidate_path=candidate_path,
        data_root=data_root,
        target_repo="KasaneCore",
        target_area="atlas_tests",
        problem_statement="Need a test proposal.",
        proposed_direction="Record proposal only.",
        acceptance_criteria=["blocked without approval"],
    )

    assert proposal["proposal_authorized"] is False
    assert proposal["self_improvement_proposal_mode_enabled"] is False
    assert "explicit_human_approval_required" in proposal["blocking_reasons"]


def test_create_self_improvement_proposal_blocks_invalid_scope(tmp_path: Path) -> None:
    data_root, candidate_path = _write_level3_candidate(tmp_path)

    proposal = create_self_improvement_proposal(
        level3_candidate_path=candidate_path,
        data_root=data_root,
        target_repo="OtherRepo",
        target_area="random_area",
        problem_statement="Need a test proposal.",
        proposed_direction="Record proposal only.",
        acceptance_criteria=["invalid scope is blocked"],
        approval_status="approved",
        explicit_decision="approve",
    )

    assert proposal["proposal_authorized"] is False
    assert "target_repo_not_allowed" in proposal["blocking_reasons"]
    assert "target_area_not_allowed" in proposal["blocking_reasons"]


def test_create_self_improvement_proposal_blocks_untrusted_level3_candidate(tmp_path: Path) -> None:
    data_root, candidate_path = _write_level3_candidate(
        tmp_path,
        overrides={
            "candidate_authorized": False,
            "candidate_blocked": True,
            "runtime_level": "level_2_guarded_bounded_loop",
            "level3_autonomous_loop_candidate_enabled": False,
            "blocking_reasons": ["fixture_blocked"],
        },
    )

    proposal = create_self_improvement_proposal(
        level3_candidate_path=candidate_path,
        data_root=data_root,
        target_repo="CodeAgentPersonal",
        target_area="atlas_safety",
        problem_statement="Need a safety proposal.",
        proposed_direction="Record proposal only.",
        acceptance_criteria=["untrusted candidate is blocked"],
        approval_status="approved",
        explicit_decision="approve",
    )

    assert proposal["proposal_authorized"] is False
    assert "level3_candidate_authorization_required" in proposal["blocking_reasons"]
    assert "level3_candidate_runtime_required" in proposal["blocking_reasons"]
    assert "level3_candidate_required" in proposal["blocking_reasons"]


def test_write_and_load_self_improvement_proposal(tmp_path: Path) -> None:
    data_root, candidate_path = _write_level3_candidate(tmp_path)
    proposal = create_self_improvement_proposal(
        level3_candidate_path=candidate_path,
        data_root=data_root,
        target_repo="KasaneCore",
        target_area="atlas_docs",
        problem_statement="Need a docs proposal.",
        proposed_direction="Record docs proposal only.",
        acceptance_criteria=["roundtrip works"],
        approval_status="approved",
        explicit_decision="approve",
    )

    path = write_self_improvement_proposal(data_root=data_root, proposal=proposal)
    loaded = load_self_improvement_proposal(manifest_path=path, data_root=data_root)

    assert loaded["proposal_id"] == proposal["proposal_id"]
    assert loaded["proposal_only"] is True


def test_no_network_or_process_execution_in_self_improvement_source() -> None:
    text = Path("app/atlas/self_improvement_proposal.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
