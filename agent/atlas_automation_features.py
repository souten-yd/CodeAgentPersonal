from __future__ import annotations

import json
from pathlib import Path

from agent.atlas_capability_preference_schema import (
    apply_preferences,
    get_default_preferences,
    normalize_ui_preferences,
)
# Canonical preset id source of truth. ``selected_preset_id`` is only a stored
# Claude-style UI selection; it never starts a loop, applies, merges, or pushes
# on its own (those stay gated by a separately-persisted envelope + explicit
# command in agent/atlas_automation_profile_resolver.py). Importing PRESETS here
# lets us fail closed on unknown ids instead of returning a 500.
from agent.atlas_automation_profile_resolver import PRESETS as KNOWN_PRESET_IDS

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
KEY_SELECTED_PRESET_ID = "selected_preset_id"
KEY_CAPABILITY_PREFERENCES = "capability_preferences"
# Claude-style default preset that preserves the existing full-automatic code
# generation configuration. It is a known preset in the canonical PRESETS source
# of truth and matches the UI fallback in web/js/atlas_claude_panel.js. It is not
# a Vue / Atlas Next preset.
DEFAULT_SELECTED_PRESET_ID = "autonomous_bounded_dev"
# Fail-closed guard: if the canonical catalogue ever drops this id, fall back to
# whatever it considers safe rather than serving a phantom preset.
if DEFAULT_SELECTED_PRESET_ID not in KNOWN_PRESET_IDS:  # pragma: no cover - defensive
    DEFAULT_SELECTED_PRESET_ID = "review_only"

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


def normalize_selected_preset_id(value: object) -> str:
    """Return a known preset id, failing closed to the default.

    Empty / None / unknown ids resolve to ``DEFAULT_SELECTED_PRESET_ID`` so the
    automation-features API can never raise on a missing or malformed selection.
    """
    text = str(value or "").strip()
    if text in KNOWN_PRESET_IDS:
        return text
    return DEFAULT_SELECTED_PRESET_ID


def normalize_capability_preferences(incoming: dict | None) -> dict[str, bool]:
    return apply_preferences(get_default_preferences(), normalize_ui_preferences(incoming or {}))


def _features_path(ca_data_root: str | Path) -> Path:
    return Path(ca_data_root).joinpath(*_FEATURES_REL_PATH)


def load_automation_features(ca_data_root: str | Path) -> dict[str, str]:
    """Load the server-side default automation features, falling back to the defaults."""
    path = _features_path(ca_data_root)
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("features"), dict):
                payload = payload.get("features")
            return normalize_features(payload)
    except Exception:
        pass
    return get_default_automation_features()


def save_automation_features(ca_data_root: str | Path, features: dict | None) -> dict[str, str]:
    """Persist (normalized) automation features server-side and return what was saved."""
    state = load_full_automation_state(ca_data_root)
    saved = save_full_automation_state(
        ca_data_root,
        features=features,
        selected_preset_id=state["selected_preset_id"],
        capability_preferences=state["capability_preferences"],
    )
    return saved["features"]


def load_full_automation_state(ca_data_root: str | Path) -> dict:
    path = _features_path(ca_data_root)
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {}
            features_payload = payload.get("features") if isinstance(payload.get("features"), dict) else payload
            return {
                "features": normalize_features(features_payload),
                "selected_preset_id": normalize_selected_preset_id(payload.get("selected_preset_id")),
                "capability_preferences": normalize_capability_preferences(payload.get("capability_preferences") if isinstance(payload.get("capability_preferences"), dict) else {}),
            }
    except Exception:
        pass
    return {
        "features": get_default_automation_features(),
        "selected_preset_id": DEFAULT_SELECTED_PRESET_ID,
        "capability_preferences": get_default_preferences(),
    }


def save_full_automation_state(
    ca_data_root: str | Path,
    *,
    features: dict | None = None,
    selected_preset_id: str | None = None,
    capability_preferences: dict | None = None,
) -> dict:
    current = load_full_automation_state(ca_data_root)
    state = {
        "features": normalize_features(features if features is not None else current["features"]),
        "selected_preset_id": normalize_selected_preset_id(selected_preset_id if selected_preset_id is not None else current["selected_preset_id"]),
        "capability_preferences": normalize_capability_preferences(capability_preferences if capability_preferences is not None else current["capability_preferences"]),
    }
    path = _features_path(ca_data_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def resolve_features(*, request_features: dict | None = None, ca_data_root: str | Path | None = None) -> dict[str, str]:
    """Resolve effective features: request override > server-side default > built-in default."""
    base = load_automation_features(ca_data_root) if ca_data_root is not None else get_default_automation_features()
    if request_features:
        return normalize_features({**base, **request_features})
    return base
