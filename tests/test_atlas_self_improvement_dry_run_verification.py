import json
from pathlib import Path

import pytest

from app.atlas.self_improvement_dry_run_verification import (
    create_self_improvement_dry_run_verification,
    load_self_improvement_dry_run_verification,
    write_self_improvement_dry_run_verification,
)


def _write_patch_preview(tmp_path: Path, *, overrides: dict[str, object] | None = None) -> tuple[Path, Path, Path]:
    data_root = tmp_path / "data"
    project_root = tmp_path / "project"
    (project_root / "tests").mkdir(parents=True)
    preview_dir = data_root / "atlas" / "self_improvement_patch_previews" / "preview_1"
    preview_dir.mkdir(parents=True)
    preview: dict[str, object] = {
        "schema_version": "atlas.self_improvement_patch_preview.v1",
        "preview_id": "preview_1",
        "created_at": "2026-05-26T00:00:00+00:00",
        "track_pr": "PR-ATLAS-SCALE-142",
        "next_required_pr": "PR-ATLAS-SCALE-143",
        "classification_path": str(data_root / "classification.json"),
        "data_root": str(data_root),
        "reviewer": "atlas",
        "target_repo": "KasaneCore",
        "target_area": "atlas_runtime",
        "risk_classification": "strict",
        "strict_gate_required": True,
        "summary": "Preview self-improvement patch paths.",
        "proposed_changes": [
            {
                "relative_path": "app/atlas/self_improvement_dry_run_verification.py",
                "change_type": "create",
                "rationale": "Add dry-run verification metadata helper.",
                "preview_only": True,
                "content_included": False,
                "diff_included": False,
                "patch_generated": False,
                "patch_applied": False,
            }
        ],
        "preview_authorized": True,
        "preview_blocked": False,
        "blocking_reasons": [],
        "self_improvement_patch_preview_enabled": True,
        "preview_only": True,
        "backend_authoritative": True,
        "vue_authoritative": False,
        "vue_execution_controls_enabled": False,
        "self_modification_enabled": False,
        "self_apply_enabled": False,
        "automatic_patch_generation_enabled": False,
        "automatic_patch_apply_enabled": False,
        "automatic_verification_enabled": False,
        "autonomous_execution_enabled": False,
        "autonomous_loop_execution_enabled": False,
        "auto_continue_enabled": False,
        "execute_all_enabled": False,
        "direct_merge_enabled": False,
        "remote_git_push_enabled": False,
        "allowed_preview_actions": ["read_classification", "record_preview", "record_changed_paths", "request_human_review"],
        "forbidden_preview_actions": ["generate_patch", "apply_patch", "direct_merge"],
        "execution_performed": False,
        "mutation_performed": False,
        "patch_generated": False,
        "patch_previewed": True,
        "patch_applied": False,
        "verification_performed": False,
        "branch_created": False,
        "draft_pr_created": False,
        "draft_pr_updated": False,
    }
    if overrides:
        preview.update(overrides)
    path = preview_dir / "manifest.json"
    path.write_text(json.dumps(preview, indent=2), encoding="utf-8")
    return data_root, project_root, path


def test_create_self_improvement_dry_run_verification_authorizes_allowlisted_plan(tmp_path: Path) -> None:
    data_root, project_root, preview_path = _write_patch_preview(tmp_path)

    manifest = create_self_improvement_dry_run_verification(
        patch_preview_path=preview_path,
        data_root=data_root,
        project_path=project_root,
        proposed_commands=["pytest -q tests/test_atlas_self_improvement_dry_run_verification.py"],
    )

    assert manifest["dry_run_verification_authorized"] is True
    assert manifest["self_improvement_dry_run_verification_enabled"] is True
    assert manifest["dry_run_only"] is True
    assert manifest["verification_plan_only"] is True
    assert manifest["verification_risk_level"] == "strict_gate"
    assert manifest["allowed_commands"] == ["pytest -q tests/test_atlas_self_improvement_dry_run_verification.py"]
    assert manifest["blocked_commands"] == []
    assert manifest["automatic_verification_enabled"] is False
    assert manifest["verification_performed"] is False
    assert manifest["verification_result_fabricated"] is False
    assert manifest["patch_applied"] is False
    assert manifest["self_apply_enabled"] is False
    assert manifest["direct_merge_enabled"] is False
    assert manifest["remote_git_push_enabled"] is False
    assert manifest["execution_performed"] is False
    assert manifest["mutation_performed"] is False


def test_create_self_improvement_dry_run_verification_blocks_disallowed_commands(tmp_path: Path) -> None:
    data_root, project_root, preview_path = _write_patch_preview(tmp_path)

    manifest = create_self_improvement_dry_run_verification(
        patch_preview_path=preview_path,
        data_root=data_root,
        project_path=project_root,
        proposed_commands=["pytest", "git push origin main"],
    )

    assert manifest["dry_run_verification_authorized"] is False
    assert "only_allowlisted_verification_commands_allowed" in manifest["blocking_reasons"]
    assert "pytest" in manifest["blocked_commands"]
    assert "git push origin main" in manifest["blocked_commands"]
    assert manifest["verification_performed"] is False


def test_create_self_improvement_dry_run_verification_blocks_untrusted_preview(tmp_path: Path) -> None:
    data_root, project_root, preview_path = _write_patch_preview(
        tmp_path,
        overrides={
            "preview_authorized": False,
            "preview_blocked": True,
            "self_improvement_patch_preview_enabled": False,
            "blocking_reasons": ["fixture_blocked"],
            "patch_previewed": False,
        },
    )

    manifest = create_self_improvement_dry_run_verification(
        patch_preview_path=preview_path,
        data_root=data_root,
        project_path=project_root,
        proposed_commands=["pytest -q tests/test_atlas_self_improvement_dry_run_verification.py"],
    )

    assert manifest["dry_run_verification_authorized"] is False
    assert "authorized_patch_preview_required" in manifest["blocking_reasons"]
    assert "patch_preview_enabled_required" in manifest["blocking_reasons"]


def test_mutating_patch_preview_flags_are_rejected_before_verification(tmp_path: Path) -> None:
    data_root, project_root, preview_path = _write_patch_preview(
        tmp_path,
        overrides={"patch_applied": True, "self_apply_enabled": True},
    )

    with pytest.raises(ValueError, match="invariant_violation"):
        create_self_improvement_dry_run_verification(
            patch_preview_path=preview_path,
            data_root=data_root,
            project_path=project_root,
            proposed_commands=["pytest -q tests/test_atlas_self_improvement_dry_run_verification.py"],
        )


def test_write_and_load_self_improvement_dry_run_verification(tmp_path: Path) -> None:
    data_root, project_root, preview_path = _write_patch_preview(tmp_path)
    manifest = create_self_improvement_dry_run_verification(
        patch_preview_path=preview_path,
        data_root=data_root,
        project_path=project_root,
        proposed_commands=["python -m py_compile app/atlas/self_improvement_dry_run_verification.py"],
    )

    path = write_self_improvement_dry_run_verification(data_root=data_root, manifest=manifest)
    loaded = load_self_improvement_dry_run_verification(manifest_path=path, data_root=data_root)

    assert loaded["verification_id"] == manifest["verification_id"]
    assert loaded["dry_run_only"] is True
    assert loaded["verification_performed"] is False


def test_no_network_or_process_execution_in_self_improvement_dry_run_verification_source() -> None:
    text = Path("app/atlas/self_improvement_dry_run_verification.py").read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "os.system" not in text
    assert "requests" not in text
    assert "Github" not in text
