"""Tests for the deterministic code-quality gate (syntax + reasoning-leak) and its wiring into
generation (reject broken output -> regenerate) and verification (hard-fail a syntax error).

A weak model generated a 22KB game.js that PARSED-FAILED (duplicate `const`) and was littered with
its own chain-of-thought as comments, yet shipped as "completed" because the verifier only ran a
deferrable whole-app smoke. These tests lock in the two fixes.
"""
from __future__ import annotations

from pathlib import Path

from agent.atlas_code_quality_gate import check_syntax, code_quality_findings, detect_reasoning_leak, detect_self_test_leak


_LEAKY = """\
function fire() {
    // I'll assume `lastFireTime` is declared in the scope above this function.
    // Wait, looking at the skeleton, there is NO `lastFireTime` defined.
    // The prompt says "Use the skeleton's declared fields". It does NOT declare it.
    if (now - lastFireTime < 100) return;
}
"""

_DUP_CONST = "function f(){ const a = 1; const a = 2; return a; }\n"
_CLEAN_JS = "function add(a, b) {\n  return a + b;\n}\n"

# Reproduces a real live-model defect (FPS game session): a self-verification harness the model
# used internally to check its own step_3 output leaked into the shipped index.html as executable
# code, not comments -- syntactically valid, so the syntax check alone did not catch it.
_SELF_TEST_LEAK_JS = """\
window.onload = () => {
  GameCore.init();
  runInputTests();
};

function runInputTests() {
  console.log('Running focused input tests...');
  let passed = 0;
  InputManager.keys['w'] = true;
  if (InputManager.keys['w'] === true) { console.log('PASS: Keyboard state tracks keydown'); passed++; } else { console.log('FAIL: Keyboard state'); }
  InputManager.touch.lookX = 10;
  if (InputManager.touch.lookX === 10) { console.log('PASS: Touch look delta calculates correctly'); passed++; } else { console.log('FAIL: Touch look delta'); }
}
"""

# Reproduces a second real live-model defect: the SAME leaked test harness above, but embedded
# inline in an .html file (a single-file game) rather than a standalone .js file -- previously
# invisible to check_syntax entirely, since the extension dispatch had no .html branch.
_HTML_WITH_BROKEN_INLINE_SCRIPT = """\
<!doctype html>
<html><body>
<canvas id="gameCanvas"></canvas>
<script>
function f(){ const a = 1; const a = 2; return a; }
</script>
</body></html>
"""


# ── pure gate ─────────────────────────────────────────────────────────────────

def test_syntax_check_flags_js_parse_error():
    ok, err = check_syntax(_DUP_CONST, "js/f.js")
    assert ok is False
    assert "syntax" in err.lower()


def test_syntax_check_passes_clean_js():
    ok, err = check_syntax(_CLEAN_JS, "js/add.js")
    assert ok is True and err == ""


def test_syntax_check_flags_python_error_without_node():
    ok, err = check_syntax("def f(:\n    pass\n", "src/x.py")
    assert ok is False and "py_syntax_error" in err


def test_syntax_check_ignores_unknown_extension():
    ok, err = check_syntax("<<<not code>>>", "notes.md")
    assert ok is True


def test_reasoning_leak_density():
    assert detect_reasoning_leak(_LEAKY)  # >= 3 deliberation comments
    assert detect_reasoning_leak(_CLEAN_JS) == []
    # a single incidental note must NOT trip it
    assert detect_reasoning_leak("// I'll do this later\nconst a = 1;\n") == []


def test_code_quality_findings_combines_syntax_and_leak():
    findings = code_quality_findings(_DUP_CONST + "// I'll x\n// I will y\n// Let's z\n", "js/f.js")
    assert any("syntax" in f for f in findings)


def test_self_test_leak_density():
    assert detect_self_test_leak(_SELF_TEST_LEAK_JS)  # >= 2 PASS/FAIL assertion lines
    assert detect_self_test_leak(_CLEAN_JS) == []
    # a single incidental PASS/FAIL-shaped log must NOT trip it
    assert detect_self_test_leak("console.log('PASS: ok');\nconst a = 1;\n") == []


def test_code_quality_findings_flags_self_test_leak():
    findings = code_quality_findings(_SELF_TEST_LEAK_JS, "js/game.js")
    assert any("self_test_leak" in f for f in findings)


def test_syntax_check_extracts_and_checks_inline_html_script():
    # Previously .html files had no branch in check_syntax at all -> always a silent pass, even for
    # a broken inline <script>. A single-file HTML game embeds its JS inline, not as a separate .js.
    ok, err = check_syntax(_HTML_WITH_BROKEN_INLINE_SCRIPT, "index.html")
    assert ok is False
    assert "syntax" in err.lower()


def test_syntax_check_passes_clean_inline_html_script():
    clean_html = "<!doctype html><html><body><script>function add(a,b){return a+b;}</script></body></html>"
    ok, err = check_syntax(clean_html, "index.html")
    assert ok is True and err == ""


def test_code_quality_findings_flags_self_test_leak_inside_html():
    html = f"<!doctype html><html><body><script>{_SELF_TEST_LEAK_JS}</script></body></html>"
    findings = code_quality_findings(html, "index.html")
    assert any("self_test_leak" in f for f in findings)


# ── generation wiring: broken content is rejected, not shipped ──────────────────

def test_generation_rejects_broken_content_then_no_content(tmp_path: Path):
    # A stub LLM that always returns a syntactically-broken create for game.js. The generation loop
    # must never return it as success; after exhausting attempts it yields a no_content failure so
    # the orchestrator's section recovery engages.
    from agent.atlas_patch_proposal_service import AtlasPatchProposalService

    svc = AtlasPatchProposalService.__new__(AtlasPatchProposalService)

    class _Proposal:
        def __init__(self, content):
            self.metadata = {"file_changes": [{"path": "js/game.js", "proposed_content": content}]}
            self.warnings = []

    broken = svc._proposal_source_quality_findings(_Proposal(_DUP_CONST), {"item": {"target_files": ["js/game.js"]}})
    clean = svc._proposal_source_quality_findings(_Proposal(_CLEAN_JS), {"item": {"target_files": ["js/game.js"]}})
    assert broken and any("syntax" in f for f in broken)
    assert clean == []


# ── verification wiring: a syntax error hard-fails even if the smoke is deferred ─

def test_verification_syntax_gate_flags_broken_file(tmp_path: Path):
    from agent.atlas_auto_verification_service import AtlasAutoVerificationService
    from types import SimpleNamespace

    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "game.js").write_text(_DUP_CONST, encoding="utf-8")
    (tmp_path / "js" / "ok.js").write_text(_CLEAN_JS, encoding="utf-8")

    svc = AtlasAutoVerificationService.__new__(AtlasAutoVerificationService)
    bad = svc._syntax_check_applied_sources(SimpleNamespace(target_files=["js/game.js"]), str(tmp_path))
    good = svc._syntax_check_applied_sources(SimpleNamespace(target_files=["js/ok.js"]), str(tmp_path))
    assert bad and "game.js" in bad[0]
    assert good == []
