"""Blueprint generation (PI-11).

Deterministic assembly of a Blueprint revision from a structured spec. Per ADR-PI-008,
deterministic code owns identity, dependency order, and requirement mapping; an LLM may
produce the spec content (file list, interfaces, commands) but within these contracts. The
generated Blueprint uses planned ``bp://`` refs only; Actual refs appear solely as
``expected_actual_refs`` materialization targets.
"""

from __future__ import annotations

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


@dataclass
class BlueprintSpec:
    requirements: list[str] = field(default_factory=list)
    files: list[FileSpec] = field(default_factory=list)
    entrypoint: str | None = None
    build_command: str | None = None
    start_command: str | None = None
    test_command: str | None = None


def decide_scope(project_mode: str, changed_file_count: int) -> str:
    """Greenfield -> full_project; an existing small change -> change_set (not a redesign)."""
    if project_mode in _GREENFIELD_MODES:
        return "full_project"
    if project_mode == "repair":
        return "repair"
    return "change_set" if changed_file_count <= _CHANGE_SET_LIMIT else "full_project"


def _el_id(path: str) -> str:
    return f"el:{path}"


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
        elements.append(BlueprintElement(
            element_id=_el_id(f.path),
            canonical_ref=f"bp://{f.path}",
            element_type="file",
            name=f.path,
            requirement_ids=list(f.requirement_ids),
            depends_on_element_ids=[_el_id(d) for d in f.depends_on],
            expected_actual_refs=[f"file://{f.path}"],
            acceptance_criteria=f.acceptance or [f"{f.path} materialized"],
            verification_contract_ids=list(f.verification_contract_ids),
            properties={"interfaces": f.interfaces},
        ))
        for d in f.depends_on:
            relations.append(BlueprintRelation(
                relation_id=f"rel:{f.path}->{d}", source_element_id=_el_id(f.path),
                target_element_id=_el_id(d), relation_type="depends_on",
            ))

    if scope == "full_project":
        # exact execution contracts for a buildable/runnable project
        elements.append(BlueprintElement(
            element_id="el:__entrypoint__", canonical_ref="bp://__entrypoint__",
            element_type="entrypoint", name=spec.entrypoint or "main",
            acceptance_criteria=["entrypoint starts"],
            expected_actual_refs=[f"file://{spec.entrypoint}"] if spec.entrypoint else [],
            properties={"start_command": spec.start_command, "build_command": spec.build_command},
        ))
        elements.append(BlueprintElement(
            element_id="el:__tests__", canonical_ref="bp://__tests__",
            element_type="test_contract", name="test_contract",
            acceptance_criteria=["test suite passes"],
            verification_contract_ids=["vc:tests"],
            properties={"test_command": spec.test_command},
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
