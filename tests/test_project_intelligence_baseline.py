"""PI-0 production baseline regression fixtures (Atlas Project Intelligence).

Read-only pins for the current public surface that the Project Intelligence program
(PI-1..PI-25) reorganizes behind the four module facades. These tests assert *current*
behavior only and must keep passing as later packages introduce the modules, so the
reorganization cannot silently break the reused owners or skip the explicit module
introduction step.

PI-0 changes no production behavior. This module and the three PI-0 maps
(existing_capability_map / consumer_map / migration_matrix) are the only new artifacts.

Scope of pins:
- authoritative owners in the PI-0 inventory scope remain importable;
- deterministic Python symbol/dependency output (Code Intel) is unchanged;
- known duplication (Code Explorer heuristic extractors) still exists;
- Project Digital Twin Core v1 contracts (atlas.project_twin.v1) are present;
- the four Project Intelligence module packages are ABSENT (introduced at PI-1);
- the foundation is recorded as PDT Core v1 complete, and the active program is PI-0.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"


# --- Authoritative owners (PI-0 inventory scope) must remain importable ------

REUSED_OWNER_MODULES = [
    # repository enumeration / symbol & dependency extraction
    "agent.atlas_repo_index_service",
    "agent.atlas_repo_index_storage",
    "agent.atlas_code_intel_service",
    "agent.atlas_code_intel_schema",
    "agent.atlas_code_explorer",
    # project / git inspection
    "agent.atlas_project_inspection_service",
    "agent.atlas_git_inspection_service",
    # related-test / impl link
    "agent.atlas_test_impl_linker",
    # context construction + planner packaging
    "agent.context_builder",
    "agent.atlas_repo_context_service",
    "agent.atlas_context_local_collectors",
    # context refresh (v1 + v2)
    "agent.atlas_context_refresh_service",
    "agent.atlas_context_refresh_v2_service",
    # impact
    "agent.atlas_plan_item_impact_map_service",
    # verification support (recommendation/handoff) and the canonical gate
    "agent.atlas_verification_recommendation_service",
    "agent.atlas_verification_recommendation_handoff_service",
    "agent.atlas_verification_gate_service",
    # durable memory + twin core v1 package
    "agent.memory",
    "agent.project_twin",
]


@pytest.mark.parametrize("module_name", REUSED_OWNER_MODULES)
def test_reused_owner_modules_import(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None


# --- Authoritative owner symbols are present on their modules ----------------

OWNER_SYMBOLS = [
    ("agent.atlas_repo_index_service", "AtlasRepoIndexService"),
    ("agent.atlas_code_intel_service", "AtlasCodeIntelService"),
    ("agent.atlas_project_inspection_service", "AtlasProjectInspectionService"),
    ("agent.atlas_git_inspection_service", "AtlasGitInspectionService"),
    ("agent.atlas_plan_item_impact_map_service", "AtlasPlanItemImpactMapService"),
    ("agent.atlas_repo_context_service", "AtlasRepoContextService"),
    ("agent.atlas_context_refresh_service", "AtlasContextRefreshService"),
    ("agent.atlas_context_refresh_v2_service", "AtlasContextRefreshV2Service"),
    ("agent.atlas_verification_recommendation_service", "AtlasVerificationRecommendationService"),
    ("agent.atlas_verification_recommendation_handoff_service", "AtlasVerificationRecommendationHandoffService"),
    ("agent.atlas_verification_gate_service", "AtlasVerificationGateService"),
]


@pytest.mark.parametrize("module_name,symbol", OWNER_SYMBOLS)
def test_owner_symbol_present(module_name: str, symbol: str) -> None:
    mod = importlib.import_module(module_name)
    assert hasattr(mod, symbol), f"{module_name}.{symbol} missing (migration matrix owner)"


# --- Deterministic Python symbol indexing (Digital Twin semantic source) -----

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


# --- Known duplication is recorded (Code Explorer heuristic extractors) -------

def test_code_explorer_duplicate_extractors_exist() -> None:
    # Documented duplication (capability map §6): a second symbol/related-test path
    # exists in the code explorer. PI must reach parity before retiring either path.
    explorer = importlib.import_module("agent.atlas_code_explorer")
    assert callable(getattr(explorer, "extract_symbols", None))
    assert callable(getattr(explorer, "find_related_tests", None))


# --- Durable Memory current behavior (Memory KEEP + ADAPT) -------------------

def test_hybrid_memory_long_term_requires_saver() -> None:
    from agent.memory import HybridMemoryStore

    # Without a long-term saver, long-scope writes are a no-op (return None): unverified
    # inference does not silently persist. The Memory adapter must preserve this invariant.
    store = HybridMemoryStore(short_term_limit=8)
    assert store.store_memory(key="x", value={"a": 1}, scope="long") is None


# --- Project Digital Twin Core v1 contracts are present (foundation) ----------

def test_project_twin_core_v1_contracts_present() -> None:
    import agent.project_twin as twin

    assert twin.CONTRACT_VERSION == "atlas.project_twin.v1"
    # Coarse contract surface the DigitalTwinModule facade (PI-1) will wrap.
    for name in ("TwinNode", "TwinEdge", "ProjectTwinPort", "StaticAnalysisPort", "TwinContextPort"):
        assert hasattr(twin, name), f"twin Core v1 contract {name} missing"


# --- The four Project Intelligence module packages are introduced at PI-1 -----

PI_MODULE_TARGETS = [
    "agent.project_intelligence",
    "agent.architecture_blueprint",
    "agent.project_convergence",
    "agent.project_twin.facade",
]


@pytest.mark.parametrize("module_name", PI_MODULE_TARGETS)
def test_pi_module_packages_present_after_pi1(module_name: str) -> None:
    # PI-0 pinned the ABSENCE of these packages so PI-1 introduction was an explicit,
    # reviewed step. PI-1 introduced the four module facades; the pin now asserts their
    # presence so they cannot silently disappear in later packages.
    assert importlib.import_module(module_name) is not None


# --- Program status is recorded truthfully (Core v1 complete, program active) -

def test_pdt_core_v1_recorded_complete() -> None:
    status = (DOCS / "atlas_project_digital_twin_current_status.md").read_text(encoding="utf-8")
    assert "COMPLETE" in status, "PDT Core v1 status must record completion"


def test_project_intelligence_program_is_active_at_pi0() -> None:
    status = (DOCS / "atlas_project_intelligence_current_status.md").read_text(encoding="utf-8")
    # The active program must not be inferred complete from the old PDT status.
    assert "ACTIVE" in status
    assert "PI-0" in status


def test_pi0_required_maps_exist() -> None:
    for name in (
        "atlas_project_intelligence_existing_capability_map.md",
        "atlas_project_intelligence_consumer_map.md",
        "atlas_project_intelligence_migration_matrix.md",
    ):
        assert (DOCS / name).is_file(), f"PI-0 output {name} missing"
