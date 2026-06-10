"""Behavioral graph model for the Digital Twin (PI-7).

Behavioral facts (control flow, side effects, routes, state, events, recovery) are layered
on top of the PI-6 static semantic identities: behavior owners are the static refs
(``py://module#qual``), so identities are reused rather than duplicated.

Every behavioral fact is inferred: it carries a derivation, a confidence < 1.0 and status
``inferred``. Heuristic behavioral facts NEVER become ``verified`` here — only runtime
evidence/reconciliation (PI-8) may upgrade status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

FACT_KINDS = {
    "control_flow", "side_effect", "route", "state", "event", "recovery", "ui_event", "api_call",
}
RELATION_KINDS = {
    "has_control_flow", "performs_side_effect", "handled_by", "mutates_state",
    "produces_event", "consumes_event", "has_recovery", "triggers", "invokes",
    "reaches", "persists_to",
}

INFERRED = "inferred"


@dataclass(frozen=True)
class BehaviorFact:
    ref: str
    kind: str
    label: str = ""
    owner_ref: str = ""          # static semantic ref this behavior belongs to
    derivation: str = "heuristic_static"
    confidence: float = 0.5
    status: str = INFERRED
    file: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BehaviorRelation:
    source_ref: str
    target_ref: str
    kind: str
    derivation: str = "heuristic_static"
    confidence: float = 0.5
    status: str = INFERRED
    file: str = ""


class BehavioralGraph:
    def __init__(self) -> None:
        self._facts: dict[str, BehaviorFact] = {}
        self._rels: dict[tuple[str, str, str], BehaviorRelation] = {}

    def add_fact(self, fact: BehaviorFact) -> None:
        if fact.kind not in FACT_KINDS:
            raise ValueError(f"unknown behavior fact kind {fact.kind!r}")
        if fact.status != INFERRED:
            raise ValueError("behavioral facts must be inferred (heuristics are never verified)")
        self._facts.setdefault(fact.ref, fact)

    def add_relation(self, rel: BehaviorRelation) -> None:
        if rel.kind not in RELATION_KINDS:
            raise ValueError(f"unknown behavior relation kind {rel.kind!r}")
        self._rels.setdefault((rel.source_ref, rel.target_ref, rel.kind), rel)

    def merge(self, facts: Iterable[BehaviorFact], rels: Iterable[BehaviorRelation]) -> None:
        for f in facts:
            self.add_fact(f)
        for r in rels:
            self.add_relation(r)

    def invalidate_file(self, relpath: str) -> tuple[int, int]:
        nf, nr = len(self._facts), len(self._rels)
        self._facts = {r: f for r, f in self._facts.items() if f.file != relpath}
        self._rels = {k: r for k, r in self._rels.items() if r.file != relpath}
        return nf - len(self._facts), nr - len(self._rels)

    def get(self, ref: str) -> BehaviorFact | None:
        return self._facts.get(ref)

    def facts(self, *, kind: str | None = None) -> list[BehaviorFact]:
        items = sorted(self._facts.values(), key=lambda f: f.ref)
        return [f for f in items if kind is None or f.kind == kind]

    def relations(self, *, kind: str | None = None) -> list[BehaviorRelation]:
        items = sorted(self._rels.values(), key=lambda r: (r.source_ref, r.target_ref, r.kind))
        return [r for r in items if kind is None or r.kind == kind]

    def out_relations(self, ref: str, *, kind: str | None = None) -> list[BehaviorRelation]:
        return [r for r in self.relations(kind=kind) if r.source_ref == ref]

    @property
    def fact_count(self) -> int:
        return len(self._facts)

    @property
    def relation_count(self) -> int:
        return len(self._rels)
