"""Model-facing instruction compiler for Atlas Twin Control Plane.

The compiler is pure policy glue: it turns an ExecutionPolicy and TwinBrief into
deterministic text for a model. It does not execute, apply, verify, or publish.
"""
from __future__ import annotations

from hashlib import sha1
from typing import Iterable

from pydantic import Field

from agent.twin_control_plane.contracts import (
    ExecutionPolicy,
    InstructionStyle,
    ModelCapabilityMode,
    TwinBrief,
    TwinConstraint,
    TwinControlPlaneModel,
)


class CompiledInstruction(TwinControlPlaneModel):
    instruction_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    brief_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    sections: list[str] = Field(default_factory=list)


def _stable_id(parts: Iterable[str]) -> str:
    data = "|".join(p for p in parts if p)
    return "instruction_" + sha1(data.encode("utf-8")).hexdigest()[:12]


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _constraint_key(constraint: TwinConstraint) -> tuple[str, str]:
    return (constraint.constraint_id, constraint.text)


def _merged_constraints(policy: ExecutionPolicy, brief: TwinBrief) -> list[TwinConstraint]:
    merged: dict[tuple[str, str], TwinConstraint] = {}
    for constraint in [*policy.hard_constraints, *brief.hard_constraints]:
        if constraint.constraint_type != "hard":
            continue
        merged.setdefault(_constraint_key(constraint), constraint)
    return [merged[key] for key in sorted(merged)]


def _bullet_section(title: str, values: Iterable[str], *, fallback: str = "None recorded.") -> list[str]:
    items = _unique(values)
    lines = [f"## {title}"]
    if not items:
        lines.append(f"- {fallback}")
        return lines
    lines.extend(f"- {item}" for item in items)
    return lines


def _constraint_lines(constraints: Iterable[TwinConstraint]) -> list[str]:
    lines = ["## Hard Constraints"]
    for constraint in constraints:
        refs = ", ".join(_unique(constraint.refs))
        suffix = f" refs={refs}" if refs else ""
        lines.append(f"- [{constraint.constraint_id}] {constraint.text}{suffix}")
    return lines


def _git_lines(policy: ExecutionPolicy) -> list[str]:
    git = policy.git_policy
    lines = ["## Git And Publication Policy"]
    lines.append(f"- local_branch_required={git.local_branch_required}")
    lines.append(f"- worktree_preferred={git.worktree_preferred}")
    lines.append(f"- local_commit_required={git.local_commit_required}")
    lines.append("- Remote publication and remote mutation require explicit approval.")
    return lines


def _mode_directive(policy: ExecutionPolicy) -> list[str]:
    lines = ["## Model Mode"]
    mode = policy.model_capability_mode
    style = policy.instruction_style
    lines.append(f"- mode={mode.value}")
    lines.append(f"- instruction_style={style.value}")
    lines.append(f"- twin_injection_level={int(policy.twin_injection_level)}")

    if mode == ModelCapabilityMode.WEAK_LOCAL:
        lines.append("- Use constrained implementation steps. Do not infer authority beyond listed refs, gates, tests, and proof requirements.")
    elif mode == ModelCapabilityMode.FRONTIER_ASSISTED:
        lines.append("- You may propose design alternatives, but hard constraints and approval gates are not optional.")
        lines.append("- Twin Challenge is allowed only as advisory critique with evidence; do not bypass Safe Apply, tests, or gates.")
    elif mode == ModelCapabilityMode.AUDIT_ONLY or style == InstructionStyle.AUDIT_ONLY:
        lines.append("- Audit only. Do not mutate files, stage changes, commit, publish, or imply direct apply authority.")
    else:
        lines.append("- Implement within the selected route and preserve the listed contracts.")
    return lines


