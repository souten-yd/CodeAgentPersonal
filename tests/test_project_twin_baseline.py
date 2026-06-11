"""PDT-0 baseline regression fixtures.

Read-only pins for the current public surface that the Project Digital Twin work
packages depend on. These tests must keep passing across PDT-1..PDT-14 so later
packages cannot silently break the reused services. They assert *current* behavior
only; they do not import any project_twin package (which does not exist at PDT-0).
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


# --- Authoritative owners must remain importable -----------------------------

REUSED_MODULES = [
    "agent.atlas_repo_index_service",
    "agent.atlas_repo_index_storage",
    "agent.atlas_code_intel_service",
    "agent.atlas_code_intel_schema",
    "agent.context_builder",
    "agent.atlas_project_inspection_service",
    "agent.atlas_requirement_tracer",
    "agent.atlas_plan_pool_storage",
    "agent.run_storage",
    "agent.atlas_conversation_store",
    "agent.session",
    "agent.memory",
    "agent.atlas_test_impl_linker",
    "agent.atlas_playwright_smoke_verifier",
]


@pytest.mark.parametrize("module_name", REUSED_MODULES)
def test_reused_owner_modules_import(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None


# --- Deterministic Python symbol indexing (PDT-3 static source) ---------------

def test_code_intel_symbol_index_is_deterministic(tmp_path: Path) -> None:
    from agent.atlas_code_intel_schema import AtlasSymbolIndexRequest
    from agent.atlas_code_intel_service import AtlasCodeIntelService

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text(
        "import os\n"
        "from x import y\n"
        "class A:\n"
        "    def m(self):\n"
        "        return 1\n"
        "def f(x):\n"
        "    return x\n",
        encoding="utf-8",
    )

    svc = AtlasCodeIntelService()
    out1 = svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=str(repo), relative_path="app.py"))
    out2 = svc.build_symbol_index(AtlasSymbolIndexRequest(project_path=str(repo), relative_path="app.py"))

    names1 = [(s.name, s.kind, s.parent) for s in out1.symbols]
    names2 = [(s.name, s.kind, s.parent) for s in out2.symbols]
    assert names1 == names2, "symbol index must be deterministic"

    method = next(s for s in out1.symbols if s.name == "m")
    assert method.kind == "method" and method.parent == "A"
    assert any(s.name == "f" and s.kind == "function" and s.parent == "" for s in out1.symbols)
    assert any(s.kind == "import" for s in out1.symbols)


def test_code_intel_dependency_edges_are_scoped(tmp_path: Path) -> None:
    from agent.atlas_code_intel_schema import AtlasDependencyGraphRequest
    from agent.atlas_code_intel_service import AtlasCodeIntelService

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "foo.py").write_text("import os\n", encoding="utf-8")

    svc = AtlasCodeIntelService()
    dep = svc.build_dependency_graph(AtlasDependencyGraphRequest(project_path=str(repo), relative_path="src"))
    assert all(e.source.startswith("src/") for e in dep.edges)


# --- HybridMemoryStore current behavior (PDT-6 adapter target) ----------------

def test_hybrid_memory_short_term_recall() -> None:
    from agent.memory import HybridMemoryStore

    store = HybridMemoryStore(short_term_limit=8)
    store.store_memory(key="brief", value={"goal": "twin baseline"}, scope="short")
    results = store.retrieve_memory(query="twin baseline", scope="short", limit=5)
    assert isinstance(results, list)
    assert any("twin baseline" in str(r) for r in results)


def test_hybrid_memory_long_term_requires_saver() -> None:
    from agent.memory import HybridMemoryStore

    # Without a long-term saver, long-scope writes are a no-op (return None),
    # i.e. unverified inference does not silently persist. PDT-6 must preserve this.
    store = HybridMemoryStore(short_term_limit=8)
    assert store.store_memory(key="x", value={"a": 1}, scope="long") is None


# --- The twin contract package is introduced in PDT-1 ------------------------

def test_project_twin_contracts_introduced_in_pdt1() -> None:
    # PDT-0 pinned the absence of this package; PDT-1 introduces it as an explicit,
    # reviewed step. The contract package must import without any storage dependency.
    contracts = importlib.import_module("agent.project_twin.contracts")
    assert hasattr(contracts, "TwinNode")
    assert hasattr(contracts, "ProjectTwinPort")
