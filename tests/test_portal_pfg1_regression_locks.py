"""PFG-1 regression locks for existing Portal behavior.

These tests pin the invariants the Portal + Model Forge program must not regress
while later PFG packages add upload import, snapshot selection, and Forge trace:
data-free export, quarantine of untrusted imports, and the absence of any
free-form command execution surface.
"""
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.portal import router as portal_router
from app.portal.contracts import (
    PortalRunMode,
    PortalRunRequest,
    TrustState,
    evaluate_portal_run_policy,
)


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(portal_router)
    return TestClient(app)


def test_capabilities_advertise_data_free_export_and_no_command_capability(tmp_path: Path) -> None:
    caps = _client(tmp_path).get("/api/portal/capabilities").json()
    # Export must never bundle runtime data.
    assert caps["package_export_includes_runtime_data"] is False
    # Core lifecycle capabilities stay enabled (Save/Snapshot/Discard live here).
    assert caps["data_management_enabled"] is True
    assert caps["run_enabled"] is True
    # There is no capability that exposes free-form command execution.
    assert not any("command" in str(key).lower() for key in caps)


def test_run_request_forbids_free_form_command_fields() -> None:
    base = dict(
        installation_id="inst-1",
        launch_profile_id="profile-1",
        trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
    )
    # A valid request constructs fine...
    PortalRunRequest(**base)
    # ...but any attempt to smuggle a free-form command is rejected by the strict
    # contract (extra="forbid"), so Portal can never run arbitrary commands.
    for field in ("command", "cmd", "args", "shell", "entrypoint_override"):
        with pytest.raises(ValidationError):
            PortalRunRequest(**base, **{field: "rm -rf /"})


def test_untrusted_import_is_quarantined_until_explicitly_acknowledged() -> None:
    untrusted = PortalRunRequest(
        installation_id="inst-1",
        launch_profile_id="profile-1",
        trust_state=TrustState.UNTRUSTED_IMPORTED_PACKAGE,
    )
    blocked = evaluate_portal_run_policy(untrusted)
    assert blocked.allowed is False
    assert blocked.reason == "untrusted_package_run_blocked_by_default"

    acknowledged = untrusted.model_copy(update={"untrusted_override_acknowledged": True})
    allowed = evaluate_portal_run_policy(acknowledged)
    assert allowed.allowed is True


def test_run_api_rejects_unknown_command_field(tmp_path: Path) -> None:
    resp = _client(tmp_path).post("/api/portal/run", json={
        "installation_id": "inst-1",
        "launch_profile_id": "profile-1",
        "trust_state": "trusted_local_capsule",
        "command": "rm -rf /",
    })
    # Unknown field is rejected by request validation before any execution path.
    assert resp.status_code == 422


def test_snapshot_run_mode_requires_snapshot_id() -> None:
    with pytest.raises(ValidationError):
        PortalRunRequest(
            installation_id="inst-1",
            launch_profile_id="profile-1",
            trust_state=TrustState.TRUSTED_LOCAL_CAPSULE,
            run_mode=PortalRunMode.START_FROM_SNAPSHOT,
        )
