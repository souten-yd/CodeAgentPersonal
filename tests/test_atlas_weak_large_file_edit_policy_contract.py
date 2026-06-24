"""Contract tests for WeakLargeFileEditPolicy.

The weak local model, asked to MODIFY a large existing file, re-emits the whole file as
proposed_content, runs away (~5000 tokens) and breaks. The policy forces edits-only output + a small
token cap for weak/standard tiers editing a large EXISTING file, while exempting frontier and CREATE.
"""
from __future__ import annotations

from agent.model_forge.weak_large_file_edit_policy import (
    EDIT_ONLY_MAX_OUTPUT_TOKENS,
    edit_only_prompt_directive,
    weak_large_file_edit_policy,
)
from agent.atlas_patch_proposal_service import AtlasPatchProposalService


def test_weak_modifying_large_existing_file_forces_edit_only():
    v = weak_large_file_edit_policy(size_tier="weak", file_chars=22000, file_lines=600, file_exists=True)
    assert v["edit_only"] is True
    assert v["max_output_tokens"] == EDIT_ONLY_MAX_OUTPUT_TOKENS
    assert v["reason"] == "large_existing_file"


def test_standard_tier_also_constrained_on_large_file():
    v = weak_large_file_edit_policy(size_tier="standard", file_chars=0, file_lines=300, file_exists=True)
    assert v["edit_only"] is True


def test_frontier_tier_is_exempt():
    v = weak_large_file_edit_policy(size_tier="frontier", file_chars=99000, file_lines=2000, file_exists=True)
    assert v["edit_only"] is False
    assert v["max_output_tokens"] is None


def test_create_mode_is_exempt_even_for_weak():
    # the file does not exist yet -> there is nothing to edit, full content is required (this is why
    # create-mode succeeded where modify-mode broke)
    v = weak_large_file_edit_policy(size_tier="weak", file_chars=0, file_lines=0, file_exists=False)
    assert v["edit_only"] is False


def test_small_existing_file_not_constrained():
    v = weak_large_file_edit_policy(size_tier="weak", file_chars=400, file_lines=20, file_exists=True)
    assert v["edit_only"] is False


def test_prior_no_content_failure_forces_edit_only_even_if_not_large():
    # after the model already failed to return content once, take the freedom away regardless of size
    v = weak_large_file_edit_policy(
        size_tier="weak", file_chars=500, file_lines=30, file_exists=True,
        prior_error="llm_no_patch_content_generated",
    )
    assert v["edit_only"] is True
    assert v["reason"] == "prior_no_content"


def test_threshold_is_either_lines_or_chars():
    assert weak_large_file_edit_policy(size_tier="weak", file_lines=120, file_exists=True)["edit_only"] is True
    assert weak_large_file_edit_policy(size_tier="weak", file_chars=8000, file_exists=True)["edit_only"] is True
    assert weak_large_file_edit_policy(size_tier="weak", file_lines=119, file_chars=7999, file_exists=True)["edit_only"] is False


def test_directive_forbids_full_file_output():
    d = edit_only_prompt_directive()
    assert "EDITS ONLY" in d
    assert "old_string" in d and "new_string" in d
    assert "proposed_content" in d  # names it to forbid it


def test_service_policy_reads_per_file_split_current_content():
    large = "x = 1\n" * 400
    svc = AtlasPatchProposalService(journal=None, storage=None)
    payload = {
        "size_tier": "weak",
        "current_target_contents": {},
        "item": {
            "target_files": ["app.js"],
            "target_file_exists": True,
            "current_file_content": large,
            "current_file_original_chars": len(large),
            "current_file_original_lines": large.count("\n") + 1,
        },
    }

    verdict = svc._weak_large_file_edit_policy(payload)

    assert verdict["edit_only"] is True
    assert verdict["max_output_tokens"] == EDIT_ONLY_MAX_OUTPUT_TOKENS
    assert verdict["reason"] == "large_existing_file"


def test_service_policy_treats_sliced_existing_content_as_edit_only():
    svc = AtlasPatchProposalService(journal=None, storage=None)
    payload = {
        "size_tier": "weak",
        "current_target_contents": {},
        "item": {
            "target_files": ["app.js"],
            "target_file_exists": True,
            "current_file_content": "function target() {}\n",
            "current_file_content_sliced": True,
            "current_file_original_chars": 24000,
            "current_file_original_lines": 700,
        },
    }

    verdict = svc._weak_large_file_edit_policy(payload)

    assert verdict["edit_only"] is True
    assert verdict["reason"] == "sliced_existing_file"
