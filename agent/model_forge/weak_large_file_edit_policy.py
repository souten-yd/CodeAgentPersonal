"""WeakLargeFileEditPolicy — stop a weak model from re-emitting a whole large file.

Live failure (Qwen local, 22 KB main.js): asked to MODIFY the file, the weak model ignored the
edits-first guidance and tried to re-output the ENTIRE file as a JSON ``proposed_content`` string,
ran to ~5 000 tokens and produced malformed/truncated output (``llm_no_patch_content_generated``) —
even the minimal old/new extraction failed the same way. Input slicing minimises what the model
READS, but cannot stop it emitting the whole file on OUTPUT.

The fix is to remove that freedom on output for the weak/standard tier when editing a large EXISTING
file: cap the output budget small so the model physically cannot run away, and demand an edits-only
response. This is the deterministic-control direction (take freedom away from the weak model) rather
than "make the model try harder". Two cases are deliberately EXEMPT:
  - frontier tier (capable of a coherent whole-file rewrite), and
  - CREATE (the file does not yet exist) — there is nothing to edit, the model must emit full content
    (this is why create-mode succeeded where modify-mode broke).
"""
from __future__ import annotations

# An existing file at/above either threshold is "large" — too big for the weak model to safely
# re-emit, so it must be patched with surgical edits.
LARGE_FILE_LINES = 120
LARGE_FILE_CHARS = 8000
# Output budget for the forced edits-only mode: enough for a few small old/new edits, far too small
# to re-emit a large file (so a runaway whole-file output is truncated early instead of after 5 000+
# tokens). Still capped further by the adapter's n_ctx budget.
EDIT_ONLY_MAX_OUTPUT_TOKENS = 1800

# Prior failure signals that mean "the model already failed to return usable content once" — after
# these, force edit-only even for a not-large file (the freedom clearly did not help).
_NO_CONTENT_SIGNALS = (
    "llm_no_patch_content_generated",
    "plan_item_patch_content_missing",
    "content_missing",
    "focused_extraction_recovered",
)


def weak_large_file_edit_policy(
    *,
    size_tier: str,
    file_chars: int = 0,
    file_lines: int = 0,
    file_exists: bool = True,
    prior_error: str = "",
    large_lines: int = LARGE_FILE_LINES,
    large_chars: int = LARGE_FILE_CHARS,
) -> dict:
    """Decide whether to force edits-only output (and a small token cap) for this generation.

    Returns {"edit_only": bool, "max_output_tokens": int | None, "reason": str}. ``edit_only`` True
    means: instruct the model to return ONLY a small edits array (old_string/new_string), forbid a
    full-file ``proposed_content``, and cap the output budget to ``max_output_tokens``.
    """
    tier = str(size_tier or "standard").strip().lower()
    none = {"edit_only": False, "max_output_tokens": None, "reason": ""}
    if tier == "frontier":
        return none
    if not file_exists:
        return none  # CREATE: there is nothing to edit; full content is required
    large = (file_lines or 0) >= large_lines or (file_chars or 0) >= large_chars
    failed_before = any(sig in str(prior_error or "") for sig in _NO_CONTENT_SIGNALS)
    if large or failed_before:
        reason = "large_existing_file" if large else "prior_no_content"
        return {"edit_only": True, "max_output_tokens": EDIT_ONLY_MAX_OUTPUT_TOKENS, "reason": reason}
    return none


def edit_only_prompt_directive(canvas_safe: bool = True) -> str:
    """The hard output-format constraint injected when edit_only is active. Offers an Aider-style
    SEARCH/REPLACE form because a weak model writes that (mostly verbatim code) more reliably than a
    nested JSON edits array; the service parses either form into edits."""
    return (
        "OUTPUT FORMAT — EDITS ONLY (this is a large existing file; do NOT rewrite the whole file).\n"
        "Return 1-3 SMALL surgical edits, in EITHER form:\n"
        "(a) a JSON \"edits\" array of {\"old_string\" (copied VERBATIM from the current file content), "
        "\"new_string\"}; OR\n"
        "(b) put Aider-style SEARCH/REPLACE blocks in the \"proposed_content\" field, each exactly:\n"
        "<<<<<<< SEARCH\n<the exact current lines to find>\n=======\n<the replacement lines>\n>>>>>>> REPLACE\n"
        "Do NOT return the whole file or a full-function rewrite over ~40 lines. Change ONLY what the "
        "task requires and keep every other line untouched. If you cannot express it as a few small "
        "edits, return the SINGLE smallest edit that makes progress."
    )
