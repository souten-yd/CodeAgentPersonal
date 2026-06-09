from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.atlas.capsule.contracts import CapsuleBuildRequest, CapsuleManifest
from app.atlas.play.contracts import (
    LaunchKind,
    LaunchProfile,
    PlayRequest,
    PlayRequestSource,
    PlayResourceLimits,
    PlayThreatModel,
    TrustState,
)
from app.atlas.play.paths import AtlasPlayPathLayout
from app.atlas.play.state import (
    PlaySessionEvent,
    PlaySessionState,
    reduce_play_session_state,
)
from app.portal.contracts import (
    PortalDataCommit,
    PortalDataDecision,
    PortalInstallation,
    PortalRunMode,
    PortalRunRequest,
    PortalSnapshot,
    evaluate_portal_run_policy,
)
from app.portal.paths import PortalPathLayout
from app.server import include_routers


def _static_profile() -> LaunchProfile:
    return LaunchProfile(
        profile_id="web",
        name="Static web",
        kind=LaunchKind.STATIC_WEB,
        entrypoint="index.html",
    )


def test_ppc0_contract_models_round_trip_with_schema_versions(tmp_path: Path) -> None:
    profile = _static_profile()
    request = PlayRequest(
        source=PlayRequestSource.ATLAS_BUTTON,
        project_id="demo",
        work_root=str(tmp_path / "atlas" / "projects" / "demo" / "work"),
        selected_entrypoint="index.html",
    )
    manifest = CapsuleManifest(
        package_id="demo",
        name="Demo",
        version="1.0.0",
        launch_profiles=[profile],
        default_profile_id=profile.profile_id,
    )
    installation = PortalInstallation(
        installation_id="inst_demo",
        package_id=manifest.package_id,
        version=manifest.version,
        package_path=str(tmp_path / "portal" / "packages" / "demo.portal.zip"),
        content_hash="sha256:abc",
        trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
    )
    commit = PortalDataCommit(
        installation_id=installation.installation_id,
        session_id="session_1",
        decision=PortalDataDecision.SAVE_AND_EXIT,
    )
    snapshot = PortalSnapshot(
        snapshot_id="snap_1",
        installation_id=installation.installation_id,
        source="current_data",
        data_hash="sha256:def",
    )
    build = CapsuleBuildRequest(
        project_id="demo",
        play_session_id="session_1",
        selected_profile_ids=[profile.profile_id],
    )

    for model in (profile, request, manifest, installation, commit, snapshot, build):
        dumped = model.model_dump()
        assert dumped["schema_version"]
        assert type(model).model_validate(dumped) == model


def test_ppc0_unknown_launch_kind_and_command_field_fail_closed() -> None:
    with pytest.raises(ValidationError):
        LaunchProfile(
            profile_id="bad",
            name="Bad",
            kind="shell",
            entrypoint="run.sh",
        )

    with pytest.raises(ValidationError):
        LaunchProfile.model_validate(
            {
                "schema_version": "atlas.play.v1",
                "profile_id": "bad",
                "name": "Bad",
                "kind": "static_web",
                "entrypoint": "index.html",
                "command": "python -m http.server",
            }
        )

    with pytest.raises(ValidationError):
        CapsuleManifest.model_validate(
            {
                "schema_version": "atlas.capsule.v1",
                "package_id": "demo",
                "name": "Demo",
                "version": "1.0.0",
                "launch_profiles": [_static_profile().model_dump()],
                "default_profile_id": "web",
                "command": "npm run dev",
            }
        )


def test_ppc0_composite_profiles_are_structured_not_shell_commands() -> None:
    profile = LaunchProfile(
        profile_id="full_stack",
        name="Full stack",
        kind=LaunchKind.COMPOSITE,
        depends_on=["api", "web"],
    )

    assert profile.entrypoint is None
    assert profile.depends_on == ["api", "web"]
    with pytest.raises(ValidationError):
        LaunchProfile(
            profile_id="bad_composite",
            name="Bad",
            kind=LaunchKind.COMPOSITE,
            entrypoint="start-all.sh",
        )


