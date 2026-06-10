"""Existing capability consolidation and consumer cutover (PI-23).

The machinery to migrate duplicated consumers onto the module facades in a safe, gated
order, WITHOUT deleting legacy paths before the retirement gates pass (ADR-PI-010). It
provides a compatibility-adapter pattern, a shadow comparison, a consumer registry that
tracks migration per capability and enforces the cutover order, and the retirement gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

# Safe cutover order (implementation plan PI-23).
CUTOVER_ORDER = [
    "inspection_api", "planning_context", "generation_context", "impact_map",
    "verification_recommendation", "repair", "final_rollup",
]

LEGACY = "legacy"
FACADE = "facade"


# --- Compatibility adapter pattern -------------------------------------------


@dataclass
class CompatibilityAdapter:
    """Translates a legacy result into a public module contract with provenance.

    Adapters may import legacy public services (the translator function), but they add
    provenance + legacy version and never mutate canonical state.
    """

    capability: str
    legacy_version: str
    translate: Callable[[Any], dict[str, Any]]

    def adapt(self, legacy_result: Any) -> dict[str, Any]:
        out = dict(self.translate(legacy_result))
        out.setdefault("_provenance", {})
        out["_provenance"] = {"source": "legacy_adapter", "capability": self.capability,
                              "legacy_version": self.legacy_version}
        return out


# --- Shadow comparison -------------------------------------------------------


@dataclass
class ParityReport:
    capability: str
    matched: list[str] = field(default_factory=list)
    mismatched: list[tuple[str, Any, Any]] = field(default_factory=list)
    documented_exceptions: list[str] = field(default_factory=list)

    @property
    def parity(self) -> bool:
        # Parity holds when every mismatch is a documented exception.
        return all(field_name in self.documented_exceptions for field_name, _, _ in self.mismatched)


def shadow_compare(capability: str, legacy: dict[str, Any], new: dict[str, Any], *,
                   ignore: tuple[str, ...] = (), documented_exceptions: tuple[str, ...] = ()) -> ParityReport:
    """Compare legacy vs new results field by field (ignoring provenance/meta keys)."""
    ignore_set = set(ignore) | {"_provenance"}
    report = ParityReport(capability=capability, documented_exceptions=list(documented_exceptions))
    keys = (set(legacy) | set(new)) - ignore_set
    for k in sorted(keys):
        lv, nv = legacy.get(k), new.get(k)
        if lv == nv:
            report.matched.append(k)
        else:
            report.mismatched.append((k, lv, nv))
    return report


# --- Consumer registry + cutover ---------------------------------------------


@dataclass
class Consumer:
    name: str
    capability: str
    mode: str = LEGACY
    forbidden_imports_clear: bool = True   # no direct legacy import once migrated


class CutoverError(Exception):
    pass


class ConsumerRegistry:
    def __init__(self) -> None:
        self._consumers: dict[str, Consumer] = {}

    def register(self, consumer: Consumer) -> None:
        self._consumers[consumer.name] = consumer

    def consumers(self, capability: str | None = None) -> list[Consumer]:
        return [c for c in self._consumers.values() if capability is None or c.capability == capability]

    def legacy_consumer_count(self, capability: str) -> int:
        return sum(1 for c in self.consumers(capability) if c.mode == LEGACY)

    def all_facade(self, capability: str) -> bool:
        cs = self.consumers(capability)
        return bool(cs) and all(c.mode == FACADE for c in cs)

    def can_cutover(self, capability: str) -> bool:
        """A capability may cut over only after all earlier capabilities are fully migrated."""
        if capability not in CUTOVER_ORDER:
            return True
        idx = CUTOVER_ORDER.index(capability)
        return all(self.all_facade(c) for c in CUTOVER_ORDER[:idx] if self.consumers(c))

    def migrate(self, consumer_name: str) -> None:
        c = self._consumers[consumer_name]
        if not self.can_cutover(c.capability):
            raise CutoverError(f"cannot cut over {c.capability!r} before earlier capabilities")
        if not c.forbidden_imports_clear:
            raise CutoverError(f"{consumer_name} still has forbidden direct legacy dependency")
        c.mode = FACADE

    def rollback(self, consumer_name: str) -> None:
        """Roll a migrated consumer back to the legacy path (rollback is always available)."""
        self._consumers[consumer_name].mode = LEGACY

    def migrated_consumers_have_no_forbidden_deps(self) -> bool:
        return all(c.forbidden_imports_clear for c in self._consumers.values() if c.mode == FACADE)


# --- Retirement gate (no deletion before parity) -----------------------------


def retirement_ready(
    capability: str,
    registry: ConsumerRegistry,
    parity: ParityReport,
    *,
    rollback_tested: bool,
    tests_pass: bool,
    documented_superiority: bool = False,
) -> tuple[bool, list[str]]:
    """A legacy path may be removed only when every gate passes (ADR-PI-010 / PI-25)."""
    reasons: list[str] = []
    if registry.legacy_consumer_count(capability) != 0:
        reasons.append("legacy consumers remain (consumer count != 0)")
    if not (parity.parity or documented_superiority):
        reasons.append("shadow parity not established and no documented superiority")
    if not rollback_tested:
        reasons.append("rollback/recovery not tested")
    if not tests_pass:
        reasons.append("affected tests / real E2E not passing")
    return (not reasons), reasons
