"""Blueprint generation (PI-11).

Deterministic assembly of a Blueprint revision from a structured spec. Per ADR-PI-008,
deterministic code owns identity, dependency order, and requirement mapping; an LLM may
produce the spec content (file list, interfaces, commands) but within these contracts. The
generated Blueprint uses planned ``bp://`` refs only; Actual refs appear solely as
``expected_actual_refs`` materialization targets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent.architecture_blueprint.contracts import (
    BlueprintElement,
    BlueprintRelation,
    BlueprintRevision,
)
from agent.architecture_blueprint.lifecycle import planner_decision

_GREENFIELD_MODES = {"empty", "greenfield_partial"}
_CHANGE_SET_LIMIT = 5  # an existing change touching <= N files is a Change Blueprint


@dataclass
class FileSpec:
    path: str
    requirement_ids: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)  # other file paths
    interfaces: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    verification_contract_ids: list[str] = field(default_factory=list)
    preserve_behaviors: list[str] = field(default_factory=list)
    contracts: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class BlueprintSpec:
    requirements: list[str] = field(default_factory=list)
    files: list[FileSpec] = field(default_factory=list)
    api_routes: list[str] = field(default_factory=list)
    schemas: list[str] = field(default_factory=list)
    config_keys: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    runtime_scenarios: list[str] = field(default_factory=list)
    nfrs: list[str] = field(default_factory=list)
    preserve_behaviors: list[str] = field(default_factory=list)
    entrypoint: str | None = None
    build_command: str | None = None
    start_command: str | None = None
    test_command: str | None = None


def decide_scope(project_mode: str, changed_file_count: int, *, allow_full_redesign: bool = False) -> str:
    """Greenfield -> full_project; existing projects default to change_set unless approved."""
    if project_mode in _GREENFIELD_MODES:
        return "full_project"
    if project_mode == "repair":
        return "repair"
    if changed_file_count > _CHANGE_SET_LIMIT and allow_full_redesign:
        return "full_project"
    return "change_set"


def _el_id(path: str) -> str:
    return f"el:{path}"


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", value).strip("_") or "item"


def generate_blueprint(
    *,
    project_id: str,
    workspace_id: str | None,
    spec: BlueprintSpec,
    project_mode: str,
    source_twin_revision_id: str | None = None,
    scope: str | None = None,
    now: datetime | None = None,
) -> BlueprintRevision:
    scope = scope or decide_scope(project_mode, len(spec.files))
    now = now or datetime.now(timezone.utc)
    elements: list[BlueprintElement] = []
    relations: list[BlueprintRelation] = []

    for f in spec.files:
        verification_ids = list(f.verification_contract_ids) or [f"vc:file:{f.path}"]
        elements.append(BlueprintElement(
            element_id=_el_id(f.path),
            canonical_ref=f"bp://{f.path}",
            element_type="file",
            name=f.path,
            requirement_ids=list(f.requirement_ids),
            depends_on_element_ids=[_el_id(d) for d in f.depends_on],
            expected_actual_refs=[f"file://{f.path}"],
            acceptance_criteria=f.acceptance or [f"{f.path} materialized"],
            verification_contract_ids=verification_ids,
            preserve_behaviors=[*f.preserve_behaviors, *spec.preserve_behaviors],
            properties={"interfaces": f.interfaces, "contracts": f.contracts},
        ))
        for d in f.depends_on:
            relations.append(BlueprintRelation(
                relation_id=f"rel:{f.path}->{d}", source_element_id=_el_id(f.path),
                target_element_id=_el_id(d), relation_type="depends_on",
            ))

    for route in spec.api_routes:
        sid = _safe_id(route)
        elements.append(BlueprintElement(
            element_id=f"el:api:{sid}",
            canonical_ref=f"bp://api/{sid}",
            element_type="api_route",
            name=route,
            requirement_ids=list(spec.requirements),
            acceptance_criteria=[f"API route {route} is implemented with request/response/error contracts"],
            verification_contract_ids=[f"vc:api:{sid}"],
            properties={"route": route, "contract_dimensions": ["request", "response", "error"]},
        ))
    for schema in spec.schemas:
        sid = _safe_id(schema)
        elements.append(BlueprintElement(
            element_id=f"el:schema:{sid}",
            canonical_ref=f"bp://schema/{sid}",
            element_type="schema",
            name=schema,
            requirement_ids=list(spec.requirements),
            acceptance_criteria=[f"schema/data contract {schema} is materialized"],
            verification_contract_ids=[f"vc:schema:{sid}"],
            properties={"schema": schema},
        ))
    for key in spec.config_keys:
        sid = _safe_id(key)
        elements.append(BlueprintElement(
            element_id=f"el:config:{sid}",
            canonical_ref=f"bp://config/{sid}",
            element_type="configuration",
            name=key,
            requirement_ids=list(spec.requirements),
            acceptance_criteria=[f"configuration key {key} is declared"],
            verification_contract_ids=[f"vc:config:{sid}"],
            properties={"config_key": key},
        ))
    for dep in spec.dependencies:
        sid = _safe_id(dep)
        elements.append(BlueprintElement(
            element_id=f"el:dependency:{sid}",
            canonical_ref=f"bp://dependency/{sid}",
            element_type="dependency",
            name=dep,
            requirement_ids=list(spec.requirements),
            acceptance_criteria=[f"dependency {dep} is declared from approved source"],
            verification_contract_ids=[f"vc:dependency:{sid}"],
            properties={"dependency": dep},
        ))
    for scenario in spec.runtime_scenarios:
        sid = _safe_id(scenario)
        elements.append(BlueprintElement(
            element_id=f"el:runtime:{sid}",
            canonical_ref=f"bp://runtime/{sid}",
            element_type="runtime_scenario",
            name=scenario,
            requirement_ids=list(spec.requirements),
            acceptance_criteria=[f"runtime scenario {scenario} is observed"],
            verification_contract_ids=[f"vc:runtime:{sid}"],
            properties={"scenario": scenario},
        ))
    for nfr in spec.nfrs:
        sid = _safe_id(nfr)
        elements.append(BlueprintElement(
            element_id=f"el:nfr:{sid}",
            canonical_ref=f"bp://nfr/{sid}",
            element_type="nfr",
            name=nfr,
            requirement_ids=list(spec.requirements),
            acceptance_criteria=[f"NFR {nfr} is verified"],
            verification_contract_ids=[f"vc:nfr:{sid}"],
            properties={"nfr": nfr},
        ))
    for behavior in spec.preserve_behaviors:
        sid = _safe_id(behavior)
        elements.append(BlueprintElement(
            element_id=f"el:preserve:{sid}",
            canonical_ref=f"bp://preserve/{sid}",
            element_type="preserve_behavior",
            name=behavior,
            requirement_ids=list(spec.requirements),
            acceptance_criteria=[f"preserve behavior {behavior} remains true"],
            verification_contract_ids=[f"vc:preserve:{sid}"],
            properties={"behavior": behavior},
        ))

    if scope == "full_project":
        # exact execution contracts for a buildable/runnable project
        elements.append(BlueprintElement(
            element_id="el:__entrypoint__", canonical_ref="bp://__entrypoint__",
            element_type="entrypoint", name=spec.entrypoint or "main",
            acceptance_criteria=["entrypoint starts"],
            expected_actual_refs=[f"file://{spec.entrypoint}"] if spec.entrypoint else [],
            verification_contract_ids=["vc:entrypoint"],
            properties={"start_command": spec.start_command, "build_command": spec.build_command},
        ))
        for command_kind, command_value in (
            ("build_command", spec.build_command),
            ("start_command", spec.start_command),
            ("test_command", spec.test_command),
        ):
            elements.append(BlueprintElement(
                element_id=f"el:command:{command_kind}",
                canonical_ref=f"bp://command/{command_kind}",
                element_type="command",
                name=command_kind,
                acceptance_criteria=[f"{command_kind} is executable under command authority"],
                verification_contract_ids=[f"vc:command:{command_kind}"],
                properties={"command_kind": command_kind, "command": command_value or ""},
            ))
    if scope == "full_project" or spec.test_command:
        elements.append(BlueprintElement(
            element_id="el:__tests__", canonical_ref="bp://__tests__",
            element_type="test_contract", name="test_contract",
            acceptance_criteria=["test suite passes"],
            verification_contract_ids=["vc:tests"],
            properties={"test_command": spec.test_command or ""},
        ))

    decision = planner_decision("dec:arch", "generated architecture", [], "",
                                [f"mode={project_mode}", f"scope={scope}"])
    return BlueprintRevision(
        blueprint_id=f"bp:{project_id}", revision_id=f"bprev:{project_id}:{int(now.timestamp()*1000)}",
        project_id=project_id, workspace_id=workspace_id, scope=scope,
        source_requirement_ids=list(spec.requirements),
        source_twin_revision_id=source_twin_revision_id, project_mode=project_mode,
        status="proposed", selected_architecture=decision, elements=elements,
        relations=relations, created_at=now,
    )
