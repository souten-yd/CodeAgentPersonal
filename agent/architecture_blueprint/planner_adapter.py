"""Blueprint planner adapter for PIR-8.

This adapter turns requirement plus actual-context request fields into a structured
``BlueprintSpec`` for the deterministic generator. It does not inspect Twin internals or
workspace state directly; callers must pass the public context they want considered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.architecture_blueprint.contracts import BlueprintCreateRequest, BlueprintDecisionRequest
from agent.architecture_blueprint.generator import BlueprintSpec, FileSpec, decide_scope

_GREENFIELD_MODES = {"empty", "greenfield_partial"}


@dataclass(frozen=True)
class BlueprintPlanningResult:
    spec: BlueprintSpec
    scope: str
    unresolved_decisions: list[BlueprintDecisionRequest] = field(default_factory=list)


class BlueprintPlannerAdapter:
    """Build deterministic Blueprint specs from public requirement/actual context."""

    def plan(self, request: BlueprintCreateRequest) -> BlueprintPlanningResult:
        paths = list(dict.fromkeys([*request.target_files, *request.changed_files]))
        if not paths:
            paths = ["README.md"] if request.project_mode in _GREENFIELD_MODES else ["project_change.md"]

        requirement_ids = list(request.source_requirement_ids)
        files = [
            FileSpec(
                path=path,
                requirement_ids=requirement_ids,
                interfaces=list(request.interfaces.get(path, [])),
                acceptance=[f"{path} satisfies requested target behavior"],
                verification_contract_ids=[f"vc:file:{path}"],
                preserve_behaviors=list(request.preserve_behaviors),
                contracts={
                    "requirement_text": [request.requirement_text] if request.requirement_text else [],
                },
            )
            for path in paths
        ]

        scope = request.scope
        unresolved = list(request.critical_decisions)
        if request.project_mode in _GREENFIELD_MODES:
            scope = "full_project"
        elif request.scope == "full_project" and not request.allow_full_redesign:
            scope = "change_set"
            unresolved.append(
                BlueprintDecisionRequest(
                    decision_id="critical:full_redesign_scope",
                    topic="existing project full redesign",
                    reason="full-project redesign of an existing project requires explicit approval",
                )
            )
        elif request.scope == "change_set":
            scope = decide_scope(
                request.project_mode,
                len(paths),
                allow_full_redesign=request.allow_full_redesign,
            )

        commands = dict(request.commands)
        full_project = scope == "full_project"
        spec = BlueprintSpec(
            requirements=requirement_ids,
            files=files,
            api_routes=list(request.api_routes),
            schemas=list(request.schemas),
            config_keys=list(request.config_keys),
            dependencies=list(request.dependencies),
            runtime_scenarios=list(request.runtime_scenarios),
            nfrs=list(request.nfrs),
            preserve_behaviors=list(request.preserve_behaviors),
            entrypoint=commands.get("entrypoint") or (paths[0] if full_project else None),
            build_command=commands.get("build") or commands.get("build_command") or ("python -m compileall ." if full_project else None),
            start_command=commands.get("start") or commands.get("start_command") or ("python main.py" if full_project else None),
            test_command=commands.get("test") or commands.get("test_command") or ("python -m pytest -q" if full_project else None),
        )
        return BlueprintPlanningResult(spec=spec, scope=scope, unresolved_decisions=unresolved)
