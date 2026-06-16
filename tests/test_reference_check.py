"""Deterministic invented-project-reference detection."""
from __future__ import annotations

from agent.twin_control_plane.reference_check import (
    build_symbol_index, check_project_references, render_reference_findings,
)

SYMS = [
    "py://agent/model_forge/decomposition_policy.py#derive_decomposition_policy",
    "py://agent/model_forge/decomposition_policy.py#DecompositionPolicy",
    "py://agent/twin_control_plane/twinproof.py#build_twinproof",
]


def test_index_builds_modules_and_symbols():
    mods, syms = build_symbol_index(SYMS)
    assert "agent.model_forge.decomposition_policy" in mods
    assert "agent.model_forge.decomposition_policy:derive_decomposition_policy" in syms


def test_valid_project_import_is_not_flagged():
    mods, syms = build_symbol_index(SYMS)
    code = "from agent.model_forge.decomposition_policy import derive_decomposition_policy\nx = 1\n"
    assert check_project_references(code, modules=mods, module_symbols=syms) == []


def test_invented_symbol_is_flagged():
    mods, syms = build_symbol_index(SYMS)
    code = "from agent.model_forge.decomposition_policy import compute_magic_policy\n"
    findings = check_project_references(code, modules=mods, module_symbols=syms)
    assert len(findings) == 1
    assert findings[0]["name"] == "compute_magic_policy"
    assert "Invented reference" in render_reference_findings(findings)


def test_external_imports_are_ignored():
    mods, syms = build_symbol_index(SYMS)
    code = "import os\nfrom collections import Counter\nimport numpy as np\n"
    assert check_project_references(code, modules=mods, module_symbols=syms) == []


def test_relative_imports_are_not_checked():
    mods, syms = build_symbol_index(SYMS)
    code = "from . import sibling\nfrom .helpers import thing\n"
    assert check_project_references(code, modules=mods, module_symbols=syms) == []


def test_syntax_error_returns_no_findings():
    mods, syms = build_symbol_index(SYMS)
    assert check_project_references("def (:\n", modules=mods, module_symbols=syms) == []
