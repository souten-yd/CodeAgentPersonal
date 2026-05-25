import json
from pathlib import Path


APP = Path("web/atlas-next/src/components/AtlasNextApp.vue").read_text(encoding="utf-8")
PANEL = Path("web/atlas-next/src/components/GuardedExecutionReviewPanel.vue").read_text(encoding="utf-8")
CLIENT = Path("web/atlas-next/src/api/atlasClient.ts").read_text(encoding="utf-8")


def test_scale_126_vue_guarded_execution_review_panel_is_display_only() -> None:
    assert "GuardedExecutionReviewPanel" in APP
    assert "Guarded Execution Review (Display-only)" in PANEL
    assert "Callable execution route:</b> disabled" in PANEL
    assert "Actions unavailable in Vue" in PANEL
    assert "Runtime transition required:</b> yes" in PANEL
    assert "PR-ATLAS-SCALE-126" in CLIENT
    assert "requiresRuntimeTransition: true" in CLIENT
    assert "callableExecutionRouteEnabled: false" in CLIENT
    assert "executionEnabled: false" in CLIENT
    assert "backendAuthoritative: true" in CLIENT
    assert "vueAuthoritative: false" in CLIENT


def test_scale_126_vue_client_adds_no_execution_or_mutation_endpoints() -> None:
    combined = "\n".join([APP, PANEL, CLIENT])
    forbidden = [
        "/api/atlas/level1/execute",
        "/api/atlas/execute",
        "/safe-apply/execute",
        "/auto-safe-apply",
        "/dry-run/start",
        "/approvals/decide",
        "/patch-proposals/generate",
        "/patch-proposals/decide",
        "/change-snapshots/restore",
        "approvePlan(",
        "executePreview(",
        "applyPatch(",
        "fetch('/api/atlas/level1/execute'",
        'fetch("/api/atlas/level1/execute"',
    ]
    for token in forbidden:
        assert token not in combined


def test_scale_126_manifest_and_plan_pointers_advance_to_runtime_transition() -> None:
    phase = json.loads(Path("docs/atlas_automation_phase_manifest.json").read_text(encoding="utf-8"))
    ui = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    roadmap = Path("docs/atlas_scale_master_roadmap.md").read_text(encoding="utf-8")
    policy = Path("docs/atlas_autonomous_execution_readiness_policy.md").read_text(encoding="utf-8")

    completed_scale = int(phase["completed_automation_pr"].rsplit("-", 1)[1])
    assert completed_scale >= 126
    assert phase["current_automation_track"].startswith("PR-ATLAS-SCALE-")
    assert phase["next_automation_track"].startswith("PR-ATLAS-SCALE-")
    assert phase["autonomous_execution_enabled"] is False

    assert ui["vue_next_guarded_execution_review_checkpoint"] == "PR-ATLAS-SCALE-126"
    assert ui["vue_next_guarded_execution_review_panel_enabled"] is True
    assert ui["vue_next_guarded_execution_review_display_only"] is True
    assert ui["vue_next_guarded_execution_review_backend_authoritative"] is True
    assert ui["vue_next_guarded_execution_review_vue_authoritative"] is False
    assert ui["vue_next_guarded_execution_review_actions_enabled"] is False
    assert ui["vue_next_guarded_execution_review_next_required_pr"] == "PR-ATLAS-SCALE-127"

    assert "SCALE-126 completed: Vue guarded execution review panel" in roadmap
    assert "PR-ATLAS-SCALE-127 is the explicit Level-1 runtime transition checkpoint" in policy
