"""Compile bounded Twin metadata for each evaluation assist mode."""
from __future__ import annotations

import json

from agent.model_forge.twin_assist_contracts import TwinAssistCase
from agent.model_forge.twin_assist_taxonomy import TwinAssistMode


def compile_assist_metadata(
    *, assist_mode: TwinAssistMode, evidence: dict, case: TwinAssistCase,
) -> dict:
    if assist_mode == TwinAssistMode.NONE:
        return {}
    payload: dict[str, object] = {
        "assist_mode": assist_mode.value,
        "hard_constraints": ["Proposal only", "Do not apply files", "Preserve Safe Apply and Verification"],
    }
    if assist_mode != TwinAssistMode.POLICY_ONLY:
        payload.update({
            "allowed_refs": [*case.target_files, *case.required_refs],
            "forbidden_refs": case.forbidden_refs,
            "expected_symbols": case.expected_symbols,
            "required_tests": case.expected_tests,
        })
    if assist_mode in {
        TwinAssistMode.IMPACT_AND_SAFE_EDIT,
        TwinAssistMode.STRICT_TWIN_BRIEF,
        TwinAssistMode.TWIN_LOCALIZED_SLOT,
        TwinAssistMode.TWIN_DETERMINISTIC_ANCHOR,
    }:
        payload["safe_edit_briefing"] = evidence.get("safe_edit_briefing", {})
        payload["impact"] = evidence.get("impact", {})
    if assist_mode in {
        TwinAssistMode.STRICT_TWIN_BRIEF,
        TwinAssistMode.TWIN_LOCALIZED_SLOT,
        TwinAssistMode.TWIN_DETERMINISTIC_ANCHOR,
    }:
        payload["strict_output"] = "Return a bounded Atlas proposal for the listed targets only."
    if assist_mode == TwinAssistMode.TWIN_LOCALIZED_SLOT:
        payload["slot"] = evidence.get("slot", {})
        payload["anchor_owned_by_atlas"] = True
    if assist_mode == TwinAssistMode.TWIN_DETERMINISTIC_ANCHOR:
        payload["deterministic_anchor"] = evidence.get("deterministic_anchor", {})
        payload["anchor_owned_by_atlas"] = True
    instruction = "Twin Assist evaluation control (advisory; Proposal/Safe Apply authority unchanged):\n" + json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
    )
    return {
        "twin_generation_hints": {
            "assist_mode": assist_mode.value,
            "twin_instruction": instruction,
            "evaluation_only": True,
        }
    }
