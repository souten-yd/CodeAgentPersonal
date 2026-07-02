from __future__ import annotations

import logging
import uuid
from typing import Callable

from agent.atlas_llm_output_models import RequirementAnalysisOutput
from agent.atlas_llm_schemas import requirement_analysis_json_schema
from agent.atlas_structured_output import generate_structured
from agent.atlas_input_canonicalizer import ensure_english_text
from agent.requirement_schema import RequirementCategoryScores, RequirementDefinition


logger = logging.getLogger(__name__)


class RequirementAnalyzer:
    def __init__(self, llm_json_fn: Callable[[str, str], dict | None]) -> None:
        self.llm_json_fn = llm_json_fn
        self._last_warnings: list[str] = []

    def get_last_warnings(self) -> list[str]:
        return list(self._last_warnings)

    def analyze(
        self,
        *,
        source_task_id: str,
        user_input: str,
        requirement_mode: str,
        planning_mode: str,
        prompt: str,
        nexus_context: dict,
        repository_context: str,
        existing_requirement: RequirementDefinition | None = None,
        canonical_task_spec: dict | None = None,
    ) -> RequirementDefinition:
        warnings: list[str] = []
        nexus_text = _format_nexus_context(nexus_context)
        raw_user_input = str((canonical_task_spec or {}).get("raw_user_input") or "").strip()
        sections = [f"User Input:\n{user_input}"]
        # The canonical English "User Input" above is a best-effort local normalization and
        # can silently genericize or drop content (e.g. turn a specific "Rubik's cube" request
        # into "build the requested software deliverable"). Surface the verbatim original request
        # so the (multilingual) analyzer honors the user's ACTUAL intent rather than planning from
        # a lossy summary.
        if raw_user_input and raw_user_input != str(user_input or "").strip():
            sections.append(
                "Original User Request (verbatim, authoritative — the canonical English above is only "
                "a best-effort normalization and may be incomplete; interpret the goal from THIS):\n"
                f"{raw_user_input}"
            )
        sections.extend([
            f"Requirement Mode: {requirement_mode}",
            f"Planning Mode: {planning_mode}",
            f"Nexus Context:\n{nexus_text}",
            f"Repository Context: {repository_context}",
        ])
        context_input = "\n\n".join(sections)
        structured = generate_structured(
            self.llm_json_fn,
            prompt,
            context_input,
            json_schema=requirement_analysis_json_schema(),
            model=RequirementAnalysisOutput,
        )
        warnings.extend(structured.warnings)
        raw_payload = structured.data
        analysis_failed = False
        if raw_payload is None:
            analysis_failed = True
            warnings.append("Requirement analysis LLM output could not be parsed. Planning is blocked until requirement analysis is retried.")
            payload: dict = {}
        elif not isinstance(raw_payload, dict):
            analysis_failed = True
            warnings.append("Requirement analysis LLM output was not a JSON object. Planning is blocked until requirement analysis is retried.")
            payload = {}
        else:
            payload = raw_payload
            if not payload:
                analysis_failed = True
                warnings.append("Requirement analysis LLM output was empty. Planning is blocked until requirement analysis is retried.")

        requirement_id = existing_requirement.requirement_id if existing_requirement else f"req_{uuid.uuid4().hex[:12]}"
        category_scores = payload.get("category_scores") or {}
        if not isinstance(category_scores, dict):
            warnings.append("Requirement payload category_scores was not a JSON object. Default category scores were used.")
            category_scores = {}
        req = RequirementDefinition(
            requirement_id=requirement_id,
            source_task_id=source_task_id,
            user_input=user_input,
            raw_user_input=str((canonical_task_spec or {}).get("raw_user_input") or user_input),
            canonical_task_spec=dict(canonical_task_spec or {}),
            interpreted_goal=str(payload.get("interpreted_goal", user_input[:120])),
            user_intent=str(payload.get("user_intent", "Solve user request safely and incrementally.")),
            task_type=str(payload.get("task_type", _guess_task_type(user_input))),
            scope=_as_str_list(payload.get("scope")),
            out_of_scope=_as_str_list(payload.get("out_of_scope")),
            functional_requirements=_as_str_list(payload.get("functional_requirements")),
            non_functional_requirements=_merge_non_functional(payload.get("non_functional_requirements")),
            constraints=_as_str_list(payload.get("constraints")),
            assumptions=_as_str_list(payload.get("assumptions")),
            open_questions=payload.get("open_questions") or [],
            answered_questions=existing_requirement.answered_questions if existing_requirement else [],
            requirement_completeness_score=_score(payload.get("requirement_completeness_score"), 0.65),
            category_scores=RequirementCategoryScores(
                goal=_score(category_scores.get("goal"), 0.7),
                scope=_score(category_scores.get("scope"), 0.6),
                functional_requirements=_score(category_scores.get("functional_requirements"), 0.7),
                non_functional_requirements=_score(category_scores.get("non_functional_requirements"), 0.6),
                constraints=_score(category_scores.get("constraints"), 0.6),
                done_definition=_score(category_scores.get("done_definition"), 0.65),
            ),
            priority=str(payload.get("priority", "medium")),
            done_definition=_as_str_list(payload.get("done_definition")),
            acceptance_criteria=_as_str_list(payload.get("acceptance_criteria")),
            verification_contract=payload.get("verification_contract") if isinstance(payload.get("verification_contract"), dict) else {},
            expected_changes=_as_str_list(payload.get("expected_changes")),
            preserve_behaviors=_as_str_list(payload.get("preserve_behaviors")),
            selected_architecture=str(payload.get("selected_architecture") or ""),
            requirement_items=_as_requirement_items(payload.get("requirements") or payload.get("requirement_items")),
            risks=_as_str_list(payload.get("risks")),
            clarification_status=existing_requirement.clarification_status if existing_requirement else "not_needed",
            ready_for_planning=False if analysis_failed else (existing_requirement.ready_for_planning if existing_requirement else True),
            user_confirmed=False,
            analysis_status="failed" if analysis_failed else "ok",
        )
        if not req.functional_requirements:
            if not analysis_failed:
                req.functional_requirements = ["Create an implementation plan that satisfies the canonical user request."]
                warnings.append("Requirement payload did not include functional_requirements. Fallback requirement item was generated.")
            else:
                warnings.append("Requirement analysis failed; functional_requirements were left empty.")
        if not req.done_definition:
            if not analysis_failed:
                req.done_definition = ["The implementation plan is specific enough to review before any code changes."]
                warnings.append("Requirement payload did not include done_definition. Fallback done_definition was generated.")
            else:
                warnings.append("Requirement analysis failed; done_definition was left empty.")
        if analysis_failed:
            req.ready_for_planning = False

        self._last_warnings = warnings
        req.analysis_warnings = list(warnings)
        return req


