"""PIBIH-3 (slice 2): import-aware call resolution + ambiguous-call diagnostics.

Beyond name-based matching, calls are resolved to stable canonical refs when an import (from-import or
module alias) or a same-file definition makes the target unambiguous; the name-only edge is always kept
so name-matchable callers still link, and a bare-name project-looking call that cannot be resolved emits
an `ambiguous_call` uncertainty diagnostic (builtins are not flagged).
"""

from __future__ import annotations

from pathlib import Path

from agent.project_twin.contracts import StaticAnalysisRequest
from agent.project_twin.static_graph import StaticStructuralAnalyzer, nid


def _write(root: Path, rel: str, content: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _analyze(root: Path):
    return StaticStructuralAnalyzer().analyze(
        StaticAnalysisRequest(project_id="p1", project_path=str(root), full_rebuild=True)
    )


def _edge_triples(result):
    return {(e.edge_type, e.source_node_id, e.target_node_id) for e in result.delta.edges}


def _fixture(tmp_path: Path):
    _write(tmp_path, "pkg/util.py", "def helper():\n    return 1\n")
    _write(tmp_path, "pkg/main.py", "from pkg.util import helper\n\ndef caller():\n    return helper()\n")
    _write(tmp_path, "pkg/aliased.py", "import pkg.util as u\n\ndef caller2():\n    return u.helper()\n")
    _write(tmp_path, "pkg/localmod.py", "def b():\n    return 1\n\ndef a():\n    return b()\n")
    _write(tmp_path, "pkg/amb.py", "def caller3():\n    return mystery_func()\n")
    _write(tmp_path, "pkg/builtins_ok.py", "def caller4():\n    return len([1, 2])\n")
    return _analyze(tmp_path)


def test_from_import_resolves_to_canonical_ref(tmp_path: Path):
    result = _fixture(tmp_path)
    triples = _edge_triples(result)
    assert ("calls", nid("py://pkg/main.py#caller"), nid("py://pkg/util.py#helper")) in triples
    # the name-only edge is still present for name-matchable callers
    assert ("calls", nid("py://pkg/main.py#caller"), nid("pyname://helper")) in triples


def test_module_alias_resolves_to_canonical_ref(tmp_path: Path):
    result = _fixture(tmp_path)
    triples = _edge_triples(result)
    assert ("calls", nid("py://pkg/aliased.py#caller2"), nid("py://pkg/util.py#helper")) in triples


def test_local_call_resolves_within_file(tmp_path: Path):
    result = _fixture(tmp_path)
    triples = _edge_triples(result)
    assert ("calls", nid("py://pkg/localmod.py#a"), nid("py://pkg/localmod.py#b")) in triples


def test_resolved_call_edge_has_higher_confidence_than_name_edge(tmp_path: Path):
    result = _fixture(tmp_path)
    resolved = [
        e for e in result.delta.edges
        if e.edge_type == "calls"
        and e.source_node_id == nid("py://pkg/main.py#caller")
        and e.target_node_id == nid("py://pkg/util.py#helper")
    ]
    assert resolved and resolved[0].confidence > 0.7
    assert resolved[0].properties.get("resolution") == "from_import"


def test_ambiguous_unresolved_call_emits_diagnostic(tmp_path: Path):
    result = _fixture(tmp_path)
    callees = {d.get("callee") for d in result.diagnostics if d.get("code") == "ambiguous_call"}
    assert "mystery_func" in callees


def test_builtins_are_not_flagged_ambiguous(tmp_path: Path):
    result = _fixture(tmp_path)
    callees = {d.get("callee") for d in result.diagnostics if d.get("code") == "ambiguous_call"}
    assert "len" not in callees


def test_self_method_call_resolves_to_concrete_method(tmp_path: Path):
    # R3: self.m() inside a class resolves to the concrete method ref on the same class.
    _write(
        tmp_path,
        "pkg/models.py",
        "class Repo:\n"
        "    def save(self, item):\n"
        "        self._validate(item)\n"
        "        return item\n\n"
        "    def _validate(self, item):\n"
        "        return bool(item)\n",
    )
    result = _analyze(tmp_path)
    triples = _edge_triples(result)
    assert ("calls", nid("py://pkg/models.py#Repo.save"), nid("py://pkg/models.py#Repo._validate")) in triples
    resolved = [
        e for e in result.delta.edges
        if e.edge_type == "calls"
        and e.source_node_id == nid("py://pkg/models.py#Repo.save")
        and e.target_node_id == nid("py://pkg/models.py#Repo._validate")
    ]
    assert resolved and resolved[0].properties.get("resolution") == "self_method"
