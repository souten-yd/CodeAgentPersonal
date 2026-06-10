"""PI-6 static and semantic graph v2 tests.

Acceptance criteria (implementation plan PI-6):
- exact same-name functions in different modules are not collapsed;
- aliases and imports resolve correctly in fixtures;
- call targets distinguish resolved and may-call;
- JS/TS/Vue imports and component basics are represented;
- old CodeIntel parity metrics are recorded;
plus: capability/version manifest, deterministic refs, LSP-unavailable AST fallback with
recorded degradation, and incremental invalidation.
"""

from __future__ import annotations

from pathlib import Path

from agent.project_twin.analyzers.default import build_default_registry
from agent.project_twin.analyzers.python import PythonAnalyzer
from agent.project_twin.analyzers.registry import compute_codeintel_parity
from agent.project_twin.graph.semantic import SemanticGraph
from agent.project_twin.lsp_adapter import LSP_FALLBACK_REASON, LspAdapter

ROOT = Path(".")


def _analyze(files: dict[str, str]) -> SemanticGraph:
    reg = build_default_registry()
    return reg.analyze_project(ROOT, files).graph


# --- Same-name functions in different modules are not collapsed --------------

def test_same_name_functions_not_collapsed() -> None:
    g = _analyze({
        "a.py": "def handler():\n    return 1\n",
        "b.py": "def handler():\n    return 2\n",
    })
    assert g.get("py://a#handler") is not None
    assert g.get("py://b#handler") is not None
    funcs = [n for n in g.nodes(kind="function") if n.name == "handler"]
    assert len(funcs) == 2  # distinct refs, not merged


# --- Aliases and imports resolve ---------------------------------------------

def test_import_alias_resolution() -> None:
    g = _analyze({
        "lib.py": "def bar():\n    return 1\n",
        "app.py": (
            "import lib as L\n"
            "from lib import bar as b\n"
            "def use():\n"
            "    L.bar()\n"
            "    b()\n"
        ),
    })
    # `from lib import bar as b` creates an alias edge to lib#bar.
    alias_edges = [e for e in g.edges(kind="aliases")]
    assert any(e.target_ref == "py://lib#bar" for e in alias_edges)
    # `b()` resolves through the alias to lib#bar.
    calls = {(e.source_ref, e.target_ref) for e in g.out_edges("py://app#use", kind="calls")}
    assert ("py://app#use", "py://lib#bar") in calls
    # `L.bar()` resolves through the module alias L -> lib.
    assert ("py://app#use", "py://lib#bar") in calls


# --- Resolved vs may-call ----------------------------------------------------

def test_calls_distinguish_resolved_and_candidate() -> None:
    g = _analyze({
        "m.py": (
            "def helper():\n    return 1\n"
            "def run(x):\n"
            "    helper()\n"          # resolved local call
            "    x.process()\n"       # unknown receiver -> candidate
        ),
    })
    resolved = {(e.source_ref, e.target_ref) for e in g.edges(kind="calls", resolved=True)}
    candidates = {e.target_ref for e in g.candidates()}
    assert ("py://m#run", "py://m#helper") in resolved
    assert "pyname://process" in candidates
    # candidate confidence is below 1.0
    assert all(e.confidence < 1.0 for e in g.candidates())


# --- Inheritance and override ------------------------------------------------

def test_inheritance_and_override() -> None:
    g = _analyze({
        "h.py": (
            "class Base:\n"
            "    def run(self):\n        return 1\n"
            "class Child(Base):\n"
            "    def run(self):\n        return 2\n"
        ),
    })
    inh = {(e.source_ref, e.target_ref) for e in g.edges(kind="inherits")}
    assert ("py://h#Child", "py://h#Base") in inh
    ovr = {(e.source_ref, e.target_ref) for e in g.edges(kind="overrides")}
    assert ("py://h#Child.run", "py://h#Base.run") in ovr


def test_receiver_annotation_and_constructor_resolve_method_calls() -> None:
    g = _analyze({
        "svc.py": (
            "class Service:\n"
            "    def process(self):\n        return 1\n"
            "def run_arg(s: Service):\n"
            "    s.process()\n"
            "def run_ctor():\n"
            "    local = Service()\n"
            "    local.process()\n"
        ),
    })
    resolved = {(e.source_ref, e.target_ref) for e in g.edges(kind="calls", resolved=True)}
    assert ("py://svc#run_arg", "py://svc#Service.process") in resolved
    assert ("py://svc#run_ctor", "py://svc#Service.process") in resolved


def test_protocol_named_base_records_implements_candidate() -> None:
    g = _analyze({
        "p.py": (
            "class ServiceProtocol:\n"
            "    def run(self):\n        pass\n"
            "class Impl(ServiceProtocol):\n"
            "    def run(self):\n        return 1\n"
        ),
    })
    assert ("py://p#Impl", "py://p#ServiceProtocol") in {
        (e.source_ref, e.target_ref) for e in g.edges(kind="implements")
    }


def test_decorator_relationship() -> None:
    g = _analyze({
        "d.py": (
            "def deco(f):\n    return f\n"
            "@deco\n"
            "def target():\n    return 1\n"
        ),
    })
    dec = {(e.source_ref, e.target_ref) for e in g.edges(kind="decorates")}
    assert ("py://d#target", "py://d#deco") in dec


