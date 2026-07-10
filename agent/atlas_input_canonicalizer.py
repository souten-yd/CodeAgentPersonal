from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field


SourceLanguage = Literal["ja", "en", "mixed", "unknown"]
RequirementPriority = Literal["must", "should", "nice_to_have"]


class CanonicalRequirement(BaseModel):
    id: str
    raw_text: str = ""
    canonical_text_en: str
    category: str = ""
    priority: RequirementPriority = "must"
    confidence: float = 1.0


class CanonicalGlossaryEntry(BaseModel):
    raw_term: str
    canonical_term_en: str
    note: str = ""


class CanonicalTaskSpec(BaseModel):
    raw_user_input: str
    source_language: SourceLanguage = "unknown"
    canonical_language: Literal["en"] = "en"
    canonical_request_en: str
    canonical_requirements: list[CanonicalRequirement] = Field(default_factory=list)
    glossary: list[CanonicalGlossaryEntry] = Field(default_factory=list)
    normalization_warnings: list[str] = Field(default_factory=list)


_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def contains_cjk(value: Any) -> bool:
    return bool(_CJK_RE.search(str(value or "")))


def detect_source_language(value: str) -> SourceLanguage:
    text = str(value or "")
    cjk_count = len(_CJK_RE.findall(text))
    latin_count = len(_LATIN_RE.findall(text))
    has_cjk = cjk_count > 0
    has_latin = latin_count > 0
    if has_cjk and has_latin and cjk_count >= latin_count:
        return "ja"
    if has_cjk and has_latin:
        return "mixed"
    if has_cjk:
        return "ja"
    if has_latin:
        return "en"
    return "unknown"


class AtlasInputCanonicalizer:
    """Build an English task spec before Atlas planning.

    This service is deterministic and local-only. It intentionally preserves the raw request while
    giving downstream PlanPool and requirement mapping an English representation to compare.
    """

    def canonicalize(self, user_input: str, *, target_language: str = "en") -> CanonicalTaskSpec:
        if str(target_language or "en").lower() != "en":
            raise ValueError("atlas canonical task specs currently support target_language='en' only")
        raw = str(user_input or "").strip()
        source_language = detect_source_language(raw)
        warnings: list[str] = []
        glossary = _glossary(raw)
        if source_language == "en":
            reqs = _english_requirements(raw)
            canonical_request = raw
        else:
            reqs, warnings = _canonical_requirements_from_multilingual(raw)
            canonical_request = _canonical_request_from_requirements(reqs)
        return CanonicalTaskSpec(
            raw_user_input=raw,
            source_language=source_language,
            canonical_request_en=canonical_request,
            canonical_requirements=reqs,
            glossary=glossary,
            normalization_warnings=warnings,
        )


def canonical_task_from_dict(value: Any) -> CanonicalTaskSpec | None:
    if not isinstance(value, dict):
        return None
    try:
        return CanonicalTaskSpec(**value)
    except Exception:
        return None


def render_canonical_task_for_prompt(spec: CanonicalTaskSpec | dict[str, Any] | None) -> str:
    if isinstance(spec, dict):
        spec = canonical_task_from_dict(spec)
    if spec is None:
        return ""
    lines = [
        "Canonical Task Spec:",
        f"- source_language: {spec.source_language}",
        f"- canonical_language: {spec.canonical_language}",
        f"- canonical_request_en: {spec.canonical_request_en}",
        "- canonical_requirements:",
    ]
    for req in spec.canonical_requirements:
        lines.append(f"  - {req.id}: {req.canonical_text_en}")
    if spec.normalization_warnings:
        lines.append("- normalization_warnings:")
        for warning in spec.normalization_warnings:
            lines.append(f"  - {warning}")
    lines.append("Use the canonical English request and requirement IDs. Keep planner output in English.")
    return "\n".join(lines)


def ensure_english_text(value: str, *, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not contains_cjk(text):
        return text
    translated = _translate_known_terms(text)
    if translated and not contains_cjk(translated):
        return translated
    return fallback or "English normalization required for this planner text."


def _english_requirements(raw: str) -> list[CanonicalRequirement]:
    chunks = _split_segments(raw)
    if not chunks and raw:
        chunks = [raw]
    return [
        CanonicalRequirement(
            id=f"req_{index:03d}",
            raw_text=chunk,
            canonical_text_en=chunk,
            confidence=1.0,
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


def _canonical_requirements_from_multilingual(raw: str) -> tuple[list[CanonicalRequirement], list[str]]:
    """Deterministic, non-semantic fallback for CJK/mixed-language input.

    This used to guess structured requirements (genre, setting, weapons, ...) from surface keyword
    matches (e.g. "space station" -> a hardcoded English sentence). That guessing was inherently
    unsound: a keyword shared across unrelated domains (e.g. the generic Japanese word for
    "shooting", or bare "bullet") would false-positive-match a narrow, hardcoded example sentence
    and inject it into the planning prompt as if it were an actual requirement -- corrupting
    planning for any request that happened to share vocabulary with the example it was tuned on.
    The real requirement-analysis LLM call already derives proper structured requirements directly
    from the raw input (see PlannerPhase1.build_requirement), so this layer only needs to hand the
    planner a safe, CJK-free anchor string -- not a semantic guess it cannot make reliably.
    """
    canonical_text = ensure_english_text(
        raw, fallback="Implement the requested behavior described in the source request."
    )
    requirements = [CanonicalRequirement(
        id="req_001",
        raw_text=raw,
        canonical_text_en=canonical_text,
        category="functional",
        confidence=0.5,
    )]
    warnings = ["canonicalization_used_generic_fallback"]
    if contains_cjk(canonical_text):
        warnings.append("canonicalization_low_confidence_segment")
    return requirements, warnings


def _canonical_request_from_requirements(requirements: list[CanonicalRequirement]) -> str:
    if not requirements:
        return "Implement the requested task."
    first = requirements[0].canonical_text_en.rstrip(".")
    rest = [req.canonical_text_en.rstrip(".") for req in requirements[1:]]
    if not rest:
        return first + "."
    return first + ". Requirements: " + "; ".join(rest) + "."


def _split_segments(raw: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"[\n。.!?]+", str(raw or ""))
        if part.strip()
    ]


def _glossary(raw: str) -> list[CanonicalGlossaryEntry]:
    entries = []
    for raw_term, canonical in (
        ("宇宙ステーション", "space station"),
        ("ハンドガン", "handgun"),
        ("ショットガン", "shotgun"),
        ("ロケットランチャー", "rocket launcher"),
        ("宇宙人", "alien"),
        ("弾は無限", "unlimited ammunition"),
        ("ファーストパーソンシューティング", "first-person shooter"),
    ):
        if raw_term in raw:
            entries.append(CanonicalGlossaryEntry(raw_term=raw_term, canonical_term_en=canonical))
    return entries


def _translate_known_terms(text: str) -> str:
    replacements = {
        "ゴール": "Goal",
        "受入条件": "Acceptance criterion",
        "検証": "Verification",
        "ロールバック": "Rollback",
        "宇宙ステーション": "space station",
        "ハンドガン": "handgun",
        "ショットガン": "shotgun",
        "ロケットランチャー": "rocket launcher",
        "宇宙人": "alien",
        "敵": "enemy",
        "弾": "ammo",
        "無限": "unlimited",
        "作って": "build",
        "作成": "create",
        "実装": "implement",
        "移動": "movement",
        "照準": "aiming",
    }
    out = str(text or "")
    for source, target in replacements.items():
        out = out.replace(source, target)
    out = re.sub(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]+", " ", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out
