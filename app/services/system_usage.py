"""Ports for the future system usage collection service.

This module intentionally contains only typing contracts for the staged
``get_system_usage_info()`` extraction. It must stay free of imports from
``main``, settings helpers, and diagnostics globals so importing it has no
runtime collection side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class SettingsPort(Protocol):
    """Settings persistence dependency used by usage collection."""

    def get_setting(self, key: str) -> str | None:
        """Return a setting value for ``key`` or ``None`` when unset."""
        ...

    def set_setting(self, key: str, value: str) -> None:
        """Persist a setting value for ``key``."""
        ...


class UsageDiagnosticsPort(Protocol):
    """Diagnostics dependency used by usage collection and debug payloads."""

    def set_last_usage_diag(self, diag: dict[str, Any]) -> None:
        """Store the latest usage diagnostics payload."""
        ...

    def get_last_usage_diag(self) -> dict[str, Any]:
        """Return a copy or snapshot of the latest usage diagnostics payload."""
        ...


@dataclass(frozen=True, slots=True)
class UsageCollectorPorts:
    """Container for dependencies needed by the future usage collector."""

    settings: SettingsPort
    diagnostics: UsageDiagnosticsPort
