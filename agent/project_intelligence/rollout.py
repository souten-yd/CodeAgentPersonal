"""Project Intelligence rollout model (PI-3).

Off by default. Rollout proceeds through off -> shadow -> per-phase active -> full active
(ADR-PI-017). Each stage is reversible: with the flag off, Atlas behaves exactly as the
legacy baseline (no new persistence, no augmented context).

Compatibility: the legacy Project Twin environment variables
(``CODEAGENT_PROJECT_TWIN_*``, PDT-14) remain valid inputs and map into this config when
the new ``CODEAGENT_PROJECT_INTELLIGENCE_*`` variables are unset.

Parsing is pure and deterministic (sorted phase sets, no I/O beyond reading the provided
environment mapping).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# New canonical environment variables.
ENV_ENABLED = "CODEAGENT_PROJECT_INTELLIGENCE_ENABLED"
ENV_SHADOW = "CODEAGENT_PROJECT_INTELLIGENCE_SHADOW"
ENV_PHASES = "CODEAGENT_PROJECT_INTELLIGENCE_PHASES"

# Legacy Project Twin variables (compatibility inputs).
LEGACY_ENV_ENABLED = "CODEAGENT_PROJECT_TWIN_ENABLED"
LEGACY_ENV_SHADOW = "CODEAGENT_PROJECT_TWIN_SHADOW"
LEGACY_ENV_PHASES = "CODEAGENT_PROJECT_TWIN_PHASES"

# The rollout phases consumers may gate on (ADR-PI-017).
PHASES: tuple[str, ...] = ("planning", "generation", "verification", "repair", "greenfield")

_TRUE = {"1", "true", "yes", "on"}


def _get(env: dict | None, key: str, default: str = "") -> str:
    return str((env if env is not None else os.environ).get(key, default))


def _truthy(value: str) -> bool:
    return value.strip().lower() in _TRUE


def _parse_phases(raw: str) -> frozenset[str]:
    # Deterministic: only known phases, order-independent set.
    requested = {p.strip().lower() for p in raw.split(",") if p.strip()}
    return frozenset(p for p in PHASES if p in requested)


@dataclass(frozen=True)
class RolloutConfig:
    """Immutable, deterministic rollout configuration."""

    enabled: bool = False
    shadow: bool = False
    active_phases: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_env(cls, env: dict | None = None) -> "RolloutConfig":
        # Prefer new variables; fall back to legacy twin variables for compatibility.
        enabled_raw = _get(env, ENV_ENABLED) or _get(env, LEGACY_ENV_ENABLED)
        shadow_raw = _get(env, ENV_SHADOW) or _get(env, LEGACY_ENV_SHADOW)
        phases_raw = _get(env, ENV_PHASES) or _get(env, LEGACY_ENV_PHASES)
        return cls(
            enabled=_truthy(enabled_raw),
            shadow=_truthy(shadow_raw),
            active_phases=_parse_phases(phases_raw),
        )

    @classmethod
    def off(cls) -> "RolloutConfig":
        return cls()

    # -- queries --------------------------------------------------------------

    def is_off(self) -> bool:
        return not self.enabled

    def mode(self) -> str:
        if not self.enabled:
            return "off"
        if self.shadow:
            return "shadow"
        return "active"

    def phase_active(self, phase: str) -> bool:
        """True when Project Intelligence should actively augment this phase.

        Shadow never augments (compute-only). With no explicit phase set, an enabled
        non-shadow rollout applies to all phases (full active).
        """
        if not self.enabled or self.shadow:
            return False
        if not self.active_phases:
            return True
        return phase in self.active_phases

    def shadow_active(self, phase: str) -> bool:
        """True when results are computed for comparison but never applied."""
        if not self.enabled or not self.shadow:
            return False
        return not self.active_phases or phase in self.active_phases

    def mode_for_phase(self, phase: str) -> str:
        if self.phase_active(phase):
            return "active"
        if self.shadow_active(phase):
            return "shadow"
        return "off"
