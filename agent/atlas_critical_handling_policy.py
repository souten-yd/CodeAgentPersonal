"""Profile/preset/envelope-aware default resolution for ``critical_handling``.

``critical_handling`` is the single human-in-the-loop knob for safety-sensitive
findings (``security`` / ``data_loss`` / ``destructive_change`` and safety-sensitive
critique). It has three values:

* ``block`` — stop and require a revised plan.
* ``ask``   — pause for an explicit user decision.
* ``auto``  — proceed without per-action approval (full autonomy).

Historically the apply-time gates defaulted to ``auto`` regardless of the selected
profile, which meant a non-autonomous profile could silently auto-allow
safety-sensitive changes. This module makes the *default* depend on the selected
profile / preset / envelope so that defaults sit on the safe end and only the
explicitly autonomous profiles relax to ``auto``.

An explicit ``critical_handling`` supplied by the caller (request metadata or
``automation_features``) always wins over these defaults.

Note: profile / preset / envelope identifiers are referenced as string literals to
keep this lower-layer ``agent`` module free of an ``app`` import (the established
dependency direction is ``app -> agent``). The literals mirror the canonical
constants in ``app.atlas.automation_safety_profile`` and
``app.atlas.pre_authorized_bounded_dev_envelope``.
"""

from __future__ import annotations

_VALID_HANDLING = {"auto", "ask", "block"}

# Conservative-by-default, keyed by automation safety profile. The autonomous dev
# profile alone is intentionally ``ask`` here: the profile is Level-8 *capable*, but
# without a preset/envelope signal we do not assume the bounded full-automation
# context, so the safe default is to ask. Preset/envelope context escalates to
# ``auto`` below.
CRITICAL_HANDLING_BY_PROFILE: dict[str, str] = {
    "review_only": "block",
    "guarded_single_action": "ask",
    "supervised_bounded_auto": "ask",
    "autonomous_dev_agent": "ask",
}

# Keyed by UI preset id. ``autonomous_custom`` resolves to ``auto`` only because
# selecting that preset *is* the explicit autonomy selection (it still requires
# per-request bounds since it carries no envelope). ``autonomous_bounded_dev`` runs
# inside a pre-authorized envelope, so ``auto`` is its default.
CRITICAL_HANDLING_BY_PRESET: dict[str, str] = {
    "review_only": "block",
    "single_action": "ask",
    "supervised_auto": "ask",
    "autonomous_custom": "auto",
    "autonomous_bounded_dev": "auto",
    # Legacy/internal full-auto preset ids kept for back-compat with existing gates.
    "full_auto": "auto",
    "full_auto_multi_item_v1": "auto",
}

_ENVELOPE_SELF_IMPROVEMENT = "pre_authorized_self_improvement_envelope"


def normalize_critical_handling(value: object) -> str | None:
    """Return a recognised handling value (lower-cased) or ``None`` if unrecognised."""
    text = str(value or "").strip().lower()
    return text if text in _VALID_HANDLING else None


def resolve_default_critical_handling(
    *,
    preset_id: str = "",
    profile: str = "",
    envelope_id: str = "",
    self_improvement: bool = False,
    envelope_active: bool = False,
    strict_gate_approved: bool = False,
    explicit: object | None = None,
) -> str:
    """Resolve the effective ``critical_handling`` value.

    Resolution order:
      1. An explicit recognised value always wins.
      2. Self-improvement envelopes default to ``ask`` (even when the strict gate is
         approved and the envelope is active — explicit confirmation is enforced
         upstream, this layer stays conservative).
      3. Preset default (the preset id is the explicit autonomy selection signal).
      4. Profile default.
      5. Unknown context falls back to ``ask`` (never ``auto``).
    """
    explicit_value = normalize_critical_handling(explicit)
    if explicit_value is not None:
        return explicit_value

    if self_improvement or str(envelope_id or "").strip() == _ENVELOPE_SELF_IMPROVEMENT:
        # Self-improvement is stricter than ordinary dev work: stay on ``ask`` unless an
        # explicit value was provided above. (strict_gate_approved/envelope_active are
        # accepted for signature symmetry and future use.)
        _ = (strict_gate_approved, envelope_active)
        return "ask"

    preset_key = str(preset_id or "").strip().lower()
    if preset_key in CRITICAL_HANDLING_BY_PRESET:
        return CRITICAL_HANDLING_BY_PRESET[preset_key]

    profile_key = str(profile or "").strip().lower()
    if profile_key in CRITICAL_HANDLING_BY_PROFILE:
        return CRITICAL_HANDLING_BY_PROFILE[profile_key]

    return "ask"
