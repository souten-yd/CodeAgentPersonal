"""Ports for the future system usage collection service.

This module intentionally contains only typing contracts for the staged
``get_system_usage_info()`` extraction. It must stay free of imports from
``main``, settings helpers, and diagnostics globals so importing it has no
runtime collection side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol, runtime_checkable


def _parse_int_maybe(value: Any) -> int:
    """Parse a comma-formatted non-negative integer, returning ``-1`` on failure."""
    text = str(value or "").strip().replace(",", "")
    return int(text) if text.isdigit() else -1


def _bytes_to_mb(value: Any) -> int:
    """Convert a byte count to whole MiB, returning ``-1`` for non-numeric input."""
    if not isinstance(value, (int, float)):
        return -1
    return int(value / (1024 * 1024))


def _kb_to_mb(value: Any) -> int:
    """Convert a KiB count to whole MiB, returning ``-1`` for non-numeric input."""
    if not isinstance(value, (int, float)):
        return -1
    return int(value / 1024)


def _calculate_percent(used: int | float, total: int | float) -> float:
    """Return a usage percentage or ``-1.0`` when the ratio is not meaningful."""
    if used >= 0 and total > 0:
        return (used / total) * 100.0
    return -1.0


def _usage_updated_at() -> str:
    """Return the usage payload timestamp in the existing ISO-8601 shape."""
    return datetime.now().isoformat()


def _normalize_static_gpu_usage(gpu: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a static GPU probe row into the ``/system/usage`` GPU shape."""
    return {
        "name": gpu.get("name", "GPU"),
        "util_percent": -1,
        "vram_used_mb": -1,
        "vram_total_mb": gpu.get("memory_total_mb", -1),
        "vram_percent": -1,
    }


class SettingsPort(Protocol):
    """Settings persistence dependency used by usage collection."""

    def get_setting(self, key: str) -> str | None:
        """Return a setting value for ``key`` or ``None`` when unset."""
        ...

    def set_setting(self, key: str, value: str) -> None:
        """Persist a setting value for ``key``."""
        ...


@runtime_checkable
class UsageDiagnosticsPort(Protocol):
    """Diagnostics dependency used by usage collection and debug payloads."""

    def set_last_usage_diag(self, diag: dict[str, Any]) -> None:
        """Store the latest usage diagnostics payload."""
        ...

    def get_last_usage_diag(self) -> dict[str, Any]:
        """Return a copy or snapshot of the latest usage diagnostics payload."""
        ...


@dataclass(slots=True)
class InMemoryUsageDiagnostics:
    """Side-effect-free in-memory diagnostics adapter skeleton.

    This adapter is intentionally disconnected from ``main`` diagnostics globals.
    It exists as a small implementation candidate for the future usage
    collection service boundary.
    """

    _diag: dict[str, Any] = field(default_factory=dict)

    def set_last_usage_diag(self, diag: dict[str, Any]) -> None:
        """Store a shallow copy of the latest usage diagnostics payload."""
        self._diag = dict(diag)

    def get_last_usage_diag(self) -> dict[str, Any]:
        """Return a shallow copy of the latest usage diagnostics payload."""
        return dict(self._diag)


@dataclass(frozen=True, slots=True)
class UsageCollectorPorts:
    """Container for dependencies needed by the future usage collector."""

    settings: SettingsPort
    diagnostics: UsageDiagnosticsPort
