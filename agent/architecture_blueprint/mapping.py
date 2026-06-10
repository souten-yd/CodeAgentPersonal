"""Blueprint-to-Actual mapping hints (PI-12).

Produces explicit expected-actual references and deterministic mapping hints between a
Blueprint revision and a public Actual snapshot, WITHOUT coupling the Blueprint to Digital
Twin internals: the snapshot is a list of public entries (ref/name/kind), never a
SemanticGraph or SQLite row. Heuristic suggestions are always ``inferred`` and never
silently accepted as verified — only ``confirm_mapping`` with evidence yields ``verified``.
Every hint carries both the Blueprint and Twin revision ids, so mapping history follows
both revisions.

This module must not import ``agent.project_twin`` (no Twin-internal coupling).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.architecture_blueprint.contracts import BlueprintRevision

# Relations (contracts/PI-12).
MATERIALIZED_AS = "materialized_as"
IMPLEMENTED_BY = "implemented_by"
REALIZED_BY = "realized_by"
SATISFIES = "satisfies"
VERIFIED_BY = "verified_by"
DIVERGES_FROM = "diverges_from"
BLOCKED_BY = "blocked_by"

RELATIONS = {MATERIALIZED_AS, IMPLEMENTED_BY, REALIZED_BY, SATISFIES, VERIFIED_BY, DIVERGES_FROM, BLOCKED_BY}

INFERRED = "inferred"
VERIFIED = "verified"


@dataclass(frozen=True)
class ActualEntry:
    """A public Actual reference (from a Twin snapshot/package, not its internals)."""
    ref: str
    name: str = ""
    kind: str = ""


def snapshot_from_public(entries: list[dict]) -> list[ActualEntry]:
    """Build an Actual snapshot from public dicts (e.g. a TwinQueryResult item list)."""
    return [ActualEntry(ref=str(e.get("ref", "")), name=str(e.get("name", "")),
                        kind=str(e.get("kind", ""))) for e in entries]


@dataclass(frozen=True)
class MappingHint:
    blueprint_element_id: str
    relation: str
    actual_ref: str | None
    confidence: float
    status: str
    basis: str
    blueprint_revision_id: str
    twin_revision_id: str | None
    evidence_refs: tuple[str, ...] = ()


def suggest_mappings(
    revision: BlueprintRevision,
    snapshot: list[ActualEntry],
    *,
    twin_revision_id: str | None,
) -> list[MappingHint]:
    """Deterministically suggest mapping hints. All hints are inferred (never verified)."""
    by_ref = {e.ref: e for e in snapshot}
    by_name: dict[str, list[ActualEntry]] = {}
    for e in snapshot:
        if e.name:
            by_name.setdefault(e.name, []).append(e)

    hints: list[MappingHint] = []
    for el in revision.elements:
        # 1) exact expected-actual ref present in the snapshot -> materialized_as.
        exact = next((r for r in el.expected_actual_refs if r in by_ref), None)
        if exact:
            hints.append(MappingHint(el.element_id, MATERIALIZED_AS, exact, 0.9, INFERRED,
                                     "exact_expected_ref", revision.revision_id, twin_revision_id))
            continue
        # 2) heuristic name match -> realized_by (low confidence, inferred).
        name_matches = by_name.get(el.name, [])
        if name_matches:
            hints.append(MappingHint(el.element_id, REALIZED_BY, name_matches[0].ref, 0.5, INFERRED,
                                     "name_heuristic", revision.revision_id, twin_revision_id))
            continue
        # 3) mandatory but unmatched -> blocked_by (gap).
        if el.mandatory:
            hints.append(MappingHint(el.element_id, BLOCKED_BY, None, 0.8, INFERRED,
                                     "no_actual_match", revision.revision_id, twin_revision_id))
    return hints


def confirm_mapping(hint: MappingHint, evidence_refs: list[str]) -> MappingHint:
    """Promote a hint to verified — only with non-empty evidence (never silent)."""
    if not evidence_refs:
        raise ValueError("confirm_mapping requires evidence; heuristic mapping is not verified")
    return MappingHint(
        blueprint_element_id=hint.blueprint_element_id, relation=VERIFIED_BY,
        actual_ref=hint.actual_ref, confidence=1.0, status=VERIFIED, basis="evidence",
        blueprint_revision_id=hint.blueprint_revision_id, twin_revision_id=hint.twin_revision_id,
        evidence_refs=tuple(evidence_refs),
    )


@dataclass
class MappingSet:
    blueprint_revision_id: str
    twin_revision_id: str | None
    hints: list[MappingHint] = field(default_factory=list)

    def key(self) -> tuple[str, str | None]:
        return (self.blueprint_revision_id, self.twin_revision_id)


def build_mapping_set(revision: BlueprintRevision, snapshot: list[ActualEntry], *,
                      twin_revision_id: str | None) -> MappingSet:
    return MappingSet(blueprint_revision_id=revision.revision_id, twin_revision_id=twin_revision_id,
                      hints=suggest_mappings(revision, snapshot, twin_revision_id=twin_revision_id))
