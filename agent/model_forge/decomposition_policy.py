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

import re
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
# MoE active-parameter notation (e.g. "35B-A3B" = 35B total, 3B ACTIVE per token). Generation
# quality tracks the ACTIVE parameter count, not the total, so a low-active MoE must be treated as
# weak for decomposition even though its total size looks large. Captures the active count in "AxB".
_MOE_ACTIVE_RE = re.compile(r"(?:^|[-_ ])a(\d+(?:\.\d+)?)b(?:[-_ .]|$)")
# At/under this many ACTIVE billions, split aggressively (small files) like any weak model. 4.0
# covers common low-active MoEs (A1.5B/A2B/A3B) that empirically fail to emit a large file at once.
_MOE_WEAK_ACTIVE_B = 4.0


def _moe_active_billions(model_id: str) -> float | None:
    """Return the MoE ACTIVE parameter count in billions parsed from the model id, or None."""
    m = _MOE_ACTIVE_RE.search((model_id or "").lower())
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None
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


# Canonical sizing per tier, referenced by both the heuristic branches (via the explicit returns
# below, which mirror these) and the manual tier override.
_TIER_SPECS = {
    "frontier": {"max_file_lines": 1200, "prefer_split": False, "max_source_files": 3},
    "standard": {"max_file_lines": _DEFAULT_MAX_FILE_LINES, "prefer_split": True, "max_source_files": _DEFAULT_MAX_SOURCE_FILES},
    "weak": {"max_file_lines": 200, "prefer_split": True, "max_source_files": 7},
}
# Accepted values for the manual override setting. "auto" (and "", unknown) keep the heuristic.
VALID_TIER_OVERRIDES = frozenset(_TIER_SPECS)


def policy_for_tier(tier: str, rationale: str) -> DecompositionPolicy:
    spec = _TIER_SPECS[tier]
    return DecompositionPolicy(tier=tier, rationale=rationale, **spec)


