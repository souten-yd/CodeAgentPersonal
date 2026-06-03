from __future__ import annotations

import json
from pathlib import Path

# Human-in-the-loop automation features. These control WHEN the autonomous pipeline stops for a
# human, and are the single knob shared by the plan-time critique gate
# (agent/atlas_plan_quality_gate.py), the apply-time full_auto gate (agent/atlas_full_auto_gate.py)
# and the autonomous orchestrator (agent/atlas_autonomous_codegen_orchestrator_service.py).

# How a critical / safety-sensitive critique finding is handled.
#   ask   - surface to the user and pause for a decision (default)
#   block - stop the run and require plan revision
#   auto  - proceed without approval (maximum autonomy)
CRITICAL_HANDLING_VALUES = frozenset({"ask", "block", "auto"})

# What happens when the plan is ambiguous.
#   pause - stop and present a Claude-style options question (default)
#   auto  - proceed with the safe-default assumption
CLARIFICATION_MODE_VALUES = frozenset({"pause", "auto"})

# How pre/post quality findings (shallow plan, placeholder-only content, disconnected modules)
# are enforced.
#   block - reject before/at apply (require revision); default
#   warn  - only warn / degrade to partial (legacy behaviour)
QUALITY_GATE_ENFORCEMENT_VALUES = frozenset({"block", "warn"})

# How requirement coverage gaps affect final status.
#   warn    - surface requirement_coverage_incomplete, but do not degrade status (default)
#   enforce - degrade when coverage has no implementation evidence
REQUIREMENT_COVERAGE_ENFORCEMENT_VALUES = frozenset({"warn", "enforce"})

KEY_CRITICAL_HANDLING = "critical_handling"
KEY_CLARIFICATION_MODE = "clarification_mode"
KEY_QUALITY_GATE_ENFORCEMENT = "quality_gate_enforcement"
KEY_REQUIREMENT_COVERAGE_ENFORCEMENT = "requirement_coverage_enforcement"

DEFAULT_AUTOMATION_FEATURES: dict[str, str] = {
    KEY_CRITICAL_HANDLING: "ask",
    KEY_CLARIFICATION_MODE: "pause",
    KEY_QUALITY_GATE_ENFORCEMENT: "block",
    KEY_REQUIREMENT_COVERAGE_ENFORCEMENT: "warn",
}

_ALLOWED_VALUES: dict[str, frozenset[str]] = {
    KEY_CRITICAL_HANDLING: CRITICAL_HANDLING_VALUES,
    KEY_CLARIFICATION_MODE: CLARIFICATION_MODE_VALUES,
    KEY_QUALITY_GATE_ENFORCEMENT: QUALITY_GATE_ENFORCEMENT_VALUES,
    KEY_REQUIREMENT_COVERAGE_ENFORCEMENT: REQUIREMENT_COVERAGE_ENFORCEMENT_VALUES,
}

_FEATURES_REL_PATH = ("atlas", "automation_features.json")


def get_default_automation_features() -> dict[str, str]:
    return dict(DEFAULT_AUTOMATION_FEATURES)


def normalize_features(incoming: dict | None) -> dict[str, str]:
    """Merge incoming values onto the defaults, dropping unknown keys / invalid values."""
    merged = get_default_automation_features()
    for key, allowed in _ALLOWED_VALUES.items():
        val = str((incoming or {}).get(key) or "").strip().lower()
        if val in allowed:
            merged[key] = val
    return merged


def _features_path(ca_data_root: str | Path) -> Path:
    return Path(ca_data_root).joinpath(*_FEATURES_REL_PATH)


def load_automation_features(ca_data_root: str | Path) -> dict[str, str]:
    """Load the server-side default automation features, falling back to the defaults."""
    path = _features_path(ca_data_root)
    try:
        if path.exists():
            return normalize_features(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        pass
    return get_default_automation_features()


def save_automation_features(ca_data_root: str | Path, features: dict | None) -> dict[str, str]:
    """Persist (normalized) automation features server-side and return what was saved."""
    normalized = normalize_features(features)
    path = _features_path(ca_data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def resolve_features(*, request_features: dict | None = None, ca_data_root: str | Path | None = None) -> dict[str, str]:
    """Resolve effective features: request override > server-side default > built-in default."""
    base = load_automation_features(ca_data_root) if ca_data_root is not None else get_default_automation_features()
    if request_features:
        return normalize_features({**base, **request_features})
    return base
