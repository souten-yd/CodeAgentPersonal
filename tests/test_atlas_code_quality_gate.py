"""Tests for the deterministic code-quality gate (syntax + reasoning-leak) and its wiring into
generation (reject broken output -> regenerate) and verification (hard-fail a syntax error).

A weak model generated a 22KB game.js that PARSED-FAILED (duplicate `const`) and was littered with
its own chain-of-thought as comments, yet shipped as "completed" because the verifier only ran a
deferrable whole-app smoke. These tests lock in the two fixes.
"""
from __future__ import annotations

from pathlib import Path

from agent.atlas_code_quality_gate import check_syntax, code_quality_findings, detect_reasoning_leak


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
