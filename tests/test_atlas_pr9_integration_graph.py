from __future__ import annotations

from pathlib import Path

from agent.atlas_integration_checker import AtlasIntegrationChecker

_CHECKER = AtlasIntegrationChecker()


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    fp = tmp_path / rel
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return fp


# ── check_entrypoint_import_graph ──────────────────────────────────────────────

def test_direct_script_src_is_reachable(tmp_path):
    _write(tmp_path, "index.html", '<script src="js/main.js"></script>')
    _write(tmp_path, "js/main.js", "console.log('hi');")
    result = _CHECKER.check_entrypoint_import_graph(
        tmp_path / "index.html", project_root=tmp_path, generated_files=["js/main.js"]
    )
    assert result["status"] == "passed"
    assert "js/main.js" in result["reachable"]
    assert result["disconnected"] == []


def test_transitive_import_is_reachable(tmp_path):
    _write(tmp_path, "index.html", '<script src="js/main.js"></script>')
    _write(tmp_path, "js/main.js", 'import "./renderer.js";')
    _write(tmp_path, "js/renderer.js", "export function render(){}")
    result = _CHECKER.check_entrypoint_import_graph(
        tmp_path / "index.html", project_root=tmp_path, generated_files=["js/renderer.js"]
    )
    assert result["status"] == "passed"
    assert "js/renderer.js" in result["reachable"]


def test_disconnected_user_facing_module_fails(tmp_path):
    _write(tmp_path, "index.html", '<script src="js/main.js"></script>')
    _write(tmp_path, "js/main.js", "console.log('hi');")
    _write(tmp_path, "js/renderer.js", "export function render(){}")
    result = _CHECKER.check_entrypoint_import_graph(
        tmp_path / "index.html", project_root=tmp_path, generated_files=["js/renderer.js"]
    )
    assert result["status"] == "failed"
    assert "js/renderer.js" in result["disconnected"]
    assert any(f["type"] == "disconnected_module" and f["severity"] == "failed" for f in result["findings"])


def test_disconnected_test_module_only_warns(tmp_path):
    _write(tmp_path, "index.html", '<script src="js/main.js"></script>')
    _write(tmp_path, "js/main.js", "console.log('hi');")
    _write(tmp_path, "js/mock.js", "")
    result = _CHECKER.check_entrypoint_import_graph(
        tmp_path / "index.html", project_root=tmp_path, generated_files=["js/mock.js"]
    )
    assert result["status"] == "warned"
    disc = [f for f in result["findings"] if f["type"] == "disconnected_module"]
    assert all(f["severity"] == "warning" for f in disc)


def test_css_connected_via_link_href(tmp_path):
    _write(tmp_path, "index.html", '<link rel="stylesheet" href="css/style.css"><script src="js/main.js"></script>')
    _write(tmp_path, "js/main.js", "")
    _write(tmp_path, "css/style.css", "body{}")
    result = _CHECKER.check_entrypoint_import_graph(
        tmp_path / "index.html", project_root=tmp_path, generated_files=["js/main.js", "css/style.css"]
    )
    assert result["status"] == "passed"
    assert "css/style.css" not in result["disconnected"]


def test_external_script_not_followed(tmp_path):
    _write(tmp_path, "index.html", '<script src="https://cdn.example.com/lib.js"></script><script src="js/main.js"></script>')
    _write(tmp_path, "js/main.js", "")
    result = _CHECKER.check_entrypoint_import_graph(
        tmp_path / "index.html", project_root=tmp_path, generated_files=["js/main.js"]
    )
    assert result["status"] == "passed"


def test_missing_html_returns_failed(tmp_path):
    result = _CHECKER.check_entrypoint_import_graph(
        tmp_path / "missing.html", project_root=tmp_path, generated_files=["js/main.js"]
    )
    assert result["status"] == "failed"
    assert any(f["type"] == "entrypoint_missing" for f in result["findings"])


def test_dynamic_import_followed(tmp_path):
    _write(tmp_path, "index.html", '<script src="js/main.js"></script>')
    _write(tmp_path, "js/main.js", "import('./lazy.js').then(m => m.run())")
    _write(tmp_path, "js/lazy.js", "export function run(){}")
    result = _CHECKER.check_entrypoint_import_graph(
        tmp_path / "index.html", project_root=tmp_path, generated_files=["js/lazy.js"]
    )
    assert "js/lazy.js" in result["reachable"]


# ── _is_external helper ────────────────────────────────────────────────────────

def test_is_external_not_called_for_local_imports(tmp_path):
    _write(tmp_path, "index.html", '<script src="js/main.js"></script>')
    _write(tmp_path, "js/main.js", 'import "https://cdn.example.com/lib.js"; import "./local.js";')
    _write(tmp_path, "js/local.js", "")
    result = _CHECKER.check_entrypoint_import_graph(
        tmp_path / "index.html", project_root=tmp_path, generated_files=["js/local.js"]
    )
    # local.js is reachable; external import is skipped
    assert "js/local.js" in result["reachable"]


# ── _normalize_join ────────────────────────────────────────────────────────────

def test_normalize_join_handles_parent_traversal():
    from agent.atlas_integration_checker import AtlasIntegrationChecker
    c = AtlasIntegrationChecker()
    assert c._normalize_join("js/utils", "../renderer.js") == "js/renderer.js"
    assert c._normalize_join("", "js/main.js") == "js/main.js"
    assert c._normalize_join("a/b/c", "../../x.js") == "a/x.js"