def _score(value, default: float) -> float:
    """
    Normalize LLM-provided score into 0.0 - 1.0.
    Accepts floats, ints, numeric strings, percentages, labels, booleans, None.
    Never raises.
    """
    try:
        default_score = max(0.0, min(1.0, float(default)))
    except Exception:  # noqa: BLE001
        default_score = 0.0

    if value is None:
        return default_score

    if isinstance(value, bool):
        return 1.0 if value else 0.0

    if isinstance(value, (int, float)):
        try:
            n = float(value)
            if n > 1.0 and n <= 100.0:
                n = n / 100.0
            return max(0.0, min(1.0, n))
        except Exception:  # noqa: BLE001
            return default_score

    text = str(value).strip().lower()
    if not text:
        return default_score

    label_map = {
        "high": 0.85,
        "higher": 0.85,
        "good": 0.8,
        "strong": 0.85,
        "medium": 0.6,
        "med": 0.6,
        "moderate": 0.6,
        "mid": 0.6,
        "low": 0.35,
        "weak": 0.35,
        "poor": 0.3,
        "unknown": default_score,
        "n/a": default_score,
        "na": default_score,
        "none": default_score,
    }
    if text in label_map:
        normalized = max(0.0, min(1.0, float(label_map[text])))
        if normalized != default_score or text not in {"unknown", "n/a", "na", "none"}:
            logger.warning('Requirement score "%s" normalized to %s.', value, normalized)
        return normalized

    try:
        if text.endswith("%"):
            normalized = max(0.0, min(1.0, float(text[:-1].strip()) / 100.0))
            logger.warning('Requirement score "%s" normalized to %s.', value, normalized)
            return normalized
        if "/" in text:
            left, right = text.split("/", 1)
            denom = float(right.strip())
            if denom:
                normalized = max(0.0, min(1.0, float(left.strip()) / denom))
                logger.warning('Requirement score "%s" normalized to %s.', value, normalized)
                return normalized
        n = float(text)
        if n > 1.0 and n <= 100.0:
            n = n / 100.0
        return max(0.0, min(1.0, n))
    except Exception:  # noqa: BLE001
        logger.warning('Invalid requirement score "%s"; default %s used.', value, default_score)
        return default_score