def _interface_first_lines(brief: TwinBrief) -> list[str]:
    lines = ["## Interface First Sequence"]
    lines.append("1. Public interfaces and API contracts: define or preserve the listed interfaces before implementation.")
    lines.append("2. Persistence and artifact schemas: state expected create/read/reload and migration behavior before implementation.")
    lines.append("3. Backend-to-UI or runtime state contracts: state authoritative backend fields and projection expectations before implementation.")
    lines.append("4. Test contracts and fixtures: identify required tests, bootstrap scenarios, and proof data before implementation.")
    for section in brief.metadata.get("interface_first_sections", []):
        if not isinstance(section, dict):
            continue
        kind = str(section.get("kind") or "interface_section")
        refs = ", ".join(_unique(section.get("refs") or [])) or "no explicit refs"
        lines.append(f"- {kind}: refs={refs}")
        for step in section.get("contract_steps") or []:
            if str(step).strip():
                lines.append(f"  contract: {str(step).strip()}")
        for proof in section.get("proof_requirements") or []:
            if str(proof).strip():
                lines.append(f"  proof: {str(proof).strip()}")
    lines.append("5. Implementation steps: edit code only after the interface/schema/state/test contracts above are explicit.")
    if brief.required_interfaces:
        lines.append("Required interface refs: " + ", ".join(_unique(brief.required_interfaces)))
    return lines


def _stale_test_policy_lines() -> list[str]:
    return [
        "## Test Debt Policy",
        "- Stale tests are retirement candidates only; do not delete or weaken them without explicit proof and approval.",
        "- A failing test must be classified as product regression, stale contract, missing mock, environment unavailable, or insufficient evidence.",
    ]


def compile_model_instruction(brief: TwinBrief, policy: ExecutionPolicy) -> CompiledInstruction:
    """Compile deterministic model-facing instructions from policy and brief."""
    constraints = _merged_constraints(policy, brief)
    sections: list[str] = []
    chunks: list[list[str]] = []

    def add(title: str, lines: list[str]) -> None:
        sections.append(title)
        chunks.append(lines)

    add("header", [
        "# Atlas Implementation Instruction",
        f"policy_id: {policy.policy_id}",
        f"brief_id: {brief.brief_id}",
        f"goal: {brief.goal or 'unspecified'}",
        f"route: {policy.route.value}",
    ])
    add("model_mode", _mode_directive(policy))
    add("hard_constraints", _constraint_lines(constraints))
    add("git_policy", _git_lines(policy))
    add("allowed_refs", _bullet_section("Allowed Refs", brief.allowed_refs, fallback="No refs explicitly allowed; inspect before editing."))
    add("forbidden_refs", _bullet_section("Forbidden Refs", brief.forbidden_refs, fallback="No forbidden refs recorded."))
    add("contracts", _bullet_section("Contracts To Preserve", brief.contracts_to_preserve))

    if policy.instruction_style == InstructionStyle.INTERFACE_FIRST:
        add("interface_first", _interface_first_lines(brief))

    add("required_tests", _bullet_section("Required Tests", brief.required_tests, fallback="No required tests recorded; add focused coverage for changed behavior."))
    add("proof_requirements", _bullet_section("Proof Requirements", brief.proof_requirements, fallback="Record focused tests and unavailable checks truthfully."))
    add("required_gates", _bullet_section("Required Gates", policy.required_gates))
    add("test_debt_policy", _stale_test_policy_lines())
    add("advisory_context", _bullet_section(
        "Advisory Context (Non-Authoritative)",
        [*policy.advisory_context, *brief.advisory_context],
        fallback="No advisory context recorded.",
    ))

    if policy.model_capability_mode == ModelCapabilityMode.AUDIT_ONLY or policy.instruction_style == InstructionStyle.AUDIT_ONLY:
        add("audit_obligations", [
            "## Audit Obligations",
            "- Review for behavioral regressions, missing tests, proof gaps, authority boundary violations, and unavailable evidence reported as passed.",
            "- Return findings and suggested repairs only; do not present a patch as already applied.",
        ])
    else:
        add("implementation_obligations", [
            "## Implementation Obligations",
            "- Make the smallest coherent change that satisfies the goal.",
            "- Keep Safe Apply, Proposal, verification, and approval boundaries intact.",
            "- Report exact focused test commands and unavailable real model/runtime checks.",
        ])

    text = "\n".join(line for chunk in chunks for line in [*chunk, ""]).rstrip() + "\n"
    return CompiledInstruction(
        instruction_id=_stable_id([policy.policy_id, brief.brief_id, text]),
        policy_id=policy.policy_id,
        brief_id=brief.brief_id,
        text=text,
        sections=sections,
    )


__all__ = ["CompiledInstruction", "compile_model_instruction"]
