"""PI-1 architecture-boundary tests.

Enforces the mandatory dependency boundaries (architecture §3, ADR-PI-014/015):

- portable module cores must not import FastAPI, UI/web/js, app.api, app.server,
  or Atlas PlanPool / workflow storage;
- the Digital Twin facade and the Blueprint facade must not import each other;
- no portable core imports a module-private SQLite store at module load;
- the four portable modules are instantiable without Atlas (no FastAPI/PlanPool import
  is triggered by importing or constructing the disabled facades).

These tests scan the actual source of the portable module files (AST import analysis),
so a forbidden import cannot slip in unnoticed in later packages.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT = REPO_ROOT / "agent"

# Portable module core files (NOT the future adapters/ which may import Atlas).
PORTABLE_CORE_FILES = [
    AGENT / "project_intelligence" / "contracts.py",
    AGENT / "project_intelligence" / "facade.py",
    AGENT / "project_intelligence" / "__init__.py",
    AGENT / "project_intelligence" / "coordinator.py",
    AGENT / "project_intelligence" / "factory.py",
    AGENT / "project_intelligence" / "rollout.py",
    AGENT / "project_intelligence" / "telemetry.py",
    AGENT / "project_twin" / "facade.py",
    AGENT / "architecture_blueprint" / "contracts.py",
    AGENT / "architecture_blueprint" / "facade.py",
    AGENT / "architecture_blueprint" / "__init__.py",
    AGENT / "project_convergence" / "contracts.py",
    AGENT / "project_convergence" / "facade.py",
    AGENT / "project_convergence" / "__init__.py",
]

# Forbidden import prefixes for any portable core (architecture §3).
FORBIDDEN_PREFIXES = (
    "fastapi",
    "starlette",
    "app.api",
    "app.server",
    "app.nexus.router",
    "agent.atlas_plan_pool_storage",
    "agent.plan_storage",
    "agent.run_storage",
    "agent.session",
    "agent.loop",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module)
    return names


@pytest.mark.parametrize("path", PORTABLE_CORE_FILES, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_portable_core_has_no_forbidden_imports(path: Path) -> None:
    imports = _imported_modules(path)
    bad = {
        name
        for name in imports
        for prefix in FORBIDDEN_PREFIXES
        if name == prefix or name.startswith(prefix + ".")
    }
    assert not bad, f"{path.relative_to(REPO_ROOT)} imports forbidden modules: {sorted(bad)}"


def test_twin_facade_and_blueprint_do_not_depend_on_each_other() -> None:
    # architecture §3: Digital Twin and Blueprint do not depend on each other.
    twin_imports = _imported_modules(AGENT / "project_twin" / "facade.py")
    bp_imports = (
        _imported_modules(AGENT / "architecture_blueprint" / "facade.py")
        | _imported_modules(AGENT / "architecture_blueprint" / "contracts.py")
    )
    assert not any(n.startswith("agent.architecture_blueprint") for n in twin_imports)
    assert not any(n.startswith("agent.project_twin") for n in bp_imports)


def test_no_portable_core_imports_private_sqlite_store() -> None:
    # ADR-PI-015: no consumer depends on SQLite tables. The portable facades must not
    # import the private Core v1 store module at load time.
    for path in PORTABLE_CORE_FILES:
        imports = _imported_modules(path)
        assert "agent.project_twin.store" not in imports, f"{path} imports private twin store"
        assert "sqlite3" not in imports, f"{path} imports sqlite3 directly"


def test_modules_instantiable_without_atlas_workflow_loaded() -> None:
    # ADR-PI-014: the portable modules are instantiable without Atlas. Constructing the
    # disabled facades must not pull FastAPI or PlanPool storage into sys.modules.
    for mod in ("fastapi", "agent.atlas_plan_pool_storage", "agent.loop"):
        sys.modules.pop(mod, None)

    from agent.architecture_blueprint.facade import DisabledArchitectureBlueprintModule
    from agent.project_convergence.facade import DisabledConvergenceModule
    from agent.project_intelligence.facade import DisabledProjectIntelligenceModule
    from agent.project_twin.facade import DisabledDigitalTwinModule

    _ = (
        DisabledDigitalTwinModule(),
        DisabledArchitectureBlueprintModule(),
        DisabledConvergenceModule(),
        DisabledProjectIntelligenceModule(),
    )

    assert "fastapi" not in sys.modules
    assert "agent.atlas_plan_pool_storage" not in sys.modules
    assert "agent.loop" not in sys.modules


def test_dependency_direction_pi_to_modules() -> None:
    # architecture §3: Project Intelligence facade -> the three module facades.
    pi_imports = _imported_modules(AGENT / "project_intelligence" / "facade.py")
    assert "agent.project_twin.facade" in pi_imports
    assert "agent.architecture_blueprint.facade" in pi_imports
    assert "agent.project_convergence.facade" in pi_imports
