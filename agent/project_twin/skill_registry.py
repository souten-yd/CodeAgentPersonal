"""Skill registry, resolver and twin integration (PDT-7).

Loads `SKILL.md` assets into a registry with a content hash and version, resolves
task-relevant skills with explicit reasons, and records activations into the twin for
traceability.

Safety precedence is structural: any authority-shaped frontmatter keys
(allowed_paths/commands/approval/...) are *quarantined* — recorded as inert metadata and
never surfaced as applicability or activation authority. A skill can inform selection; it
can never expand allowed paths, commands or approval authority.

Implements `TwinSkillPort` (resolve / record_activation).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agent.project_twin.contracts import (
    ContextItem,
    SkillActivation,
    SkillResolutionRequest,
    SkillResolutionResult,
    TwinDelta,
    TwinNode,
)
from agent.project_twin.static_graph import nid

#: Frontmatter keys that must never grant execution authority.
AUTHORITY_KEYS = frozenset(
    {"allowed_paths", "commands", "command", "approval", "approvals", "authority",
     "allow_commands", "permissions", "allow", "exec", "run_commands"}
)


@dataclass
class SkillDefinition:
    skill_id: str
    name: str
    version: str
    content_hash: str
    description: str = ""
    keywords: tuple[str, ...] = ()
    phases: tuple[str, ...] = ()
    path: str = ""
    quarantined_authority: dict = field(default_factory=dict)

    @property
    def canonical_ref(self) -> str:
        return f"skill://{self.skill_id}@{self.version}"


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse a leading ``---`` fenced ``key: value`` block. Returns (meta, body)."""

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    meta: dict = {}
    body_start = len(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        if ":" in lines[i]:
            k, _, v = lines[i].partition(":")
            meta[k.strip().lower()] = v.strip()
    return meta, "\n".join(lines[body_start:]).strip()


def _split_list(value: str) -> tuple[str, ...]:
    return tuple(s.strip() for s in value.replace(";", ",").split(",") if s.strip())


def load_skill_file(path: Path) -> SkillDefinition:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _parse_frontmatter(text)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    skill_id = meta.get("id") or meta.get("name") or path.parent.name
    quarantined = {k: meta[k] for k in list(meta) if k in AUTHORITY_KEYS}
    return SkillDefinition(
        skill_id=skill_id,
        name=meta.get("name", skill_id),
        version=meta.get("version") or content_hash[:12],
        content_hash=content_hash,
        description=meta.get("description", "") or body[:200],
        keywords=_split_list(meta.get("keywords", "")),
        phases=_split_list(meta.get("phases", "")),
        path=str(path),
        quarantined_authority=quarantined,
    )


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, definition: SkillDefinition) -> None:
        self._skills[definition.skill_id] = definition

    def load_dir(self, root: str | Path) -> int:
        root = Path(root)
        count = 0
        if not root.is_dir():
            return 0
        for path in sorted(root.rglob("SKILL.md")):
            self.register(load_skill_file(path))
            count += 1
        return count

    def list_skills(self) -> list[SkillDefinition]:
        return [self._skills[k] for k in sorted(self._skills)]

    def get(self, skill_id: str) -> SkillDefinition | None:
        return self._skills.get(skill_id)


class SkillResolver:
    """Pure `TwinSkillPort` over a registry; records activations into the twin store."""

    def __init__(self, registry: SkillRegistry, twin_store=None) -> None:
        self._registry = registry
        self._store = twin_store

    def resolve(self, request: SkillResolutionRequest) -> SkillResolutionResult:
        objective = request.objective.lower()
        scored: list[tuple[float, ContextItem]] = []
        for skill in self._registry.list_skills():
            reasons: list[str] = []
            score = 0.0
            for kw in skill.keywords:
                if kw and kw.lower() in objective:
                    score += 1.0
                    reasons.append(f"keyword:{kw}")
            if request.phase in skill.phases:
                score += 0.5
                reasons.append(f"phase:{request.phase}")
            if score <= 0:
                continue
            scored.append((
                score,
                ContextItem(
                    item_type="skill",
                    canonical_ref=skill.canonical_ref,
                    summary=f"{skill.name} v{skill.version}",
                    status="declared",
                    confidence=min(1.0, 0.5 + 0.1 * score),
                    source_refs=[skill.path],
                    evidence_refs=[],
                    inclusion_reason=", ".join(reasons),
                    estimated_tokens=max(1, len(skill.name) // 4 + 6),
                ),
            ))
        scored.sort(key=lambda t: t[0], reverse=True)
        diagnostics = []
        quarantined = [s.skill_id for s in self._registry.list_skills() if s.quarantined_authority]
        if quarantined:
            diagnostics.append({"code": "authority_metadata_quarantined", "skills": quarantined})
        return SkillResolutionResult(
            project_id=request.project_id,
            skills=[it for _, it in scored[: request.limit]],
            diagnostics=diagnostics,
        )

    def record_activation(self, activation: SkillActivation) -> None:
        if self._store is None:
            return
        now = activation.activated_at or datetime.now(timezone.utc)
        ref = f"skill_activation://{activation.skill_ref}/{activation.content_hash[:12]}"
        node = TwinNode(
            node_id=nid(ref), project_id=activation.project_id, domain="learning",
            node_type="skill_activation", canonical_ref=ref,
            label=f"{activation.skill_ref}@{activation.skill_version}", source_kind="skill",
            source_ref=activation.skill_ref, derivation="user_decision", confidence=1.0,
            status="declared",
            properties={
                "activation_reason": activation.activation_reason,
                "phase": activation.phase,
                "outcome": activation.outcome,
                "skill_version": activation.skill_version,
                "content_hash": activation.content_hash,
            },
            valid_from=now, created_at=now, updated_at=now,
        )
        self._store.apply_delta(
            TwinDelta(
                project_id=activation.project_id,
                idempotency_key=f"skill_activation:{ref}:{now.isoformat()}",
                trigger_type="skill.activated", nodes=[node],
            )
        )
