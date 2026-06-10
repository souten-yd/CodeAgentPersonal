"""PIR-1 facade conformance for disabled and concrete implementations."""

from __future__ import annotations

from agent.architecture_blueprint.contracts import ArchitectureBlueprintModule
from agent.architecture_blueprint.facade import DisabledArchitectureBlueprintModule
from agent.architecture_blueprint.module import ArchitectureBlueprintModuleImpl
from agent.architecture_blueprint.store import BlueprintStore
from agent.project_convergence.contracts import ConvergenceModule
from agent.project_convergence.facade import DisabledConvergenceModule
from agent.project_convergence.module import ConvergenceModuleImpl
from agent.project_convergence.store import ConvergenceStore
from agent.project_intelligence.facade import DisabledProjectIntelligenceModule
from agent.project_intelligence.contracts import ProjectIntelligenceModule
from agent.project_twin.facade import DigitalTwinModule, DisabledDigitalTwinModule
from agent.project_twin.module import DigitalTwinModuleImpl


def test_disabled_and_concrete_facades_conform_to_protocols(tmp_path) -> None:
    assert isinstance(DisabledProjectIntelligenceModule(), ProjectIntelligenceModule)
    assert isinstance(DisabledArchitectureBlueprintModule(), ArchitectureBlueprintModule)
    assert isinstance(DisabledDigitalTwinModule(), DigitalTwinModule)
    assert isinstance(DisabledConvergenceModule(), ConvergenceModule)

    assert isinstance(ArchitectureBlueprintModuleImpl(BlueprintStore(tmp_path / "bp.db")), ArchitectureBlueprintModule)
    assert isinstance(DigitalTwinModuleImpl(tmp_path / "twin.db"), DigitalTwinModule)
    assert isinstance(ConvergenceModuleImpl(store=ConvergenceStore(tmp_path / "conv.db")), ConvergenceModule)


def test_concrete_facades_do_not_expose_fastapi_or_planpool_dependencies() -> None:
    modules = [
        "agent.project_twin.module",
        "agent.architecture_blueprint.module",
        "agent.project_convergence.module",
    ]
    for module in modules:
        imported = __import__(module, fromlist=["dummy"])
        names = set(vars(imported))
        assert "FastAPI" not in names
        assert "PlanPool" not in names

