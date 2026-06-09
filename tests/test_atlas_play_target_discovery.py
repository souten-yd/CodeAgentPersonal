import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.atlas_play import router as atlas_play_router
from app.atlas.play.contracts import PlayRequestSource
from app.atlas.play.target_discovery import (
    PlayTargetResolutionRequest,
    detect_launch_candidates,
    discover_dependency_graph,
    resolve_play_target,
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


def test_play_command_and_button_resolve_same_target_and_dependencies(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "index.html").write_text(
        '<link rel="stylesheet" href="css/style.css"><script type="module" src="js/app.js"></script>',
        encoding="utf-8",
    )
    (work / "css").mkdir()
    (work / "css" / "style.css").write_text("body{background:url('../assets/bg.png')}", encoding="utf-8")
    (work / "js").mkdir()
    (work / "js" / "app.js").write_text("import './helper.js';\n", encoding="utf-8")
    (work / "js" / "helper.js").write_text("export const ok = true;\n", encoding="utf-8")
    (work / "assets").mkdir()
    (work / "assets" / "bg.png").write_bytes(b"png")

    command = resolve_play_target(
        work,
        PlayTargetResolutionRequest(
            project_id="demo",
            source=PlayRequestSource.ATLAS_COMMAND,
            command_text="/play index.html",
        ),
    )
    button = resolve_play_target(
        work,
        PlayTargetResolutionRequest(
            project_id="demo",
            source=PlayRequestSource.ATLAS_BUTTON,
            current_editor_path="index.html",
        ),
    )

    assert command.status == "resolved"
    assert button.status == "resolved"
    assert command.target and button.target
    assert command.target.entrypoint == button.target.entrypoint == "index.html"
    assert set(command.dependency_graph.files) == {
        "index.html",
        "css/style.css",
        "js/app.js",
        "js/helper.js",
        "assets/bg.png",
    }


def test_play_target_discovery_returns_selection_when_multiple_candidates(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "index.html").write_text("<h1>A</h1>", encoding="utf-8")
    (work / "admin.html").write_text("<h1>B</h1>", encoding="utf-8")

    result = resolve_play_target(
        work,
        PlayTargetResolutionRequest(project_id="demo", source=PlayRequestSource.ATLAS_BUTTON),
    )

    assert result.status == "needs_selection"
    assert {candidate.entrypoint for candidate in result.candidates} == {"admin.html", "index.html"}


def test_play_target_detection_includes_python_and_vite_package(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
    (work / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite --host 127.0.0.1"}, "devDependencies": {"vite": "^5.0.0"}}),
        encoding="utf-8",
    )

    candidates = detect_launch_candidates(work)

    by_entry = {candidate.entrypoint: candidate.launch_kind for candidate in candidates}
    assert by_entry["main.py"] == "python_asgi"
    assert by_entry["package.json"] == "vite"


def test_dependency_graph_records_missing_or_unsafe_dependencies_without_escape(tmp_path: Path) -> None:
    work = _project(tmp_path)
    outside = tmp_path / "atlas" / "projects" / "demo" / "secret.js"
    outside.write_text("secret", encoding="utf-8")
    (work / "index.html").write_text(
        '<script src="../secret.js"></script><script src="missing.js"></script>',
        encoding="utf-8",
    )

    graph = discover_dependency_graph(work, "index.html")

    assert graph.files == ["index.html"]
    assert {entry["ref"] for entry in graph.missing} == {"../secret.js", "missing.js"}
    assert "secret.js" not in graph.files


def test_play_target_resolve_api_persists_latest_dependency_graph(tmp_path: Path) -> None:
    work = _project(tmp_path)
    (work / "index.html").write_text("<script src=\"app.js\"></script>", encoding="utf-8")
    (work / "app.js").write_text("console.log('ok')\n", encoding="utf-8")
    client = _client(tmp_path)

    response = client.post(
        "/api/atlas/play/target/resolve",
        json={
            "project_id": "demo",
            "source": "atlas_command",
            "command_text": "/play index.html",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["target"]["entrypoint"] == "index.html"
    persisted = tmp_path / "atlas" / "play" / "target_graphs" / "demo" / "latest.json"
    assert persisted.exists()
    record = json.loads(persisted.read_text(encoding="utf-8"))
    assert record["resolution"]["dependency_graph"]["files"] == ["index.html", "app.js"]


def test_atlas_ui_classifies_play_without_lumen_routing() -> None:
    atlas_js = Path("web/js/atlas_claude_panel.js").read_text(encoding="utf-8")
    lumen_js = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (Path("web/js/lumen.js"), Path("web/js/lumen_api.js"), Path("web/js/lumen_tools.js"))
    )

    assert "lower === '/play' || lower.startsWith('/play ')" in atlas_js
    assert atlas_js.index("lower === '/play'") < atlas_js.index("lower === '/plan'")
    assert "resolvePlayTarget" in atlas_js
    assert "/api/atlas/play/target/resolve" not in lumen_js
    assert "'/play'" not in lumen_js
