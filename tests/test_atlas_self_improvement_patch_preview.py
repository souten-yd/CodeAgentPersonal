import json
from pathlib import Path

import pytest

from app.atlas.self_improvement_patch_preview import (
    create_self_improvement_patch_preview,
    load_self_improvement_patch_preview,
    write_self_improvement_patch_preview,
)


def _write_classification(tmp_path: Path, *, overrides: dict[str, object] | None = None) -> tuple[Path, Path]:
    data_root = tmp_path / "data"
    classification_dir = data_root / "atlas" / "self_modification_risk_classifications" / "classification_1"
    classification_dir.mkdir(parents=True)
    classification: dict[str, object] = {
        "schema_version": "atlas.self_modification_risk_classification.v1",
        "classification_id": "classification_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "track_pr": "PR-ATLAS-SCALE-141",
        "next_required_pr": "PR-ATLAS-SCALE-142",
        "proposal_path": str(data_root / "proposal.json"),
        "data_root": str(data_root),
        "reviewer": "atlas",
        "target_repo": "KasaneCore",
        "target_area": "atlas_runtime",
        "proposal_risk_level": "strict",
        "classification": "strict",
        "classification_authorized": True,
        "classification_blocked": False,
        "blocking_reasons": [],
        "strict_self_modification_risk_classifier_enabled": True,
        "classification_only": True,
        "strict_gate_required": True,
        "human_review_required": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "patch_preview_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "allowed_classifier_actions": ["read_proposal", "classify_risk", "record_required_gates", "request_human_review"],
        "forbidden_classifier_actions": ["generate_patch", "apply_patch", "direct_merge"],
        "required_next_gates": ["human_review", "proposal_traceability", "no_self_apply", "strict_gate"],
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_previewed": False,
        "patch_applied": False,
        "verification_performed": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    if overrides:
        classification.update(overrides)
    path = classification_dir / "manifest.json"
    path.write_text(json.dumps(classification, indent=2), encoding="utf-8")
    return data_root, path


def _changes() -> list[dict[str, object]]:
    return [
        {
            "relative_path": "app/atlas/self_improvement_patch_preview.py",
            "change_type": "create",
            "rationale": "Add preview-only helper after risk classification.",
        },
        {
            "relative_path": "tests/test_atlas_self_improvement_patch_preview.py",
            "change_type": "create",
            "rationale": "Cover preview-only invariants.",
        },
    ]


def test_create_self_improvement_patch_preview_authorizes_preview_only(tmp_path: Path) -> None:
    data_root, classification_path = _write_classification(tmp_path)

    preview = create_self_improvement_patch_preview(
        classification_path=classification_path,
        data_root=data_root,
        summary="Preview a self-improvement patch without generating or applying it.",
        proposed_changes=_changes(),
    )

    assert preview["preview_authorized"] is True
    assert preview["self_improvement_patch_preview_enabled"] is True
    assert preview["preview_only"] is True
    assert preview["risk_classification"] == "strict"
    assert preview["strict_gate_required"] is True
    assert preview["patch_previewed"] is True
    assert preview["patch_generated"] is False
    assert preview["patch_applied"] is False
    assert preview["self_modification_enabled"] is False
    assert preview["self_apply_enabled"] is False
    assert preview["automatic_patch_generation_enabled"] is False
    assert preview["automatic_patch_apply_enabled"] is False
    assert preview["automatic_verification_enabled"] is False
    assert preview["direct_merge_enabled"] is False
    assert preview["remote_git_push_enabled"] is False
    assert preview["execution_performed"] is False
    assert preview["mutation_performed"] is False
    assert preview["proposed_changes"][0]["content_included"] is False
    assert preview["proposed_changes"][0]["diff_included"] is False


def test_create_self_improvement_patch_preview_blocks_untrusted_classification(tmp_path: Path) -> None:
    data_root, classification_path = _write_classification(
        tmp_path,
        overrides={
            "classification_authorized": False,
            "classification_blocked": True,
            "strict_self_modification_risk_classifier_enabled": False,
            "blocking_reasons": ["fixture_blocked"],
        },
    )

    preview = create_self_improvement_patch_preview(
        classification_path=classification_path,
        data_root=data_root,
        summary="Blocked preview.",
        proposed_changes=_changes(),
    )

    assert preview["preview_authorized"] is False
    assert preview["self_improvement_patch_preview_enabled"] is False
    assert "authorized_risk_classification_required" in preview["blocking_reasons"]
    assert "risk_classifier_enabled_required" in preview["blocking_reasons"]
    assert preview["patch_previewed"] is False


def test_create_self_improvement_patch_preview_blocks_unsafe_change_paths(tmp_path: Path) -> None:
    data_root, classification_path = _write_classification(tmp_path)

    preview = create_self_improvement_patch_preview(
        classification_path=classification_path,
        data_root=data_root,
        summary="Preview unsafe paths.",
        proposed_changes=[
            {"relative_path": "../escape.py", "change_type": "create", "rationale": "bad"},
            {"relative_path": "app/atlas/ok.py", "change_type": "execute", "rationale": "bad"},
        ],
    )

    assert preview["preview_authorized"] is False
    assert "change_0_path_traversal_forbidden" in preview["blocking_reasons"]
    assert "change_1_change_type_not_allowed" in preview["blocking_reasons"]


def test_mutating_classification_flags_are_rejected_before_preview(tmp_path: Path) -> None:
    data_root, classification_path = _write_classification(
        tmp_path,
        overrides={"patch_generated": True, "self_apply_enabled": True},
    )

    with pytest.raises(ValueError, match="invariant_violation"):
        create_self_improvement_patch_preview(
            classification_path=classification_path,
            data_root=data_root,
            summary="Invalid classification.",
            proposed_changes=_changes(),
        )


def test_write_and_load_self_improvement_patch_preview(tmp_path: Path) -> None:
    data_root, classification_path = _write_classification(tmp_path)
    preview = create_self_improvement_patch_preview(
        classification_path=classification_path,
        data_root=data_root,
        summary="Roundtrip preview.",
        proposed_changes=_changes(),
    )

    path = write_self_improvement_patch_preview(data_root=data_root, preview=preview)
    loaded = load_self_improvement_patch_preview(manifest_path=path, data_root=data_root)

    assert loaded["preview_id"] == preview["preview_id"]
    assert loaded["preview_only"] is True
    assert loaded["patch_applied"] is False


def test_no_network_or_process_execution_in_self_improvement_patch_preview_source() -> None:
    text = Path("app/atlas/self_improvement_patch_preview.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
