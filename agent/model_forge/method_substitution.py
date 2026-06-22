"""Method substitution: when a capability weakness CANNOT be fixed by more Twin injection, propose
a different generation METHOD instead.

Some weaknesses respond to guidance (inject more Twin context and the model complies). Others are
structural — e.g. a model that cannot emit a clean edit-intent list will not improve no matter how
much guidance you add. For those, the right lever is not "more injection" but "a method where the
hard part is owned by Atlas, not the model" (deterministic text patch, Twin-localized slot fill,
anchored block). This module names that alternative per weak dimension.

This mirrors what ExecutionPolicy already does internally (``avoid_method_variants`` +
``CapabilityRescuePlanner``); it just surfaces it as an explicit, auditable recommendation so the
benchmark/UI can say "edit_intent is weak -> use deterministic_text_patch".
"""
from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass

from agent.model_forge.method_taxonomy import MethodVariant

WEAKNESS_THRESHOLD = 0.55

# The capability dimension(s) a method LEANS ON model-side. Empty = the platform owns the hard part
# (deterministic compile / Twin-owned slot/anchor), so the model bears little risk -> a safe baseline
# fitness. This is what makes substitute selection measurement-driven instead of a static order:
# among the candidate substitutes we pick the one the model's real benchmark scores say it can do.
_METHOD_REQUIRED_DIMENSIONS: dict[MethodVariant, tuple[str, ...]] = {
    MethodVariant.DETERMINISTIC_TEXT_PATCH: (),          # platform compiles -> safe
    MethodVariant.DETERMINISTIC_AST_PATCH: (),
    MethodVariant.TWIN_LOCALIZED_SLOT_PATCH: (),         # Atlas owns the anchor; model fills the slot
    MethodVariant.TWIN_SLOT_FILL_ONLY: (),
    MethodVariant.TWIN_DETERMINISTIC_ANCHOR_PATCH: (),
    MethodVariant.ANCHORED_EDIT_BLOCK: ("anchor_selection_quality",),
    MethodVariant.EDIT_INTENT_LIST: ("edit_intent_quality",),
    MethodVariant.STRUCTURED_PATCH_JSON: ("structured_output_fidelity",),
    MethodVariant.PATCH_DSL_JSON: ("patch_protocol_fidelity",),
    MethodVariant.UNIFIED_DIFF: ("patch_protocol_fidelity",),
}
# Platform-owned methods get this floor: high enough to be the safe default, but a measured model
# STRENGTH (a required dim scoring above it) will out-rank it so we leverage that strength.
_PLATFORM_OWNED_FITNESS = 0.8


def method_fitness(method: MethodVariant, capability_scores: Mapping[str, float] | None) -> float:
    """How well a model can be expected to drive ``method``, from its measured capability scores.
    Platform-owned methods return a safe baseline; model-dependent methods return the WEAKEST of
    their required dimensions (a chain is only as strong as its weakest required skill)."""
    req = _METHOD_REQUIRED_DIMENSIONS.get(method, ())
    if not req:
        return _PLATFORM_OWNED_FITNESS
    scores = capability_scores or {}
    return min(float(scores.get(dim, 0.5)) for dim in req)