def derive_decomposition_policy(
    *,
    capability_scores: Mapping[str, float] | None = None,
    known_weaknesses: Iterable[str] = (),
    model_id: str = "",
    context_window: int = 0,
    tier_override: str = "",
) -> DecompositionPolicy:
    """Pick a sizing tier from capability evidence and a model-name/context heuristic.

    Frontier: large files OK, minimal splitting. Weak: split aggressively into small files. Standard
    (default, also when nothing is known): balanced split into a few focused files.

    ``tier_override`` (from the ``ATLAS_DECOMPOSITION_TIER`` setting) forces a tier when splitting is
    not wanted or should be forced: ``frontier`` disables aggressive splitting (a single
    self-contained file is fine), ``weak`` always splits small, ``standard`` uses the balanced
    default. ``auto`` / empty / unknown keep the automatic model-based heuristic below."""
    override = (tier_override or "").strip().lower()
    if override in VALID_TIER_OVERRIDES:
        return policy_for_tier(override, f"tier forced by setting ATLAS_DECOMPOSITION_TIER={override}")

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

    # Low-active MoE (e.g. "35B-A3B"): generation quality tracks ACTIVE params, so a big-looking
    # total must not buy the frontier tier. The generic capability STRENGTH average must NOT cancel
    # this: those dims (contract preservation / structured-output / patch-protocol fidelity) measure
    # EDITING fidelity, not the ability to emit a large file from scratch — an A3B can score ~1.0 on
    # them and still return empty on a large generation. Only a DEDICATED large_file_editing
    # measurement overrides it, and that is already handled by the early `measured` return above.
    active_b = _moe_active_billions(mid)
    low_active_moe = active_b is not None and active_b <= _MOE_WEAK_ACTIVE_B

    frontier = (
        any(h in mid for h in _FRONTIER_HINTS)
        or (context_window and context_window >= _LONG_CONTEXT_TOKENS)
        or (strength is not None and strength >= 0.8 and not has_core_weakness)
    )
    weak = (
        any(h in mid for h in _SMALL_HINTS)
        or has_core_weakness
        or low_active_moe
        or (strength is not None and strength <= 0.45)
    )

    # A clear frontier signal wins over an incidental small-name match (e.g. a name containing
    # "small" but with strong evidence); a core capability weakness or a low-active MoE keeps it out
    # of the frontier tier.
    if frontier and not has_core_weakness and not low_active_moe and not (weak and strength is not None and strength <= 0.45):
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
    static default sizing. For the weak tier the split is a HARD requirement (the model cannot emit
    a large single file), so a single-file request is downgraded to a warning there; for
    standard/frontier an explicit single-file request in the goal still wins."""
    if policy.tier == "weak":
        min_files = max(3, min(policy.max_source_files, 4))
        split_line = (
            "This model CANNOT reliably emit a large or complex single file in one generation (it "
            "returns empty / incomplete output and the step fails). You MUST split the app into "
            f"multiple small files — index.html plus several external js/*.js via <script src> (and "
            f"css/*.css via <link href>) — each kept UNDER ~{policy.max_file_lines} lines, roughly "
            f"{min_files}-{policy.max_source_files} focused source files that each implement one concern "
            "(e.g. input, rendering, weapons, enemies, game-state). Do NOT place the whole app in one "
            "file: a single-file / self-contained deliverable is NOT acceptable for this model even if "
            "the user's goal suggests one — split it and wire the parts together."
        )
        override_line = (
            "- A single-file request in the goal is downgraded to a warning here: this model cannot "
            "deliver it, so split anyway and note the deviation."
        )
    else:
        if policy.prefer_split:
            split_line = ("Split the app into focused files (index.html + external js/*.js via <script src> "
                          "and css/*.css via <link href>); keep each file within the size budget.")
        else:
            split_line = ("This model handles large files well — a single self-contained file is acceptable; "
                          "split only if a file would clearly exceed the size budget.")
        override_line = "- An explicit single-file / self-contained request in the user's goal still overrides this."
    return (
        "=== DECOMPOSITION BUDGET (model-specific; overrides the default sizing) ===\n"
        f"- model_tier: {policy.tier} ({policy.rationale})\n"
        f"- max_file_lines: ~{policy.max_file_lines} lines per code file before splitting a concern out\n"
        f"- target_source_file_count: at most ~{policy.max_source_files} source files; prefer the fewest that keep each focused, scaled to real complexity\n"
        f"- {split_line}\n"
        f"{override_line}"
    )


def resolve_size_tier(
    *,
    data_root: str,
    metadata: Mapping[str, object] | None = None,
    env: Mapping[str, str] | None = None,
    model_id: str = "",
    provider_id: str = "",
) -> str:
    """Resolve the ``frontier|standard|weak`` sizing tier for the active model — the shared
    capability lookup behind both plan-time decomposition and patch-time output shaping.

    Resolves the Forge-evaluated identity when the caller pinned none (honouring the opt-in live
    local probe), loads its capability profile, and derives the tier. This is the single signal that
    lets weak-model output restrictions be applied while a frontier model skips them. Best-effort and
    disabled-safe: any problem yields the balanced ``standard`` tier (legacy neutral behaviour)."""
    import os
    from pathlib import Path

    try:
        env = env if env is not None else os.environ
        md = metadata or {}
        mid = str(model_id or md.get("model_id") or env.get("FORGE_LOCAL_MODEL") or "").strip()
        pid = str(provider_id or md.get("provider_id") or "local").strip() or "local"
        if not mid:
            try:
                from agent.model_forge.forge_service import ForgeService

                probe = str(env.get("ATLAS_FORGE_PROBE_LOCAL", "")).strip().lower() in {"1", "on", "true", "yes"}
                resolved = ForgeService(data_root, env=dict(env)).resolve_active_codegen_model(probe_live=probe)
                mid = str(resolved.get("model_id") or "").strip()
                pid = str(resolved.get("provider_id") or pid).strip() or pid
            except Exception:  # noqa: BLE001 - resolution is advisory.
                pass
        capability_scores: dict = {}
        known_weaknesses: tuple = ()
        if mid:
            try:
                from agent.model_forge.capability_scoring import load_capability_profile
                from agent.model_forge.profile_store import ProfileStore

                store = ProfileStore(Path(data_root) / "model_forge" / "profiles")
                cap = load_capability_profile(store, pid, mid)
                capability_scores = dict(getattr(cap, "capability_scores", {}) or {})
                known_weaknesses = tuple(getattr(cap, "known_weaknesses", ()) or ())
            except Exception:  # noqa: BLE001 - profile is advisory.
                pass
        return derive_decomposition_policy(
            capability_scores=capability_scores, known_weaknesses=known_weaknesses, model_id=mid,
        ).tier
    except Exception:  # noqa: BLE001 - never raise from an advisory tier lookup.
        return "standard"
