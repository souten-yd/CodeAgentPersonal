"""Twin assistance levels used by Forge evaluation and routing."""
from __future__ import annotations

from enum import StrEnum


class TwinAssistMode(StrEnum):
    NONE = "none"
    POLICY_ONLY = "policy_only"
    CONSTRAINTS_AND_REFS = "constraints_and_refs"
    IMPACT_AND_SAFE_EDIT = "impact_and_safe_edit"
    STRICT_TWIN_BRIEF = "strict_twin_brief"
    TWIN_LOCALIZED_SLOT = "twin_localized_slot"
    TWIN_DETERMINISTIC_ANCHOR = "twin_deterministic_anchor"
