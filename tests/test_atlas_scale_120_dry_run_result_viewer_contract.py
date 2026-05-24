from pathlib import Path


def test_scale_120_dry_run_result_viewer_is_display_only() -> None:
    text = Path("web/atlas-next/src/components/DryRunResultViewer.vue").read_text(encoding="utf-8").lower()
    for marker in [
        "dry-run result viewer",
        "scale-120 display-only",
        "dry-run artifact:",
        "latest run:",
        "workflow snapshot:",
        "backend-owned result note",
        "actions unavailable in scale-120",
        "displayed only when provided by backend workflow_state",
    ]:
        assert marker in text

    for banned in [
        "<button",
        "@click",
        "submit",
        "fetch(",
        "atlasclient",
        "/dry-run",
        "/execute",
        "/apply",
        "/verify",
        "/rollback",
        "/restore",
        "/retry",
        "/continue",
    ]:
        assert banned not in text


def test_scale_120_app_mounts_viewer_without_changing_client_endpoints() -> None:
    app = Path("web/atlas-next/src/components/AtlasNextApp.vue").read_text(encoding="utf-8")
    client = Path("web/atlas-next/src/api/atlasClient.ts").read_text(encoding="utf-8")

    assert "DryRunResultViewer" in app
    assert "<DryRunResultViewer :snapshot=\"snapshot\" />" in app
    assert "/api/atlas/workflow-state/read-only" in client
    assert "/api/atlas/plan-pools" in client
    for banned in [
        "/api/atlas/level1/dry-run-result-artifact",
        "/dry-run",
        "/execute",
        "/apply",
        "/verify",
        "/rollback",
        "/restore",
        "/retry",
        "/continue",
    ]:
        assert banned not in client


def test_scale_120_manifest_records_display_only_viewer() -> None:
    manifest = Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8")
    assert '"vue_next_dry_run_result_viewer_checkpoint": "PR-ATLAS-SCALE-120"' in manifest
    assert '"vue_next_dry_run_result_viewer_enabled": true' in manifest
    assert '"vue_next_dry_run_result_viewer_display_only": true' in manifest
    assert '"vue_next_dry_run_result_viewer_starts_dry_run": false' in manifest
    assert '"vue_next_dry_run_result_viewer_captures_artifact": false' in manifest
    assert '"vue_next_dry_run_result_viewer_execution_enabled": false' in manifest
