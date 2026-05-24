from pathlib import Path

from fastapi.testclient import TestClient

from app.atlas.level1_dry_run_endpoint_skeleton import build_level1_dry_run_only_result
from app.atlas.level1_dry_run_result_artifact_capture import (
    CAPTURE_SCHEMA_VERSION,
    capture_level1_dry_run_result_artifact,
)
from app.server import create_app


def _dry_run_result() -> dict[str, object]:
    return build_level1_dry_run_only_result(
        {
            "workspace_id": "ws_1",
            "pool_id": "pool_1",
            "item_id": "item_1",
            "action_id": "action_1",
            "command_id": "pytest_file",
            "risk_level": "low",
            "dry_run_summary": "dry-run result metadata",
        }
    )


def test_scale_118_captures_dry_run_result_artifact_without_execution(tmp_path: Path) -> None:
    captured = capture_level1_dry_run_result_artifact(
        data_root=tmp_path,
        dry_run_result={**_dry_run_result(), "run_id": "run_1"},
    )

    assert captured["schema_version"] == CAPTURE_SCHEMA_VERSION
    assert captured["status"] == "captured"
    assert captured["runtime_level"] == "level_0_manual_only"
    assert captured["manual_only"] is True
    assert captured["dry_run_only"] is True
    assert captured["capture_only"] is True
    assert captured["mutation_performed"] is False
    assert captured["execution_performed"] is False
    assert captured["verification_performed"] is False
    assert captured["rollback_performed"] is False
    assert captured["retry_performed"] is False
    assert captured["remote_git_operation_performed"] is False
    assert captured["level1_execution_enabled"] is False
    assert captured["autonomous_execution_enabled"] is False
    assert captured["next_required_pr"] == "PR-ATLAS-SCALE-119"

    manifest_path = Path(str(captured["manifest_path"]))
    assert manifest_path.exists()
    assert manifest_path.is_relative_to(tmp_path)
    manifest = captured["manifest"]
    assert manifest["schema_version"] == "atlas.dry_run_artifact.v1"
    assert manifest["runtime_level"] == "level_0_manual_only"
    assert manifest["execution_enabled"] is False
    assert manifest["level1_execution_enabled"] is False
    assert manifest["autonomous_execution_enabled"] is False
    assert "scale_118_dry_run_result_artifact_capture" in manifest["policy_notes"]


def test_scale_118_endpoint_captures_under_resolved_data_root(tmp_path: Path) -> None:
    app = create_app()
    app.state.atlas_ca_data_root = str(tmp_path)
    client = TestClient(app)

    response = client.post(
        "/api/atlas/level1/dry-run-result-artifact",
        json={"workspace_id": "ws_1", "dry_run_result": {**_dry_run_result(), "run_id": "run_2"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == CAPTURE_SCHEMA_VERSION
    assert payload["status"] == "captured"
    assert payload["execution_performed"] is False
    assert payload["mutation_performed"] is False
    assert Path(payload["manifest_path"]).is_relative_to(tmp_path)


def test_scale_118_forbids_execution_mutation_remote_git_tokens() -> None:
    source = Path("app/atlas/level1_dry_run_result_artifact_capture.py").read_text(encoding="utf-8").lower()
    for token in [
        "subprocess",
        "shell=true",
        "safe_apply",
        "git push",
        "git pull",
        "git clone",
        "apply_patch",
        "rollback(",
        "retry(",
    ]:
        assert token not in source