# dimension -> (avoid these methods, prefer these instead, why). Prefer-order is best-first.
_SUBSTITUTION_MAP: dict[str, tuple[list[MethodVariant], list[MethodVariant], str]] = {
    "edit_intent_quality": (
        [MethodVariant.EDIT_INTENT_LIST],
        [MethodVariant.DETERMINISTIC_TEXT_PATCH, MethodVariant.TWIN_LOCALIZED_SLOT_PATCH,
         MethodVariant.ANCHORED_EDIT_BLOCK],
        "編集意図リストを正しく出せない → 構造を外部(Atlas)が持つ決定論テキスト/Twinスロット/アンカーへ",
    ),
    "structured_output_fidelity": (
        [MethodVariant.STRUCTURED_PATCH_JSON, MethodVariant.PATCH_DSL_JSON],
        [MethodVariant.DETERMINISTIC_TEXT_PATCH, MethodVariant.EDIT_INTENT_LIST],
        "構造化JSONが崩れる → 決定論テキスト、または素の編集意図へ",
    ),
    "patch_protocol_fidelity": (
        [MethodVariant.PATCH_DSL_JSON, MethodVariant.UNIFIED_DIFF],
        [MethodVariant.DETERMINISTIC_TEXT_PATCH, MethodVariant.ANCHORED_EDIT_BLOCK],
        "パッチ書式の整合が弱い → 決定論テキスト/アンカーで書式生成をモデルに任せない",
    ),
    "anchor_selection_quality": (
        [MethodVariant.ANCHORED_EDIT_BLOCK],
        [MethodVariant.TWIN_LOCALIZED_SLOT_PATCH, MethodVariant.TWIN_SLOT_FILL_ONLY],
        "アンカー選定が不安定 → Atlasがアンカーを保持するスロット方式へ",
    ),
    "large_file_editing": (
        [MethodVariant.STRUCTURED_PATCH_JSON],
        [MethodVariant.TWIN_LOCALIZED_SLOT_PATCH, MethodVariant.ANCHORED_EDIT_BLOCK],
        "大ファイルの全書換が苦手 → 局所スロット/アンカーで最小編集に絞る",
    ),
}


@dataclass(frozen=True)
class MethodSubstitution:
    dimension: str
    avoid: tuple[str, ...]
    prefer: tuple[str, ...]            # best-first; measurement-driven when scores were supplied
    why: str
    basis: str = "static"             # "measured" once ranked by capability scores
    fitness: tuple[tuple[str, float], ...] = ()  # (method, fitness) for transparency

    def as_dict(self) -> dict:
        return {"dimension": self.dimension, "avoid": list(self.avoid),
                "prefer": list(self.prefer), "why": self.why, "basis": self.basis,
                "fitness": {m: round(f, 3) for m, f in self.fitness}}


def recommend_method_substitutions(
    weak_dimensions: Iterable[str],
    capability_scores: Mapping[str, float] | None = None,
) -> list[MethodSubstitution]:
    """For each weak dimension with a structural alternative, return the method to avoid and the
    methods to prefer. When ``capability_scores`` is given the prefer-order is **measurement-driven**:
    candidates are ranked by ``method_fitness`` (the model's measured competence at each method), so a
    real strength is leveraged and a weakness avoided — not a hand-fixed order. Without scores it
    falls back to the static curated order. Unmapped dimensions are skipped."""
    out: list[MethodSubstitution] = []
    seen: set[str] = set()
    for dim in weak_dimensions:
        if dim not in _SUBSTITUTION_MAP or dim in seen:
            continue
        seen.add(dim)
        avoid, prefer, why = _SUBSTITUTION_MAP[dim]
        prefer_methods = list(prefer)
        basis = "static"
        fitness: tuple[tuple[str, float], ...] = ()
        if capability_scores is not None:
            scored = sorted(
                prefer_methods,
                key=lambda m: (method_fitness(m, capability_scores), -prefer_methods.index(m)),
                reverse=True,
            )
            fitness = tuple((m.value, method_fitness(m, capability_scores)) for m in scored)
            prefer_methods = scored
            basis = "measured"
        out.append(MethodSubstitution(
            dimension=dim, avoid=tuple(m.value for m in avoid),
            prefer=tuple(m.value for m in prefer_methods), why=why, basis=basis, fitness=fitness))
    return out


def rank_methods_by_fitness(capability_scores: Mapping[str, float] | None) -> list[tuple[str, float]]:
    """A model's method "向き不向き": every known generation method ranked by measured fitness
    (best-first). This is the benchmark-facing view — it turns the 16-dim capability profile into
    "which generation method this model should be driven with". A future per-method live measurement
    can replace ``method_fitness`` without changing callers."""
    ranked = sorted(
        _METHOD_REQUIRED_DIMENSIONS,
        key=lambda m: method_fitness(m, capability_scores),
        reverse=True,
    )
    return [(m.value, round(method_fitness(m, capability_scores), 3)) for m in ranked]


__all__ = [
    "MethodSubstitution", "recommend_method_substitutions", "method_fitness",
    "rank_methods_by_fitness", "WEAKNESS_THRESHOLD",
]