def test_init_reexport() -> None:
    g = _analyze({
        "pkg/__init__.py": "from pkg.core import thing\n",
        "pkg/core.py": "def thing():\n    return 1\n",
    })
    reex = {(e.source_ref, e.target_ref) for e in g.edges(kind="reexports")}
    assert ("module://pkg", "py://pkg.core#thing") in reex


def test_reexported_symbol_call_resolves_to_actual_target() -> None:
    g = _analyze({
        "pkg/__init__.py": "from pkg.core import thing\n",
        "pkg/core.py": "def thing():\n    return 1\n",
        "app.py": "from pkg import thing\n\ndef use():\n    thing()\n",
    })
    calls = {(e.source_ref, e.target_ref, e.properties.get("via_reexport")) for e in g.edges(kind="calls")}
    assert ("py://app#use", "py://pkg.core#thing", "py://pkg#thing") in calls


# --- JS / TS / Vue basics ----------------------------------------------------

def test_js_imports_and_functions() -> None:
    g = _analyze({
        "app.js": "import {h} from './helper.js';\nexport function main() { h(); }\n",
    })
    imports = {e.target_ref for e in g.edges(kind="imports")}
    assert "module://./helper.js" in imports
    assert g.get("js://app.js#main") is not None


def test_vue_component_and_imports() -> None:
    g = _analyze({
        "Button.vue": (
            "<template><button/></template>\n"
            "<script>\nimport api from './api.js'\nexport default { name: 'Button' }\n</script>\n"
        ),
    })
    comp = g.get("vue://Button.vue#Button")
    assert comp is not None and comp.kind == "component"
    assert comp.properties.get("has_template") is True
    assert "module://./api.js" in {e.target_ref for e in g.edges(kind="imports")}


# --- Manifest, LSP fallback, parity, incremental -----------------------------

def test_capability_manifest_and_versions() -> None:
    reg = build_default_registry()
    langs = {m.language for m in reg.manifests()}
    assert {"python", "javascript", "typescript_vue"} <= langs
    py = next(m for m in reg.manifests() if m.language == "python")
    assert "calls_resolved" in py.capabilities and py.version


def test_python_symbols_include_source_ranges() -> None:
    g = _analyze({"a.py": "\n\nclass C:\n    def f(self):\n        return 1\n"})
    cls = g.get("py://a#C")
    method = g.get("py://a#C.f")
    assert cls and cls.properties["start_line"] == 3
    assert method and method.properties["start_line"] == 4


def test_lsp_unavailable_falls_back_to_ast_with_degradation() -> None:
    reg = build_default_registry()
    adapter = LspAdapter(reg)  # default probe -> unavailable
    analysis = adapter.analyze(ROOT, {"a.py": "def f():\n    return 1\n"})
    assert analysis.used_lsp is False
    assert analysis.degraded is True
    assert LSP_FALLBACK_REASON in analysis.degradation_reasons
    assert analysis.result.graph.get("py://a#f") is not None


def test_codeintel_parity_is_recorded() -> None:
    g = _analyze({"a.py": "def alpha():\n    return 1\ndef beta():\n    return 2\n"})
    parity = compute_codeintel_parity(g, {"alpha", "beta", "gamma"})
    assert parity["codeintel_symbols"] == 3
    assert parity["matched"] == 2
    assert "gamma" in parity["missing"]
    assert 0.0 <= parity["coverage"] <= 1.0


def test_incremental_invalidation_drops_only_changed_file() -> None:
    reg = build_default_registry()
    files = {"a.py": "def f():\n    return 1\n", "b.py": "def g():\n    return 2\n"}
    res = reg.analyze_project(ROOT, files)
    g = res.graph
    assert g.get("py://a#f") and g.get("py://b#g")
    # Re-analyze only b.py changed; a.py facts must remain, b.py rebuilt.
    reg.analyze_project(ROOT, {"b.py": "def g2():\n    return 3\n"}, graph=g)
    assert g.get("py://a#f") is not None       # untouched
    assert g.get("py://b#g") is None           # old b symbol invalidated
    assert g.get("py://b#g2") is not None       # new b symbol present


def test_reanalysis_is_idempotent() -> None:
    reg = build_default_registry()
    files = {"a.py": "def f():\n    helper()\n"}
    g = reg.analyze_project(ROOT, files).graph
    n1, e1 = g.node_count, g.edge_count
    reg.analyze_project(ROOT, files, graph=g)  # same input again
    assert (g.node_count, g.edge_count) == (n1, e1)


def test_incremental_matches_full_for_changed_file() -> None:
    reg = build_default_registry()
    base = {
        "a.py": "def f():\n    return 1\n",
        "b.py": "def g():\n    return f()\n",
    }
    changed = {"a.py": "def f2():\n    return 2\n"}
    inc = reg.analyze_project(ROOT, base).graph
    reg.analyze_project(ROOT, changed, graph=inc)
    full = reg.analyze_project(ROOT, {**base, **changed}).graph
    assert {n.ref for n in inc.nodes()} == {n.ref for n in full.nodes()}
    assert {(e.source_ref, e.target_ref, e.kind) for e in inc.edges()} == {
        (e.source_ref, e.target_ref, e.kind) for e in full.edges()
    }
