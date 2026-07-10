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
    lowered = raw.lower()
    requirements: list[tuple[str, str, str, float]] = []

    def add(raw_text: str, text: str, category: str = "functional", confidence: float = 0.95) -> None:
        if not any(existing[1] == text for existing in requirements):
            requirements.append((raw_text, text, category, confidence))

    # "シューティング" ("shooting") alone is the generic Japanese word for the whole shooter genre
    # (2D shmups, rail shooters, FPS, etc.) -- it must NOT by itself imply first-person. Only a
    # first-person-specific signal (fps / first-person / the compound "ファーストパーソン...") should.
    if any(token in lowered for token in ("fps", "first-person")) or "ファーストパーソン" in raw:
        add(
            _source_segment(raw, ("fps", "ファーストパーソン", "シューティング", "007")),
            "Build an HTML-based retro first-person shooter game inspired by classic console FPS gameplay.",
        )
    elif any(token in raw for token in ("作って", "作成", "生成", "実装")) or any(token in lowered for token in ("build", "create", "make", "implement")):
        add(
            _source_segment(raw, ("作って", "作成", "生成", "実装", "build", "create")),
            "Build the requested software deliverable.",
            confidence=0.75,
        )
    if "html" in lowered:
        add(_source_segment(raw, ("HTML", "html")), "Produce the deliverable as browser-runnable HTML.")
    if "space station" in lowered or "宇宙ステーション" in raw:
        add(_source_segment(raw, ("space station", "宇宙ステーション")), "Set the experience in a space station environment.")
    if "handgun" in lowered or "ハンドガン" in raw:
        weapons = _detected_weapons(raw, lowered)
        add(_source_segment(raw, ("handgun", "shotgun", "rocket launcher", "ハンドガン", "ショットガン", "ロケットランチャー")), f"Implement player weapons: {weapons}.")
    # "弾" ("bullet/ammo") alone is generic to any shooting mechanic -- it must NOT by itself imply
    # unlimited ammo. Only an actual unlimited/infinite qualifier should.
    if "unlimited" in lowered or "infinite" in lowered or "無限" in raw:
        add(_source_segment(raw, ("unlimited", "infinite", "無限", "弾")), "Give player weapons unlimited ammunition.")
    if "alien" in lowered or "宇宙人" in raw:
        add(_source_segment(raw, ("alien", "宇宙人", "敵")), "Add alien enemies.")
    if any(token in lowered for token in ("enemy", "weapon", "combat")) or any(token in raw for token in ("敵", "武器", "ダメージ", "倒")):
        add(_source_segment(raw, ("enemy", "weapon", "combat", "敵", "武器", "ダメージ", "倒")), "Implement combat, damage, enemy defeat, and game state feedback.")
    if any(token in lowered for token in ("movement", "aiming", "first-person")) or any(token in raw for token in ("移動", "照準", "操作")):
        # Movement/aiming vocabulary is genre-neutral (a top-down or side-view shooter has it too);
        # only assert "first-person" when that perspective was independently detected above.
        movement_text = (
            "Implement player-controlled first-person movement and aiming."
            if any(token in lowered for token in ("fps", "first-person")) or "ファーストパーソン" in raw
            else "Implement player-controlled movement and aiming."
        )
        add(_source_segment(raw, ("movement", "aiming", "移動", "照準", "操作")), movement_text)

    warnings: list[str] = []
    if not requirements:
        requirements.append((raw, "Implement the requested behavior described in the source request.", "functional", 0.45))
        warnings.append("canonicalization_used_generic_fallback")
    if contains_cjk(raw) and any(req[3] < 0.8 for req in requirements):
        warnings.append("canonicalization_low_confidence_segment")

    return [
        CanonicalRequirement(
            id=f"req_{index:03d}",
            raw_text=raw_text,
            canonical_text_en=text,
            category=category,
            confidence=confidence,
        )
        for index, (raw_text, text, category, confidence) in enumerate(requirements, start=1)
    ], warnings


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


def _source_segment(raw: str, tokens: tuple[str, ...]) -> str:
    for segment in _split_segments(raw):
        s_lower = segment.lower()
        if any(token.lower() in s_lower for token in tokens):
            return segment
    return raw


def _detected_weapons(raw: str, lowered: str) -> str:
    weapons: list[str] = []
    for raw_term, canonical in (
        ("ハンドガン", "handgun"),
        ("handgun", "handgun"),
        ("ショットガン", "shotgun"),
        ("shotgun", "shotgun"),
        ("ロケットランチャー", "rocket launcher"),
        ("rocket launcher", "rocket launcher"),
    ):
        if raw_term.lower() in lowered or raw_term in raw:
            weapons.append(canonical)
    return ", ".join(dict.fromkeys(weapons)) or "handgun, shotgun, and rocket launcher"


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