def test_ppc0_portal_untrusted_package_runs_are_blocked_by_default() -> None:
    request = PortalRunRequest(
        installation_id="inst_untrusted",
        launch_profile_id="web",
        run_mode=PortalRunMode.CONTINUE_CURRENT_DATA,
        trust_state=TrustState.UNTRUSTED_IMPORTED_PACKAGE,
    )

    blocked = evaluate_portal_run_policy(request)
    assert blocked.allowed is False
    assert blocked.reason == "untrusted_package_run_blocked_by_default"
    assert "not OS-isolated" in blocked.warning

    override = evaluate_portal_run_policy(
        request.model_copy(update={"untrusted_override_acknowledged": True})
    )
    assert override.allowed is True
    assert override.reason == "untrusted_package_override_acknowledged"


def test_ppc0_play_state_reducer_accepts_only_forward_lifecycle_transitions() -> None:
    state = PlaySessionState.CREATED
    for event in (
        PlaySessionEvent.RESOLVE_TARGET,
        PlaySessionEvent.TARGET_RESOLVED,
        PlaySessionEvent.ENVIRONMENT_RESOLVED,
        PlaySessionEvent.PREPARED,
        PlaySessionEvent.STARTED,
        PlaySessionEvent.STOP_REQUESTED,
        PlaySessionEvent.STOPPED,
    ):
        state = reduce_play_session_state(state, event)

    assert state == PlaySessionState.STOPPED
    with pytest.raises(ValueError, match="terminal_state_transition_rejected"):
        reduce_play_session_state(state, PlaySessionEvent.STARTED)
    with pytest.raises(ValueError, match="invalid_play_session_transition"):
        reduce_play_session_state(PlaySessionState.CREATED, PlaySessionEvent.STARTED)


def test_ppc0_path_layouts_are_contained_and_reject_escape_components(tmp_path: Path) -> None:
    play = AtlasPlayPathLayout(tmp_path)
    portal = PortalPathLayout(tmp_path)

    assert play.atlas_project_work_root("demo").is_relative_to(tmp_path.resolve())
    assert play.play_session_root("session_1").is_relative_to(tmp_path.resolve())
    assert portal.quarantine_root("import_1").is_relative_to(tmp_path.resolve())
    assert portal.current_data_root("inst_1").is_relative_to(tmp_path.resolve())
    assert portal.snapshot_root("inst_1", "snap_1").is_relative_to(tmp_path.resolve())

    for bad in ("..", "../x", "x/y", r"x\y", "C:/temp", r"\\server\share"):
        with pytest.raises(ValueError):
            play.play_session_root(bad)
        with pytest.raises(ValueError):
            portal.installation_root(bad)


def test_router_capabilities_keep_no_arbitrary_command_surface() -> None:
    app = FastAPI()
    include_routers(app)
    client = TestClient(app)

    play = client.get("/api/atlas/play/capabilities").json()
    portal = client.get("/api/portal/capabilities").json()

    assert play["execution_enabled"] is True
    assert play["process_supervisor_enabled"] is True
    assert play["file_serving_enabled"] is False
    assert portal["run_enabled"] is False
    assert portal["import_enabled"] is False
    assert portal["export_enabled"] is False

    methods_by_path = {
        route.path: route.methods
        for route in app.routes
        if route.path.startswith(("/api/atlas/play", "/api/portal"))
    }
    assert methods_by_path["/api/atlas/play/capabilities"] == {"GET"}
    assert "/api/atlas/play/sessions/start" in methods_by_path
    assert not any("command" in path or "shell" in path for path in methods_by_path)
    assert methods_by_path["/api/portal/capabilities"] == {"GET"}


def test_ppc0_threat_model_and_limits_keep_execution_boundary_separate() -> None:
    threat = PlayThreatModel()
    limits = PlayResourceLimits()

    assert "not agent autonomous command execution" in threat.execution_boundary
    assert "verification allowlists" in threat.launch_adapter_authority
    assert threat.untrusted_default_run_allowed is False
    assert limits.allow_unbounded_commands is False
    assert limits.allow_host_filesystem_serving is False
    assert limits.expose_temporary_ports_directly is False
