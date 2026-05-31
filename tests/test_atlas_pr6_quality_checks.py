from __future__ import annotations

from pathlib import Path

from agent.atlas_integration_checker import AtlasIntegrationChecker
from agent.atlas_modular_slice_policy import check_disconnected_modules, check_god_source
from agent.atlas_placeholder_detector import detect_placeholders, scan_file_for_placeholders
from agent.atlas_requirement_tracer import AtlasRequirementTracer

_TRACER = AtlasRequirementTracer()
_CHECKER = AtlasIntegrationChecker()


# ── Requirement tracer ────────────────────────────────────────────────────────

def test_extract_requirements_produces_ids():
    reqs = _TRACER.extract_requirements("Show a color animation. Move a ball across the screen.")
    assert len(reqs) >= 1
    for req in reqs:
        assert req['requirement_id'].startswith('req_')
        assert req['status'] == 'planned'


def test_coverage_summary_with_missing_fails_success():
    reqs = _TRACER.extract_requirements("Show a color animation. Move the ball across the screen.")
    assert len(reqs) >= 2
    reqs[0] = _TRACER.update_status(reqs[0], implemented_files=["index.html"])
    # reqs[1] remains unimplemented
    summary = _TRACER.coverage_summary(reqs)
    assert summary['success_eligible'] is False
    assert summary['missing_or_partial_count'] >= 1


def test_coverage_summary_all_verified_is_success():
    reqs = _TRACER.extract_requirements("Show a color animation. Move the ball across the screen.")
    assert len(reqs) >= 2
    reqs = [_TRACER.update_status(r, implemented_files=["index.html"], verification_passed=True)
            for r in reqs]
    summary = _TRACER.coverage_summary(reqs)
    assert summary['all_verified'] is True
    assert summary['success_eligible'] is True


# ── Placeholder detector ──────────────────────────────────────────────────────

def test_placeholder_comment_detected():
    code = "def draw():\n    # placeholder\n    pass\n"
    findings = detect_placeholders(code)
    types = [f['type'] for f in findings]
    assert 'placeholder_comment' in types


def test_todo_comment_detected():
    code = "function update() {\n  // TODO: implement this\n}\n"
    findings = detect_placeholders(code)
    assert any(f['type'] == 'js_todo_comment' for f in findings)


def test_in_real_implementation_comment_detected():
    code = "# in a real implementation this would do X\n"
    findings = detect_placeholders(code)
    assert any(f['type'] == 'in_real_impl_comment' for f in findings)


def test_clean_code_no_findings():
    code = "def draw(canvas):\n    canvas.fillRect(0, 0, 100, 100)\n"
    findings = detect_placeholders(code)
    assert findings == []


def test_test_file_suppressed():
    code = "# placeholder logic for test\n# TODO\n"
    findings = detect_placeholders(code, file_path="tests/test_animation.py")
    assert findings == []


def test_docs_file_suppressed():
    code = "# TODO: add more docs\n"
    findings = detect_placeholders(code, file_path="docs/README.md")
    assert findings == []


def test_scan_file_missing_returns_empty(tmp_path):
    findings = scan_file_for_placeholders(tmp_path / "nonexistent.py")
    assert findings == []


# ── Integration checker ───────────────────────────────────────────────────────

def test_html_references_all_generated_files_passes(tmp_path):
    html = tmp_path / "index.html"
    html.write_text(
        '<!doctype html><html><head>'
        '<link href="css/style.css" rel="stylesheet">'
        '</head><body>'
        '<script src="js/main.js"></script>'
        '<script src="js/renderer.js"></script>'
        '</body></html>',
        encoding='utf-8',
    )
    result = _CHECKER.check_html_entrypoint(html, generated_files=["css/style.css", "js/main.js", "js/renderer.js"])
    assert result['status'] == 'passed'
    assert result['disconnected'] == []


def test_html_missing_generated_file_warns(tmp_path):
    html = tmp_path / "index.html"
    html.write_text(
        '<!doctype html><html><body><script src="js/main.js"></script></body></html>',
        encoding='utf-8',
    )
    result = _CHECKER.check_html_entrypoint(html, generated_files=["js/main.js", "js/renderer.js"])
    assert result['status'] in ('warned', 'failed')
    assert 'js/renderer.js' in result['disconnected']


def test_missing_entrypoint_fails(tmp_path):
    result = _CHECKER.check_html_entrypoint(tmp_path / "missing.html", generated_files=["js/main.js"])
    assert result['status'] == 'failed'


def test_export_import_consistency_no_findings():
    files = {
        "js/main.js": "import { render } from './renderer.js';\nrender();",
        "js/renderer.js": "export function render() { return 1; }",
    }
    result = _CHECKER.check_import_consistency(files)
    assert result['status'] == 'passed'


# ── Modular slice policy ──────────────────────────────────────────────────────

def test_god_source_html_inline_script_warned():
    big_script = "\n".join([f"var x{i} = {i};" for i in range(100)])
    files = {"index.html": f"<!doctype html><html><body><script>{big_script}</script></body></html>"}
    findings = check_god_source(files)
    assert any(f['type'] == 'god_source_html_inline_script' for f in findings)


def test_small_html_inline_script_ok():
    files = {"index.html": "<!doctype html><html><body><script>var x=1;</script></body></html>"}
    findings = check_god_source(files)
    assert not any(f['type'] == 'god_source_html_inline_script' for f in findings)


def test_disconnected_module_detected():
    findings = check_disconnected_modules(
        entrypoint_references={"js/main.js", "css/style.css"},
        generated_files=["js/main.js", "js/renderer.js", "css/style.css"],
    )
    types = [f['path'] for f in findings]
    assert "js/renderer.js" in types


def test_no_disconnected_modules_when_all_referenced():
    findings = check_disconnected_modules(
        entrypoint_references={"js/main.js", "js/renderer.js"},
        generated_files=["js/main.js", "js/renderer.js"],
    )
    assert findings == []


def test_unused_generated_module_is_integration_warning(tmp_path):
    """Generated module not referenced in HTML → integration warning/failed."""
    html = tmp_path / "index.html"
    html.write_text(
        '<!doctype html><html><body><script src="js/main.js"></script></body></html>',
        encoding='utf-8',
    )
    result = _CHECKER.check_html_entrypoint(
        html,
        generated_files=["js/main.js", "js/unused_module.js"],
    )
    assert result['status'] in ('warned', 'failed')
    assert 'js/unused_module.js' in result['disconnected']
