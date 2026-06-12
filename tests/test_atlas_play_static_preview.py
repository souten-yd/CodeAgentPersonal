from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import pytest

from app.api.atlas_play import router as atlas_play_router
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.sessions import PlaySessionManager
from app.atlas.play.static_preview import StaticPreviewError, validate_preview_request_headers


def _project(tmp_path: Path, project_id: str = "demo") -> Path:
    work = tmp_path / "atlas" / "projects" / project_id / "work"
    work.mkdir(parents=True)
    return work


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(atlas_play_router)
    return TestClient(app)


def _start_static(tmp_path: Path, work: Path, profile_id: str = "web"):
    adapter = build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id=profile_id, name="Web", kind=LaunchKind.STATIC_WEB, entrypoint="index.html"),
    )
    return PlaySessionManager(tmp_path).start_session(project_id=profile_id, project_root=work, adapter=adapter)


def test_static_preview_serves_nested_assets_and_records_observed_paths(tmp_path: Path) -> None:
    work = _project(tmp_path, "web")
    (work / "assets").mkdir()
    (work / "index.html").write_text("<script src='/assets/app.js'></script>", encoding="utf-8")
    (work / "assets" / "app.js").write_text("console.log('ok')\n", encoding="utf-8")
    session = _start_static(tmp_path, work, "web")
    client = _client(tmp_path)

    index = client.get(f"/api/atlas/play/preview/{session.session_id}/index.html")
    asset = client.get(f"/api/atlas/play/preview/{session.session_id}/assets/app.js")
    observations = client.get(f"/api/atlas/play/preview/{session.session_id}/observations").json()
    PlaySessionManager(tmp_path).stop_session(session.session_id)

    assert index.status_code == 200
    assert index.headers["x-atlas-play-session"] == session.session_id
    assert asset.status_code == 200
    assert "console.log" in asset.text
    assert observations["served_paths"] == ["index.html", "assets/app.js"]