from agent.atlas_list_utils import as_str_list as _as_str_list


def _as_requirement_items(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            req = dict(item)
            description = str(req.get("description") or req.get("title") or req.get("goal") or "").strip()
            if not description:
                continue
            req.setdefault("requirement_id", str(req.get("id") or f"req_{index:03d}"))
            req["description"] = description
            req.setdefault("required", True)
            out.append(req)
        elif str(item).strip():
            out.append({"requirement_id": f"req_{index:03d}", "description": str(item).strip(), "required": True})
    return out


def _guess_task_type(user_input: str) -> str:
    text = user_input.lower()
    if any(k in text for k in ["bug", "fix", "バグ", "不具合"]):
        return "bugfix"
    if any(k in text for k in ["ui", "画面", "デザイン"]):
        return "ui"
    if any(k in text for k in ["refactor", "リファクタ"]):
        return "refactor"
    if any(k in text for k in ["project", "新規", "generate", "生成"]):
        return "project_generation"
    if any(k in text for k in ["investigate", "調査"]):
        return "investigation"
    return "feature"


def _merge_non_functional(raw_value) -> list[str]:
    existing = [ensure_english_text(value) for value in _as_str_list(raw_value)]
    minimums = [
        "Stability: preserve existing behavior.",
        "Maintainability: keep responsibilities separated and readable.",
        "UI/UX: remain consistent with the existing interface.",
        "iPhone Safari support: avoid layout breakage.",
        "Docker, Runpod, and Windows local compatibility.",
        "Security: do not perform unsafe automatic execution.",
        "Data persistence: keep JSON and Markdown records consistent.",
        "Logging: surface warnings clearly.",
        "Recoverability: clear busy states and allow retry after errors.",
        "Backward compatibility with existing features.",
    ]
    merged = list(existing)
    for item in minimums:
        if not any(item.split(":")[0] in x for x in merged):
            merged.append(item)
    return merged


def _format_nexus_context(nexus_context: dict) -> str:
    if not isinstance(nexus_context, dict):
        return str(nexus_context)
    compact = str(nexus_context.get("compact_text") or "").strip()
    if compact:
        return compact[:8000]
    summary = str(nexus_context.get("summary") or "")
    items = nexus_context.get("items") if isinstance(nexus_context.get("items"), list) else []
    lines = [summary] if summary else []
    for item in items[:4]:
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("name") or "")
            s = str(item.get("summary") or item.get("description") or item.get("content") or "")
            lines.append(f"- {title}: {s[:200]}")
        else:
            lines.append(f"- {str(item)[:200]}")
    return "\n".join([x for x in lines if x]).strip()[:8000]
