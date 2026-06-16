"""Model-capability-driven file-decomposition policy.

A weak local model cannot reliably read or edit a large file (it stalls and fails to place new
code), so its plans should split an app into small focused files. A large / frontier model handles
big files and long context well, so it can keep more in one file (even a single self-contained
deliverable) and avoid the wiring overhead of many tiny files. This module turns what Forge knows
about a model — its capability scores / known weaknesses, plus a model-name/context-window heuristic
— into concrete sizing knobs (``max_file_lines`` / ``prefer_split`` / ``max_source_files``) that
parameterize the planner's decomposition guidance per model.

Part A wires this from the existing capability profile + a name heuristic. A dedicated
``large_file_editing`` capability dimension (Part B) can later drive ``tier`` from real evidence.

Nothing here mutates source or applies patches; it only produces an advisory directive string that
the planner prompt reflects. Disabled-safe: with no profile and an unknown model it returns the
balanced ``standard`` tier (the same defaults the static prompt already used).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

# Default budget when nothing is known: balanced split into a small number of focused files. Mirrors
# the static guidance in PLAN_GENERATION_PROMPT so behaviour is unchanged when no profile is present.
_DEFAULT_MAX_FILE_LINES = 350
_DEFAULT_MAX_SOURCE_FILES = 5

# Substrings identifying a large / frontier model that handles big files and long context well.
_FRONTIER_HINTS = (
    "opus", "sonnet", "fable", "gpt-4", "gpt-4o", "gpt-5", "o1", "o3", "o4-mini",
    "gemini-1.5", "gemini-2", "gemini-pro", "claude-3", "claude-4", "mistral-large",
    "llama-3.1-405b", "llama-3.3-70b", "deepseek-v3", "deepseek-r1", "qwen2.5-72b",
    "command-r-plus", "grok",
)
# Substrings for small / heavily-quantized local models that need aggressive splitting.
_SMALL_HINTS = (
    "q2_k", "q3_k", "q4_0", "q4_k_s", "1.5b", "-3b", "-7b", "-8b", "mini", "small", "tiny", "phi-3",
)
# Capability dimensions whose weakness most directly predicts trouble editing a large existing file.
_CORE_EDIT_DIMS = frozenset({"contract_preservation", "impact_analysis", "repair_discipline"})

# Dedicated measured dimension (Part B): direct evidence of large-file / long-context editing skill.
# When present it drives the tier directly, ahead of the model-name heuristic.
_LARGE_FILE_DIM = "large_file_editing"
_LARGE_FILE_FRONTIER_AT = 0.7   # >= this measured score -> large files OK
_LARGE_FILE_WEAK_AT = 0.4       # <= this measured score -> split aggressively

# Long-context threshold (tokens) above which a model is treated as comfortable with large files.
_LONG_CONTEXT_TOKENS = 100_000


@dataclass(frozen=True)
class DecompositionPolicy:
    tier: str            # "frontier" | "standard" | "weak"
    max_file_lines: int
    prefer_split: bool
    max_source_files: int
    rationale: str

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "max_file_lines": self.max_file_lines,
            "prefer_split": self.prefer_split,
            "max_source_files": self.max_source_files,
            "rationale": self.rationale,
        }


def _capability_strength(capability_scores: Mapping[str, float] | None) -> float | None:
    vals = [float(v) for v in (capability_scores or {}).values() if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None


def derive_decomposition_policy(
    *,
    capability_scores: Mapping[str, float] | None = None,
    known_weaknesses: Iterable[str] = (),
    model_id: str = "",
    context_window: int = 0,
) -> DecompositionPolicy:
    """Pick a sizing tier from capability evidence and a model-name/context heuristic.

    Frontier: large files OK, minimal splitting. Weak: split aggressively into small files. Standard
    (default, also when nothing is known): balanced split into a few focused files."""
    mid = (model_id or "").lower()
    scores = dict(capability_scores or {})
    strength = _capability_strength(scores)
    weaknesses = {str(w) for w in (known_weaknesses or [])}
    has_core_weakness = bool(weaknesses & _CORE_EDIT_DIMS)

    # Part B: a MEASURED large-file-editing score takes precedence over the name heuristic — it is
    # direct evidence of whether this model can edit a big file without mangling it.
    measured = scores.get(_LARGE_FILE_DIM)
    measured = float(measured) if isinstance(measured, (int, float)) else None
    if measured is not None:
        if measured >= _LARGE_FILE_FRONTIER_AT and not has_core_weakness:
            return DecompositionPolicy(
                tier="frontier", max_file_lines=1200, prefer_split=False, max_source_files=3,
                rationale=f"measured large_file_editing={measured:.2f}: handles large files reliably, minimal splitting",
            )
        if measured <= _LARGE_FILE_WEAK_AT or has_core_weakness:
            return DecompositionPolicy(
                tier="weak", max_file_lines=200, prefer_split=True, max_source_files=7,
                rationale=f"measured large_file_editing={measured:.2f}: weak at large files, split aggressively",
            )
        return DecompositionPolicy(
            tier="standard", max_file_lines=_DEFAULT_MAX_FILE_LINES, prefer_split=True,
            max_source_files=_DEFAULT_MAX_SOURCE_FILES,
            rationale=f"measured large_file_editing={measured:.2f}: middling, balanced split",
        )

    frontier = (
        any(h in mid for h in _FRONTIER_HINTS)
        or (context_window and context_window >= _LONG_CONTEXT_TOKENS)
        or (strength is not None and strength >= 0.8 and not has_core_weakness)
    )
    weak = (
        any(h in mid for h in _SMALL_HINTS)
        or has_core_weakness
        or (strength is not None and strength <= 0.45)
    )

    # A clear frontier signal wins over an incidental small-name match (e.g. a name containing
    # "small" but with strong evidence); a core capability weakness keeps it out of the frontier tier.
    if frontier and not has_core_weakness and not (weak and strength is not None and strength <= 0.45):
        return DecompositionPolicy(
            tier="frontier", max_file_lines=1200, prefer_split=False, max_source_files=3,
            rationale="capable/long-context model: large files OK, minimal splitting (a single self-contained file is acceptable)",
        )
    if weak:
        return DecompositionPolicy(
            tier="weak", max_file_lines=200, prefer_split=True, max_source_files=7,
            rationale="small/weak model: split aggressively into small files so each step stays within reach",
        )
    return DecompositionPolicy(
        tier="standard", max_file_lines=_DEFAULT_MAX_FILE_LINES, prefer_split=True,
        max_source_files=_DEFAULT_MAX_SOURCE_FILES,
        rationale="default model tier: balanced split into a small number of focused files",
    )


def render_decomposition_directive(policy: DecompositionPolicy) -> str:
    """Render the policy as an advisory block the planner prompt reflects. Authoritative over the
    static default sizing, but still subordinate to an explicit single-file request in the goal."""
    if policy.prefer_split:
        split_line = ("Split the app into focused files (index.html + external js/*.js via <script src> "
                      "and css/*.css via <link href>); keep each file within the size budget.")
    else:
        split_line = ("This model handles large files well — a single self-contained file is acceptable; "
                      "split only if a file would clearly exceed the size budget.")
    return (
        "=== DECOMPOSITION BUDGET (model-specific; overrides the default sizing) ===\n"
        f"- model_tier: {policy.tier} ({policy.rationale})\n"
        f"- max_file_lines: ~{policy.max_file_lines} lines per code file before splitting a concern out\n"
        f"- target_source_file_count: at most ~{policy.max_source_files} source files; prefer the fewest that keep each focused, scaled to real complexity\n"
        f"- {split_line}\n"
        "- An explicit single-file / self-contained request in the user's goal still overrides this."
    )
