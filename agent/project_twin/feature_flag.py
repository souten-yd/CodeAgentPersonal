"""Project Digital Twin rollout flag (PDT-14).

Disabled by default. The twin is rolled out per phase behind this flag with an optional
shadow mode (twin context is computed for comparison but the caller's baseline is what is
used). This guarantees a rollback path: with the flag off, Atlas behaves exactly as before.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

ENV_ENABLED = "CODEAGENT_PROJECT_TWIN_ENABLED"
ENV_SHADOW = "CODEAGENT_PROJECT_TWIN_SHADOW"
ENV_PHASES = "CODEAGENT_PROJECT_TWIN_PHASES"

_TRUE = {"1", "true", "yes", "on"}


def _env(env, key, default=""):
    return (env or os.environ).get(key, default)


def is_twin_enabled(env: dict | None = None) -> bool:
    return str(_env(env, ENV_ENABLED, "")).strip().lower() in _TRUE


@dataclass
class RolloutConfig:
    enabled: bool = False
    shadow: bool = False
    enabled_phases: set[str] = field(default_factory=set)

    @classmethod
    def from_env(cls, env: dict | None = None) -> "RolloutConfig":
        enabled = is_twin_enabled(env)
        shadow = str(_env(env, ENV_SHADOW, "")).strip().lower() in _TRUE
        phases_raw = str(_env(env, ENV_PHASES, "")).strip()
        phases = {p.strip() for p in phases_raw.split(",") if p.strip()}
        return cls(enabled=enabled, shadow=shadow, enabled_phases=phases)

    def phase_active(self, phase: str) -> bool:
        """True when the twin should actually augment context for this phase.

        Shadow mode never augments (it only computes for comparison). When no explicit
        phase set is configured, an enabled non-shadow rollout applies to all phases.
        """

        if not self.enabled or self.shadow:
            return False
        if not self.enabled_phases:
            return True
        return phase in self.enabled_phases

    def shadow_active(self, phase: str) -> bool:
        """True when the twin should be computed for comparison but not applied."""

        if not self.enabled or not self.shadow:
            return False
        return not self.enabled_phases or phase in self.enabled_phases
