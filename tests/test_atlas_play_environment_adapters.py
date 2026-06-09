import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_play import router as atlas_play_router
from app.atlas.play.contracts import LaunchKind, LaunchProfile
from app.atlas.play.environment import (
    build_structured_launch_adapter,
    resolve_node_environment,
    resolve_python_environment,
    validate_composite_launch_profiles,
)


def _project(tmp_path: Path) -> Path:
    work = tmp_path / "atlas" / "projects" / "demo" / "work"
    work.mkdir(parents=True)
    return work


def _client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    app.state.atlas_ca_data_root = str(tmp_path)
    app.include_router(atlas_play_router)
    return TestClient(app)


def test_python_environment_prefers_local_venv_and_never_allows_host_mutation(tmp_path: Path) -> None:
    work = _project(tmp_path)
    py = work / ".venv" / "Scripts" / "python.exe"
    py.parent.mkdir(parents=True)
    py.write_text("", encoding="utf-8")
    (work / "requirements.txt").write_text("fastapi\n", encoding="utf-8")

    env = resolve_python_environment(work)

    assert env.python_executable == str(py)
    assert env.missing_dependencies == []
    assert env.host_mutation_allowed is False


def test_node_environment_uses_lockfile_precedence_and_reports_malformed_package(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "package.json").write_text("{bad json", encoding="utf-8")
    (work / "pnpm-lock.yaml").write_text("lock", encoding="utf-8")

    env = resolve_node_environment(work)

    assert env.package_manager == "pnpm"
    assert "package_json_invalid" in env.missing_dependencies
    assert env.host_mutation_allowed is False


def test_structured_launch_adapters_build_loopback_only_argv_without_execution(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    (work / "app.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (work / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"}}), encoding="utf-8")

    static = build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id="web", name="Web", kind=LaunchKind.STATIC_WEB, entrypoint="index.html"),
    )
    asgi = build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id="api", name="API", kind=LaunchKind.PYTHON_ASGI, entrypoint="app.py"),
    )
    vite = build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id="vite", name="Vite", kind=LaunchKind.VITE, entrypoint="package.json"),
    )

    assert static.status == "ready"
    assert static.argv == ["serve-static", "index.html"]
    assert asgi.status in {"ready", "missing_dependency"}
    assert "127.0.0.1" in asgi.argv
    assert "{PORT}" in asgi.argv
    assert vite.argv[:3] == ["npm", "run", "dev"]
    for adapter in (static, asgi, vite):
        assert adapter.port.loopback_only is True
        assert adapter.port.expose_directly is False
        assert adapter.execution_started is False
        assert adapter.host_mutation_allowed is False


def test_adapter_blocks_disallowed_arguments_and_environment_keys(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "script.py").write_text("print('ok')\n", encoding="utf-8")

    bad_arg = build_structured_launch_adapter(
        work,
        LaunchProfile(
            profile_id="bad_arg",
            name="Bad",
            kind=LaunchKind.PYTHON_SCRIPT,
            entrypoint="script.py",
            args=["ok;rm"],
        ),
    )
    bad_env = build_structured_launch_adapter(
        work,
        LaunchProfile(
            profile_id="bad_env",
            name="Bad",
            kind=LaunchKind.PYTHON_SCRIPT,
            entrypoint="script.py",
            environment_keys=["PATH"],
        ),
    )

    assert bad_arg.status == "blocked"
    assert "disallowed_argument" in bad_arg.diagnostics
    assert bad_env.status == "blocked"
    assert "disallowed_environment_key" in bad_env.diagnostics


def test_missing_entrypoint_and_package_metadata_are_missing_dependency_outcomes(tmp_path: Path) -> None:
    work = _project(tmp_path)

    py = build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id="missing_py", name="Missing", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="missing.py"),
    )
    node = build_structured_launch_adapter(
        work,
        LaunchProfile(profile_id="node", name="Node", kind=LaunchKind.NPM_SCRIPT, entrypoint="package.json", args=["dev"]),
    )

    assert py.status == "missing_dependency"
    assert "entrypoint_missing_or_unsafe" in py.missing_dependencies
    assert node.status == "missing_dependency"
    assert "package_json_missing" in node.missing_dependencies


def test_composite_launch_profile_validation_rejects_cycles_and_unknown_dependencies() -> None:
    api = LaunchProfile(profile_id="api", name="API", kind=LaunchKind.PYTHON_SCRIPT, entrypoint="api.py")
    web = LaunchProfile(profile_id="web", name="Web", kind=LaunchKind.STATIC_WEB, entrypoint="index.html", depends_on=["api"])
    assert validate_composite_launch_profiles([api, web]).startup_order == ["api", "web"]

    cycle_a = LaunchProfile(profile_id="a", name="A", kind=LaunchKind.COMPOSITE, depends_on=["b"])
    cycle_b = LaunchProfile(profile_id="b", name="B", kind=LaunchKind.COMPOSITE, depends_on=["a"])
    cycle = validate_composite_launch_profiles([cycle_a, cycle_b])
    assert cycle.valid is False
    assert any(error.startswith("dependency_cycle") for error in cycle.errors)

    unknown = validate_composite_launch_profiles([web])
    assert unknown.valid is False
    assert "unknown_dependency:web:api" in unknown.errors


def test_environment_resolve_api_returns_structured_adapter_without_starting_execution(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    client = _client(tmp_path)

    response = client.post(
        "/api/atlas/play/environment/resolve",
        json={
            "project_id": "demo",
            "launch_profile": {
                "profile_id": "web",
                "name": "Web",
                "kind": "static_web",
                "entrypoint": "index.html",
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["argv"] == ["serve-static", "index.html"]
    assert data["port"]["host"] == "127.0.0.1"
    assert data["execution_started"] is False
