"""Evidence-bound Anti-Pattern Memory for future repair and prompt guardrails."""
from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Iterable

from pydantic import Field

from agent.twin_control_plane.contracts import TwinControlPlaneModel
from agent.twin_control_plane.proof_ledger import ProofLedgerEntry
from agent.twin_control_plane.repair_compass import RepairCategory, RepairCompassReport


class AntiPatternSource(StrEnum):
    PROOF_LEDGER = "proof_ledger"
    RUNTIME_INCIDENT = "runtime_incident"
    REJECTED_PATCH = "rejected_patch"
    REPAIR_COMPASS = "repair_compass"


class GuardrailStrength(StrEnum):
    HARD = "hard"
    SOFT = "soft"
    ADVISORY = "advisory"


class AntiPatternEntry(TwinControlPlaneModel):
    pattern_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source: AntiPatternSource
    categories: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    model_ids: list[str] = Field(default_factory=list)
    routes: list[str] = Field(default_factory=list)
    project_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    occurrences: int = Field(default=1, ge=1)
    environment_related: bool = False
    product_regression: bool = False


class AntiPatternMemory(TwinControlPlaneModel):
    memory_id: str = Field(min_length=1)
    entries: list[AntiPatternEntry] = Field(default_factory=list)


class GuardrailHint(TwinControlPlaneModel):
    hint_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    strength: GuardrailStrength
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    model_ids: list[str] = Field(default_factory=list)
    routes: list[str] = Field(default_factory=list)
    project_refs: list[str] = Field(default_factory=list)


def _unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _merge_entry(existing: AntiPatternEntry, incoming: AntiPatternEntry) -> AntiPatternEntry:
    return existing.model_copy(update={
        "title": incoming.title or existing.title,
        "description": incoming.description or existing.description,
        "categories": _unique([*existing.categories, *incoming.categories]),
        "evidence_refs": _unique([*existing.evidence_refs, *incoming.evidence_refs]),
        "model_ids": _unique([*existing.model_ids, *incoming.model_ids]),
        "routes": _unique([*existing.routes, *incoming.routes]),
        "project_refs": _unique([*existing.project_refs, *incoming.project_refs]),
        "confidence": max(existing.confidence, incoming.confidence),
        "occurrences": existing.occurrences + incoming.occurrences,
        "environment_related": existing.environment_related or incoming.environment_related,
        "product_regression": existing.product_regression or incoming.product_regression,
    })


def record_anti_pattern(memory: AntiPatternMemory, entry: AntiPatternEntry) -> AntiPatternMemory:
    """Record or merge one evidence-bound anti-pattern entry."""
    entries: list[AntiPatternEntry] = []
    merged = False
    normalized = entry.model_copy(update={
        "categories": _unique(entry.categories),
        "evidence_refs": _unique(entry.evidence_refs),
        "model_ids": _unique(entry.model_ids),
        "routes": _unique(entry.routes),
        "project_refs": _unique(entry.project_refs),
    })
    for existing in memory.entries:
        if existing.pattern_id == normalized.pattern_id:
            entries.append(_merge_entry(existing, normalized))
            merged = True
        else:
            entries.append(existing)
    if not merged:
        entries.append(normalized)
    entries.sort(key=lambda item: item.pattern_id)
    return memory.model_copy(update={"entries": entries})


def record_from_proof_ledger(
    memory: AntiPatternMemory,
    entry: ProofLedgerEntry,
    *,
    pattern_id: str,
    title: str,
    categories: Iterable[str],
    confidence: float,
    model_id: str = "",
    route: str = "",
) -> AntiPatternMemory:
    evidence_refs = _unique([
        entry.entry_id,
        *entry.test_refs,
        *entry.runtime_evidence_refs,
        *entry.gate_refs,
    ])
    product_regression = "verification_failed" in entry.repair_reasons
    return record_anti_pattern(memory, AntiPatternEntry(
        pattern_id=pattern_id,
        title=title,
        description="Failure pattern derived from Proof Ledger evidence.",
        source=AntiPatternSource.PROOF_LEDGER,
        categories=list(categories),
        evidence_refs=evidence_refs,
        model_ids=[model_id] if model_id else [],
        routes=[route] if route else [],
        confidence=confidence,
        environment_related="verification_unavailable" in entry.repair_reasons and not product_regression,
        product_regression=product_regression,
    ))


