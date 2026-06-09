import zipfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_capsule import router as atlas_capsule_router
from app.atlas.capsule.builder import CapsuleBuildError, CapsuleBuilder
from app.atlas.capsule.contracts import CapsuleBuildRequest
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.environment import build_structured_launch_adapter
from app.atlas.play.file_service import sha256_file
from app.atlas.play.sessions import PlayProcessPolicy, PlaySessionRecord, PlaySessionRepository


def _project(tmp_path: Path, project_id: str = "demo") -> Path:
    work = tmp_path / "atlas" / "projects" / project_id / "work"
    work.mkdir(parents=True)
    return work


def _save_success_session(tmp_path: Path, work: Path, project_id: str = "demo") -> PlaySessionRecord:
    (work / "app.py").write_text("print('ok')\n", encoding="utf-8")
    adapter = build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id="py", name="Python", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="app.py"),
    )
    record = PlaySessionRecord(
        session_id="play-success",
        project_id=project_id,
        project_root=str(work),
        state="stopped",
        launch_profile_id="py",
        launch_kind=LaunchKind.PYTHON_SCRIPT,
        adapter=adapter.model_dump(mode="json"),
        process_policy=PlayProcessPolicy(uses_process_group=True, cleanup_strategy="test"),
        exit_code=0,
    )
    PlaySessionRepository(tmp_path).save(record)
    return record


def _request(**overrides) -> CapsuleBuildRequest:
    base = {
        "project_id": "demo",
        "play_session_id": "play-success",
        "selected_profile_ids": ["py"],
        "package_id": "demo.package",
        "name": "Demo Package",
        "version": "1.0.0",
    }
    base.update(overrides)
    return CapsuleBuildRequest(**base)


def _zip_names(path: str) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return sorted(zf.namelist())


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(atlas_capsule_router)
    return TestClient(app)


def test_capsule_build_is_deterministic_and_writes_immutable_record(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _save_success_session(tmp_path, work)
    (work / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    builder = CapsuleBuilder(tmp_path)

    first = builder.build(_request())
    second = builder.build(_request())

    assert first["record"]["content_hash"] == second["record"]["content_hash"]
    assert first["record"]["immutable"] is True
    assert Path(first["record"]["storage_path"]).exists()
    assert _zip_names(first["record"]["storage_path"]) == [
        "application/app.py",
        "application/index.html",
        "metadata/checksums.json",
        "metadata/findings.json",
        "metadata/manifest.json",
    ]


def test_capsule_build_rejects_stale_expected_hashes(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _save_success_session(tmp_path, work)
    (work / "index.html").write_text("new", encoding="utf-8")

    try:
        CapsuleBuilder(tmp_path).build(_request(expected_file_hashes={"index.html": "bad"}))
    except CapsuleBuildError as exc:
        assert exc.code == "stale_file_hash"
    else:
        raise AssertionError("stale hash must fail")


def test_capsule_build_rejects_unsuccessful_play_session(tmp_path: Path) -> None:
    work = _project(tmp_path)
    record = _save_success_session(tmp_path, work)
    record.state = "failed"
    record.exit_code = 1
    PlaySessionRepository(tmp_path).save(record)

    try:
        CapsuleBuilder(tmp_path).build(_request())
    except CapsuleBuildError as exc:
        assert exc.code == "play_session_not_successful"
    else:
        raise AssertionError("failed play session must fail")


def test_capsule_profile_selection_supports_multiple_and_validates_composite_deps(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _save_success_session(tmp_path, work)
    profiles = [
        LaunchProfile(profile_id="api", name="API", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="app.py"),
        LaunchProfile(profile_id="stack", name="Stack", kind=LaunchKind.COMPOSITE, depends_on=["api"]),
    ]
    built = CapsuleBuilder(tmp_path).build(
        _request(selected_profile_ids=["api", "stack"], launch_profiles=profiles, default_profile_id="stack")
    )

    assert [profile["profile_id"] for profile in built["manifest"]["launch_profiles"]] == ["api", "stack"]
    try:
        CapsuleBuilder(tmp_path).build(_request(selected_profile_ids=["stack"], launch_profiles=profiles, default_profile_id="stack"))
    except CapsuleBuildError as exc:
        assert exc.code == "composite_dependency_not_selected"
    else:
        raise AssertionError("missing composite dep must fail")


def test_capsule_exclusions_checksums_and_private_findings(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _save_success_session(tmp_path, work)
    (work / ".env").write_text("API_KEY=secret\n", encoding="utf-8")
    (work / "data").mkdir()
    (work / "data" / "runtime.db").write_text("runtime", encoding="utf-8")
    (work / "ca_data").mkdir()
    (work / "ca_data" / "internal.json").write_text("{}", encoding="utf-8")

    built = CapsuleBuilder(tmp_path).build(_request(expected_file_hashes={"app.py": sha256_file(work / "app.py")}))
    names = _zip_names(built["record"]["storage_path"])

    assert "application/app.py" in names
    assert "application/data/runtime.db" not in names
    assert "application/ca_data/internal.json" not in names
    assert built["checksums"]["app.py"] == sha256_file(work / "app.py")
    assert any(item["kind"] in {"env_file", "api_key"} and item["path"] == ".env" for item in built["findings"])


def test_capsule_build_api_returns_record(tmp_path: Path) -> None:
    work = _project(tmp_path)
    _save_success_session(tmp_path, work)
    client = _client(tmp_path)

    response = client.post(
        "/api/atlas/capsule/build",
        json={
            "project_id": "demo",
            "play_session_id": "play-success",
            "selected_profile_ids": ["py"],
            "package_id": "demo.package",
            "name": "Demo Package",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "built"
