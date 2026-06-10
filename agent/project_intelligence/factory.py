"""Project Intelligence composition root (PI-3).

The single place that wires the four modules together through their public facades and a
rollout configuration. Dependencies are injected, so tests and future production wiring can
substitute real module implementations (PI-4+) without changing consumers.

With the rollout off (the default), ``build_project_intelligence`` returns a coordinator
that is behaviourally equivalent to the legacy baseline and constructs no persistence.
"""

from __future__ import annotations

from agent.architecture_blueprint.contracts import ArchitectureBlueprintModule
from agent.architecture_blueprint.facade import DisabledArchitectureBlueprintModule
from agent.project_convergence.contracts import ConvergenceModule
from agent.project_convergence.facade import DisabledConvergenceModule
from agent.project_intelligence.coordinator import ProjectIntelligenceCoordinator
from agent.project_intelligence.rollout import RolloutConfig
from agent.project_intelligence.telemetry import TelemetrySink
from agent.project_twin.facade import DigitalTwinModule, DisabledDigitalTwinModule


def build_project_intelligence(
    *,
    rollout: RolloutConfig | None = None,
    env: dict | None = None,
    digital_twin: DigitalTwinModule | None = None,
    blueprint: ArchitectureBlueprintModule | None = None,
    convergence: ConvergenceModule | None = None,
    telemetry: TelemetrySink | None = None,
) -> ProjectIntelligenceCoordinator:
    """Compose the Project Intelligence coordinator.

    Resolution order for rollout: explicit ``rollout`` arg wins; otherwise parse from
    ``env`` (or the process environment) including legacy Project Twin variables.
    """
    config = rollout if rollout is not None else RolloutConfig.from_env(env)
    return ProjectIntelligenceCoordinator(
        digital_twin=digital_twin or DisabledDigitalTwinModule(),
        blueprint=blueprint or DisabledArchitectureBlueprintModule(),
        convergence=convergence or DisabledConvergenceModule(),
        rollout=config,
        telemetry=telemetry or TelemetrySink(),
    )
