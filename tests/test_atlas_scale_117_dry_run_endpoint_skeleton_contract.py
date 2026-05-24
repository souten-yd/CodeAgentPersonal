from pathlib import Path

from fastapi.testclient import TestClient

from app.atlas.level1_dry_run_endpoint_skeleton import (
    RUNTIME_LEVEL,
    SCHEMA_VERSION,
    build_level1_dry_run_only_result,
)
from app.server import create_app


def test_scale_117_builder_is_dry_run_only_and_non_mutating() -> None:
    payload = build_level1_dry_run_only_result(
        {
            "workspace_id": "ws_1",
            "pool_id": "pool_1",
            "item_id": "item_1",
            "action_id": "action_1",
            "command_id": "pytest_file",
            "risk_level": "low",
            "dry_run_summary": "review metadata only",
        }
    )

    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["status"] == "dry_run_only_skeleton"
    assert payload["runtime_level"] == RUNTIME_LEVEL
    assert payload["manual_only"] is True
    assert payload["dry_run_only"] is True
    assert payload["advisory_only"] is True
    assert payload["backend_authoritative"] is True
    assert payload["vue_authoritative"] is False
    assert payload["mutation_performed"] is False
    assert payload["execution_performed"] is False
    assert payload["artifact_persisted"] is False
    assert payload["level1_execution_enabled"] is False
    assert payload["autonomous_execution_enabled"] is False
    assert payload["automatic_patch_apply_enabled"] is False
    assert payload["remote_git_operations_enabled"] is False
    assert payload["next_required_pr"] == "PR-ATLAS-SCALE-118"


def test_scale_117_endpoint_returns_metadata_without_persistence(tmp_path: Path) -> None:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/atlas/level1/dry-run-only",
        json={"pool_id": "pool_1", "item_id": "item_1", "command_id": "pytest_file"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["pool_id"] == "pool_1"
    assert payload["item_id"] == "item_1"
    assert payload["command_id"] == "pytest_file"
    assert payload["execution_performed"] is False
    assert payload["mutation_performed"] is False
    assert not (tmp_path / "atlas").exists()


def test_scale_117_forbidden_capability_tokens_not_introduced() -> None:
    source = Path("app/atlas/level1_dry_run_endpoint_skeleton.py").read_text(encoding="utf-8").lower()
    forbidden = [
        "subprocess",
        "safe_apply",
        "git push",
        "git pull",
        "git clone",
        "shell=true",
        "write_text",
        "open(",
    ]

    for token in forbidden:
        assert token not in source