def record_from_repair_compass(
    memory: AntiPatternMemory,
    report: RepairCompassReport,
    *,
    source_ref: str,
    pattern_id: str = "",
    confidence: float = 0.5,
) -> AntiPatternMemory:
    categories = _unique(instruction.category.value for instruction in report.instructions)
    environment_related = bool(report.environment_unavailable_refs) and not report.product_regression_refs
    product_regression = bool(report.product_regression_refs)
    stable_id = pattern_id or f"repair_compass:{report.policy_id}:{','.join(categories) or 'unknown'}"
    return record_anti_pattern(memory, AntiPatternEntry(
        pattern_id=stable_id,
        title="Recurring Repair Compass outcome",
        description="Repair Compass produced a recurring repair category set.",
        source=AntiPatternSource.REPAIR_COMPASS,
        categories=categories,
        evidence_refs=_unique([source_ref, report.report_id, *report.product_regression_refs, *report.environment_unavailable_refs]),
        confidence=confidence,
        environment_related=environment_related,
        product_regression=product_regression,
    ))


def guardrail_hints(
    memory: AntiPatternMemory,
    *,
    model_id: str = "",
    route: str = "",
    project_ref: str = "",
    min_confidence: float = 0.5,
) -> list[GuardrailHint]:
    """Return evidence-bound guardrail hints scoped to the requested context."""
    hints: list[GuardrailHint] = []
    for entry in memory.entries:
        if entry.confidence < min_confidence or not entry.evidence_refs:
            continue
        if model_id and entry.model_ids and model_id not in entry.model_ids:
            continue
        if route and entry.routes and route not in entry.routes:
            continue
        if project_ref and entry.project_refs and project_ref not in entry.project_refs:
            continue

        categories = set(entry.categories)
        if entry.environment_related and not entry.product_regression:
            strength = GuardrailStrength.ADVISORY
            text = f"Environment issue observed before: {entry.title}. Keep unavailable evidence separate from product-regression claims."
        elif entry.occurrences >= 2 and {"test_weakening", "gate_weakening"} & categories:
            strength = GuardrailStrength.HARD
            text = f"Repeated anti-pattern: {entry.title}. Do not weaken tests or gates; require evidence-backed repair."
        elif entry.occurrences >= 2:
            strength = GuardrailStrength.SOFT
            text = f"Recurring anti-pattern: {entry.title}. Check this risk, but verify against current evidence."
        else:
            strength = GuardrailStrength.ADVISORY
            text = f"Possible anti-pattern: {entry.title}. Treat as advisory until current evidence confirms relevance."

        hints.append(GuardrailHint(
            hint_id=f"guardrail:{entry.pattern_id}",
            text=text,
            strength=strength,
            confidence=entry.confidence,
            evidence_refs=list(entry.evidence_refs),
            model_ids=list(entry.model_ids),
            routes=list(entry.routes),
            project_refs=list(entry.project_refs),
        ))
    return sorted(hints, key=lambda hint: hint.hint_id)


class AntiPatternMemoryStore:
    """Durable, evidence-bound Anti-Pattern Memory persistence (one JSON file per memory).

    Survives reload and merges by ``pattern_id`` (via ``record_anti_pattern``), so repeated
    failure patterns across runs accumulate occurrences/evidence rather than duplicating.
    Used to feed prior-run guardrails into later live runs."""

    def __init__(self, store_dir: str | Path) -> None:
        self._dir = Path(store_dir)

    def _path(self, memory_id: str) -> Path:
        safe = (memory_id or "default").replace("/", "_").replace(":", "_")
        return self._dir / f"{safe}.json"

    def load(self, memory_id: str = "default") -> AntiPatternMemory:
        path = self._path(memory_id)
        if path.exists():
            try:
                return AntiPatternMemory.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return AntiPatternMemory(memory_id=memory_id or "default")

    def save(self, memory: AntiPatternMemory) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(memory.memory_id).write_text(
            json.dumps(memory.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record(self, entry: AntiPatternEntry, *, memory_id: str = "default") -> AntiPatternMemory:
        memory = record_anti_pattern(self.load(memory_id), entry)
        self.save(memory)
        return memory


__all__ = [
    "AntiPatternEntry",
    "AntiPatternMemory",
    "AntiPatternMemoryStore",
    "AntiPatternSource",
    "GuardrailHint",
    "GuardrailStrength",
    "guardrail_hints",
    "record_anti_pattern",
    "record_from_proof_ledger",
    "record_from_repair_compass",
]