def test_static_preview_uses_spa_fallback_for_extensionless_routes(tmp_path: Path) -> None:
    work = _project(tmp_path, "spa")
    (work / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    session = _start_static(tmp_path, work, "spa")
    client = _client(tmp_path)

    response = client.get(f"/api/atlas/play/preview/{session.session_id}/settings/profile")
    PlaySessionManager(tmp_path).stop_session(session.session_id)

    assert response.status_code == 200
    assert "spa shell" in response.text
    assert response.headers["x-atlas-play-path"] == "index.html"


def test_static_preview_rejects_invalid_session_traversal_and_cross_session_access(tmp_path: Path) -> None:
    work_a = _project(tmp_path, "a")
    work_b = _project(tmp_path, "b")
    (work_a / "index.html").write_text("A", encoding="utf-8")
    (work_b / "index.html").write_text("B", encoding="utf-8")
    (work_b / "secret.txt").write_text("secret-b", encoding="utf-8")
    session_a = _start_static(tmp_path, work_a, "a")
    session_b = _start_static(tmp_path, work_b, "b")
    client = _client(tmp_path)

    missing = client.get("/api/atlas/play/preview/nope/index.html")
    traversal = client.get(f"/api/atlas/play/preview/{session_a.session_id}/..%2Fsecret.txt")
    cross_session = client.get(f"/api/atlas/play/preview/{session_a.session_id}/secret.txt")
    own_session = client.get(f"/api/atlas/play/preview/{session_b.session_id}/secret.txt")
    manager = PlaySessionManager(tmp_path)
    manager.stop_session(session_a.session_id)
    manager.stop_session(session_b.session_id)

    assert missing.status_code == 404
    assert traversal.status_code == 403
    assert cross_session.status_code == 404
    assert own_session.status_code == 200
    assert own_session.text == "secret-b"


def test_static_preview_validates_host_and_origin_headers(tmp_path: Path) -> None:
    work = _project(tmp_path, "headers")
    (work / "index.html").write_text("headers", encoding="utf-8")
    session = _start_static(tmp_path, work, "headers")
    client = _client(tmp_path)

    ok = client.get(
        f"/api/atlas/play/preview/{session.session_id}/index.html",
        headers={"host": "localhost", "origin": "http://localhost"},
    )
    bad_host = client.get(f"/api/atlas/play/preview/{session.session_id}/index.html", headers={"host": "evil.example"})
    bad_origin = client.get(
        f"/api/atlas/play/preview/{session.session_id}/index.html",
        headers={"origin": "https://evil.example"},
    )
    PlaySessionManager(tmp_path).stop_session(session.session_id)

    assert ok.status_code == 200
    assert bad_host.status_code == 403
    assert bad_host.json()["detail"]["error"] == "host_not_allowed"
    assert bad_origin.status_code == 403
    assert bad_origin.json()["detail"]["error"] == "origin_not_allowed"


def test_preview_headers_allow_lan_and_runpod_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_PREVIEW_ALLOWED_HOSTS", raising=False)
    # iPhone on the same LAN reaches the host by its private IP.
    validate_preview_request_headers({"host": "192.168.1.42:7860", "origin": "http://192.168.1.42:7860"})
    # RunPod exposes the port through its proxy domain.
    validate_preview_request_headers(
        {"host": "abc123-7860.proxy.runpod.net", "origin": "https://abc123-7860.proxy.runpod.net"}
    )
    # Explicitly pinned custom host via env.
    monkeypatch.setenv("ATLAS_PREVIEW_ALLOWED_HOSTS", "my-tunnel.example.com")
    validate_preview_request_headers({"host": "my-tunnel.example.com", "origin": "https://my-tunnel.example.com"})


def test_preview_headers_allow_local_network_hostnames(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_PREVIEW_ALLOWED_HOSTS", raising=False)
    # iPhone reaching a Windows/LAN box by its bare machine name (single label).
    validate_preview_request_headers({"host": "DESKTOP-AB12:7860", "origin": "http://DESKTOP-AB12:7860"})
    # mDNS / Bonjour name as resolved natively on iOS.
    validate_preview_request_headers({"host": "kkens-pc.local", "origin": "http://kkens-pc.local"})
    # Common router-assigned local TLDs.
    validate_preview_request_headers({"host": "kkens-pc.lan:7860", "origin": "http://kkens-pc.lan:7860"})
    # Tailscale / CGNAT shared address space (not RFC1918 private).
    validate_preview_request_headers({"host": "100.101.102.103", "origin": "http://100.101.102.103"})


def test_preview_headers_reject_public_host_and_cross_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATLAS_PREVIEW_ALLOWED_HOSTS", raising=False)
    # DNS-rebinding style arbitrary public hostname is still rejected.
    with pytest.raises(StaticPreviewError) as host_exc:
        validate_preview_request_headers({"host": "evil.example"})
    assert host_exc.value.code == "host_not_allowed"
    # A LAN host targeted from a foreign public origin is cross-origin.
    with pytest.raises(StaticPreviewError) as origin_exc:
        validate_preview_request_headers({"host": "192.168.1.42", "origin": "https://evil.example"})
    assert origin_exc.value.code == "origin_not_allowed"


def test_static_preview_ingests_console_and_failed_request_events(tmp_path: Path) -> None:
    work = _project(tmp_path, "events")
    (work / "index.html").write_text("events", encoding="utf-8")
    session = _start_static(tmp_path, work, "events")
    client = _client(tmp_path)

    console = client.post(
        f"/api/atlas/play/preview/{session.session_id}/console",
        json={"level": "error", "message": "ReferenceError: x is not defined", "source": "index.html:1"},
    )
    failed = client.post(
        f"/api/atlas/play/preview/{session.session_id}/failed-request",
        json={"url": "/missing.png", "method": "GET", "status_code": 404, "resource_type": "image", "reason": "not_found"},
    )
    observations = client.get(f"/api/atlas/play/preview/{session.session_id}/observations").json()
    PlaySessionManager(tmp_path).stop_session(session.session_id)

    assert console.status_code == 200
    assert failed.status_code == 200
    assert observations["console_events"][0]["level"] == "error"
    assert observations["failed_requests"][0]["url"] == "/missing.png"
