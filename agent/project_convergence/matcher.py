"""Deterministic Blueprint-element matcher (PI-13).

Matches Blueprint elements to a public Actual snapshot using the PI-12 mapping hints. It
consumes only public data (snapshot entries + mapping hints) — no Twin internals, no
Blueprint store internals. Matching is reproducible (sorted, pure).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.architecture_blueprint.contracts import BlueprintRevision
from agent.architecture_blueprint.mapping import (
    ActualEntry,
    BLOCKED_BY,
    MATERIALIZED_AS,
    MappingHint,
    suggest_mappings,
)


@dataclass
class MatchInfo:
    element_id: str
    relation: str | None
    matched_actual_refs: list[str] = field(default_factory=list)
    missing_actual_refs: list[str] = field(default_factory=list)
    mandatory: bool = True


def match_elements(
    revision: BlueprintRevision,
    snapshot: list[ActualEntry],
    *,
    twin_revision_id: str | None,
    hints: list[MappingHint] | None = None,
) -> dict[str, MatchInfo]:
    snapshot_refs = {e.ref for e in snapshot}
    hints = hints if hints is not None else suggest_mappings(revision, snapshot, twin_revision_id=twin_revision_id)
    by_el = {h.blueprint_element_id: h for h in hints}

    out: dict[str, MatchInfo] = {}
    for el in revision.elements:
        hint = by_el.get(el.element_id)
        expected = list(el.expected_actual_refs)
        matched = sorted(r for r in expected if r in snapshot_refs)
        missing = sorted(r for r in expected if r not in snapshot_refs)
        relation = hint.relation if hint else None
        if hint and hint.actual_ref and hint.actual_ref not in matched and relation != BLOCKED_BY:
            matched = sorted(set(matched) | {hint.actual_ref})
        out[el.element_id] = MatchInfo(element_id=el.element_id, relation=relation,
                                       matched_actual_refs=matched, missing_actual_refs=missing,
                                       mandatory=el.mandatory)
    return out
