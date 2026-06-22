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
from dataclasses import dataclass

from agent.model_forge.method_taxonomy import MethodVariant

WEAKNESS_THRESHOLD = 0.55

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
    prefer: tuple[str, ...]
    why: str

    def as_dict(self) -> dict:
        return {"dimension": self.dimension, "avoid": list(self.avoid),
                "prefer": list(self.prefer), "why": self.why}


def recommend_method_substitutions(weak_dimensions: Iterable[str]) -> list[MethodSubstitution]:
    """For each weak dimension that has a known structural alternative, return the method to avoid
    and the methods to prefer. Dimensions with no mapping are skipped (injection/other levers apply)."""
    out: list[MethodSubstitution] = []
    seen: set[str] = set()
    for dim in weak_dimensions:
        if dim in _SUBSTITUTION_MAP and dim not in seen:
            seen.add(dim)
            avoid, prefer, why = _SUBSTITUTION_MAP[dim]
            out.append(MethodSubstitution(
                dimension=dim, avoid=tuple(m.value for m in avoid),
                prefer=tuple(m.value for m in prefer), why=why))
    return out


__all__ = ["MethodSubstitution", "recommend_method_substitutions", "WEAKNESS_THRESHOLD"]
