from __future__ import annotations

# Capability preference keys stored in workflow/project/session state
CAP_COMMAND_EXECUTION = "command_execution_requested"
CAP_BROWSER_AUTOMATION = "browser_automation_requested"
CAP_PLAYWRIGHT_VERIFICATION = "playwright_visual_verification_requested"
CAP_WEB_EVIDENCE = "web_evidence_gathering_requested"
CAP_SANDBOXED_INSTALL = "sandboxed_package_installation_requested"

# All capability preference keys (in display order)
ALL_CAPABILITY_KEYS: list[str] = [
    CAP_COMMAND_EXECUTION,
    CAP_BROWSER_AUTOMATION,
    CAP_PLAYWRIGHT_VERIFICATION,
    CAP_WEB_EVIDENCE,
    CAP_SANDBOXED_INSTALL,
]

# Default initial state: all checked (user expresses intent)
DEFAULT_CAPABILITY_PREFERENCES: dict[str, bool] = {key: True for key in ALL_CAPABILITY_KEYS}

# Runtime block reasons per capability (backend policy enforcement)
# These are checked against backend policy, NOT against UI preference.
RUNTIME_BLOCK_REASONS: dict[str, str] = {
    CAP_COMMAND_EXECUTION: "blocked: runtime level_0_manual_only",
    CAP_BROWSER_AUTOMATION: "blocked: arbitrary browser automation not enabled",
    CAP_PLAYWRIGHT_VERIFICATION: "available only in test/CI harness if Playwright exists",
    CAP_WEB_EVIDENCE: "planner/evidence mode only",
    CAP_SANDBOXED_INSTALL: "blocked until sandbox policy is enabled",
}

# Human-readable labels for UI display
CAPABILITY_LABELS: dict[str, str] = {
    CAP_COMMAND_EXECUTION: "Command execution requested",
    CAP_BROWSER_AUTOMATION: "Browser automation requested",
    CAP_PLAYWRIGHT_VERIFICATION: "Playwright visual verification requested",
    CAP_WEB_EVIDENCE: "Web evidence gathering requested",
    CAP_SANDBOXED_INSTALL: "Sandboxed package installation requested",
}


def get_default_preferences() -> dict[str, bool]:
    """Return a copy of the default capability preferences (all checked)."""
    return dict(DEFAULT_CAPABILITY_PREFERENCES)


def apply_preferences(existing: dict, updates: dict) -> dict:
    """Merge preference updates into existing preferences, validating known keys."""
    merged = dict(existing)
    for key, val in updates.items():
        if key in ALL_CAPABILITY_KEYS:
            merged[key] = bool(val)
    return merged


def build_feature_summary(preferences: dict[str, bool]) -> list[dict]:
    """Build a list of feature summary entries for final summary display.

    Each entry:
        {key, label, requested, runtime_status, blocked}
    """
    summary: list[dict] = []
    for key in ALL_CAPABILITY_KEYS:
        requested = bool(preferences.get(key, False))
        block_reason = RUNTIME_BLOCK_REASONS.get(key, "")
        # playwright verification is the only one that may be available
        blocked = key != CAP_PLAYWRIGHT_VERIFICATION or not _playwright_available()
        if key == CAP_WEB_EVIDENCE:
            blocked = False  # evidence mode is allowed in planner
        summary.append({
            "key": key,
            "label": CAPABILITY_LABELS.get(key, key),
            "requested": requested,
            "runtime_status": block_reason,
            "blocked": blocked,
        })
    return summary


def _playwright_available() -> bool:
    try:
        import playwright  # type: ignore[import]  # noqa: F401
        return True
    except ImportError:
        return False
