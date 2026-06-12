"""Legacy model-execution retirement gate and consumer registry (PFG-37).

Builds a registry of the production code that still calls the legacy model-execution path
(the AtlasLLMJsonAdapter / ``atlas_llm_json_fn`` structured-output executor) and a
retirement gate that REFUSES deletion until the legacy path is consumer-zero AND the
benchmark / shadow / rollback gates pass. This prepares deletion without deleting too
early — it never removes the legacy path itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import Field

from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel

# Markers that identify a direct use of the legacy model-execution path.
LEGACY_MODEL_MARKERS: tuple[str, ...] = ("AtlasLLMJsonAdapter", "atlas_llm_json_fn")

# The legacy owner module and the Forge wrapper are not "consumers to retire".
_EXCLUDED_MODULES: frozenset[str] = frozenset({
    "agent/atlas_llm_json_adapter.py",
    "agent/model_forge/providers/legacy_atlas.py",
    # This module defines the markers as string literals; it is not a consumer.
    "agent/model_forge/retirement.py",
})

RETIREMENT_CHECKLIST: tuple[str, ...] = (
    "consumer_zero",          # no direct legacy model-execution callers remain
    "benchmark_passed",       # real benchmark gate passed
    "shadow_passed",          # stage shadow comparison passed with no regression
    "rollback_available",     # a tested rollback control exists
)


class LegacyModelConsumerRegistry(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    legacy_owner: str = "agent/atlas_llm_json_adapter.py"
    markers: list[str] = Field(default_factory=lambda: list(LEGACY_MODEL_MARKERS))
    consumers: list[str] = Field(default_factory=list)
    legacy_consumer_count: int = 0
    generated_at: str = ""


class RetirementGateResult(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    allowed: bool = False
    legacy_consumer_count: int = 0
    checklist: dict[str, bool] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(("agent/", "app/")) and "/__pycache__/" not in f"/{rel}":
            yield path, rel


def scan_legacy_model_consumers(root: str | Path) -> list[str]:
    """Production modules under agent/ or app/ (excluding tests) that directly reference
    the legacy model-execution path."""
    root = Path(root)
    found: set[str] = set()
    for path, rel in _iter_python_files(root):
        if rel in _EXCLUDED_MODULES or "/tests/" in f"/{rel}" or rel.startswith("tests/"):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(marker in text for marker in LEGACY_MODEL_MARKERS):
            found.add(rel)
    return sorted(found)


def build_model_consumer_registry(root: str | Path) -> LegacyModelConsumerRegistry:
    consumers = scan_legacy_model_consumers(root)
    return LegacyModelConsumerRegistry(
        consumers=consumers,
        legacy_consumer_count=len(consumers),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def evaluate_model_retirement_gate(
    registry: LegacyModelConsumerRegistry,
    *,
    benchmark_passed: bool,
    shadow_passed: bool,
    rollback_available: bool,
) -> RetirementGateResult:
    checklist = {
        "consumer_zero": registry.legacy_consumer_count == 0,
        "benchmark_passed": bool(benchmark_passed),
        "shadow_passed": bool(shadow_passed),
        "rollback_available": bool(rollback_available),
    }
    blocked = [name for name, ok in checklist.items() if not ok]
    return RetirementGateResult(
        allowed=not blocked,
        legacy_consumer_count=registry.legacy_consumer_count,
        checklist=checklist,
        blocked_reasons=([] if not blocked else [f"gate_failed:{n}" for n in blocked]),
    )


__all__ = [
    "LEGACY_MODEL_MARKERS",
    "RETIREMENT_CHECKLIST",
    "LegacyModelConsumerRegistry",
    "RetirementGateResult",
    "scan_legacy_model_consumers",
    "build_model_consumer_registry",
    "evaluate_model_retirement_gate",
]
