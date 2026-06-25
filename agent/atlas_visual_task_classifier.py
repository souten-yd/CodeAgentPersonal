"""
Task classification for visual generation.

Produces a VisualTaskClassification from a NormalizedVisualRequirement
(and optional raw task description) using deterministic keyword rules.
No LLM call — results are stable and testable.

Classification rules:
- canvas_game     — only when gameplay keywords are present
- canvas_animation — only when canvas/webgl rendering implied, no gameplay
- animated_html_page — DOM/CSS/JS animations without canvas
- static_html_page — no animation/interaction keywords
- chart_visualization — explicit chart/graph/plot/visualization keywords
- ui_component / interactive_web_app — form/component/interaction without canvas
- svg_visualization — SVG rendering explicitly requested
- unknown — none of the above with sufficient confidence
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent.atlas_visual_requirement_normalizer import NormalizedVisualRequirement

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARTIFACT_TYPES = [
    "static_html_page",
    "animated_html_page",
    "ui_component",
    "interactive_web_app",
    "canvas_animation",
    "canvas_game",
    "svg_visualization",
    "chart_visualization",
    "document",
    "test_only",
    "unknown",
]

VISUAL_INTENTS = [
    "static_render",
    "text_animation",
    "element_animation",
    "layout_interaction",
    "form_input",
    "data_visualization",
    "canvas_motion",
    "gameplay",
    "media_playback",
    "none",
    "unknown",
]

INTERACTION_INTENTS = [
    "none",
    "click",
    "keyboard",
    "pointer",
    "touch",
    "drag_drop",
    "form_submit",
    "game_controls",
    "unknown",
]

RUNTIME_REQUIREMENT_FLAGS = [
    "browser_required",
    "animation_required",
    "runtime_loop_required",
    "input_required",
    "canvas_required",
    "svg_required",
    "webgl_required",
    "network_required",
    "storage_required",
    "audio_required",
    "video_required",
]

# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

@dataclass
class VisualTaskClassification:
    artifact_type: str        # value from ARTIFACT_TYPES
    visual_intent: str        # value from VISUAL_INTENTS
    interaction_intent: str   # value from INTERACTION_INTENTS
    runtime_requirements: list[str] = field(default_factory=list)
    confidence: float = 1.0   # 0.0–1.0
    rationale: str = ""


# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

_GAME_KEYWORDS = re.compile(
    r"\b(game|score|lives?|player|collision|level|enemy|enemies|"
    r"sprite|tilemap|power[\s\-]?up|checkpoint|game[\s\-]?over|"
    r"leaderboard|high[\s\-]?score|respawn|hitbox|arena)\b",
    re.I,
)
# Negation patterns that suppress game classification even when game keywords appear
_GAME_NEGATION = re.compile(
    r"\b(no|not|without|non[\s\-]|without any)\s+(game|gameplay|gaming|game\s+mechanic)",
    re.I,
)

_CANVAS_KEYWORDS = re.compile(
    r"\b(canvas|webgl|2d\s+rendering|pixel[\s\-]?art|particle[\s\-]?system|"
    r"particle\b|draw[\s\-]?loop|animation[\s\-]?loop|requestAnimationFrame)\b",
    re.I,
)

_SVG_KEYWORDS = re.compile(
    r"\b(svg|scalable\s+vector|vector\s+graphic)\b",
    re.I,
)

_CHART_KEYWORDS = re.compile(
    r"\b(chart|graph|plot|histogram|pie[\s\-]?chart|bar[\s\-]?chart|"
    r"line[\s\-]?chart|scatter[\s\-]?plot|data[\s\-]?visuali[sz]ation|"
    r"dashboard[\s\-]?chart|visuali[sz]ation|infographic)\b",
    re.I,
)

_FORM_KEYWORDS = re.compile(
    r"\b(form|input\s+field|text[\s\-]?field|checkbox|radio\s+button|"
    r"dropdown|select\s+menu|form\s+validation|signup|login\s+form|submit)\b",
    re.I,
)

_COMPONENT_KEYWORDS = re.compile(
    r"\b(component|widget|panel|modal|sidebar|nav(?:bar|igation)?|"
    r"card\s+layout|accordion|tab[\s\-]?component)\b",
    re.I,
)

_APP_KEYWORDS = re.compile(
    r"\b(app|application|webapp|web\s+app|spa|single[\s\-]?page|"
    r"dashboard|admin\s+panel|todo\s+app|crud)\b",
    re.I,
)
# Action verbs that imply interactive functionality even without explicit pointer words
_ACTION_VERB_KEYWORDS = re.compile(
    r"\b(add|delete|remove|edit|update|create|search|filter|sort|"
    r"submit|save|load|toggle|select|upload|download|manage|track|solve|randomi[sz]e)\b",
    re.I,
)
_RUBIK_SOLVER_KEYWORDS = re.compile(
    r"\brubik(?:'s)?\b|ルービック|"
    r"(?:\bcube\b.*\b(?:solver|solve)\b|\b(?:solver|solve)\b.*\bcube\b)|"
    r"(?:キューブ.*(?:解く|揃う|そろう)|(?:解く|揃う|そろう).*キューブ)",
    re.I,
)
_RUBIK_INTERACTION_KEYWORDS = re.compile(
    r"\b(button|solve|solver|step[\s\-]?by[\s\-]?step|random(?:ize|ise|ized|ised)?)\b|"
    r"ボタン|押す|自動|順次|初期状態|ランダム|解く|揃う|そろう",
    re.I,
)
_HTML_KEYWORDS = re.compile(r"html?", re.I)

_ANIMATION_KEYWORDS = re.compile(
    # Stem-based: animat(e/ion/ing/ed), wave, oscillat(e/ion), etc.
    r"\b(animat\w*|wave\w*|oscillat\w*|bounc\w*|spin\w*|rotat\w*|pulse\w*|fade\w*|"
    r"color\s+chang\w*|colour\s+chang\w*|hue|rainbow|slide\w*|drift\w*|"
    r"orbit\w*|translat\w*|transit\w*|kinetic)\b",
    re.I,
)

_STATIC_KEYWORDS = re.compile(
    r"\b(static|display|show|render|page|document|landing[\s\-]?page|"
    r"article|blog[\s\-]?post|report)\b",
    re.I,
)

_AUDIO_KEYWORDS = re.compile(r"\b(audio|sound|music|play[\s\-]?sound)\b", re.I)
_VIDEO_KEYWORDS = re.compile(r"\b(video|mp4|stream|media[\s\-]?player)\b", re.I)
_NETWORK_KEYWORDS = re.compile(r"\b(fetch|api[\s\-]?call|http|ajax|websocket)\b", re.I)
_STORAGE_KEYWORDS = re.compile(r"\b(localStorage|sessionStorage|indexedDB|cache)\b", re.I)


def _combine(normalized_text: str, task_desc: str) -> str:
    """Merge normalized requirement text and task description for matching."""
    return f"{normalized_text} {task_desc}"


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class VisualTaskClassifier:
    """
    Deterministic rule-based classifier for visual generation tasks.

    Rules are ordered from most-specific (canvas_game) to least-specific
    (static_html_page / unknown).  The first matching rule wins.
    """

    def classify(
        self,
        normalized: NormalizedVisualRequirement,
        task_description: str = "",
    ) -> VisualTaskClassification:
        text = _combine(normalized.raw_requirement, task_description)
        rt = list(normalized.runtime_requirements)  # copy; we may extend it

        # ------------------------------------------------------------------
        # 1. Canvas game — requires explicit gameplay keywords
        #    Negations like "no game mechanics" suppress this branch
        # ------------------------------------------------------------------
        game_keyword_present = bool(_GAME_KEYWORDS.search(text))
        game_negated = bool(_GAME_NEGATION.search(text))
        if game_keyword_present and not game_negated and (
            "canvas_required" in rt or _CANVAS_KEYWORDS.search(text)
        ):
            return VisualTaskClassification(
                artifact_type="canvas_game",
                visual_intent="gameplay",
                interaction_intent="game_controls",
                runtime_requirements=_add_flags(rt, [
                    "browser_required", "canvas_required",
                    "runtime_loop_required", "input_required",
                ]),
                confidence=0.9,
                rationale="Game keywords (score/player/collision) detected alongside canvas/rendering",
            )

        # ------------------------------------------------------------------
        # 2. Canvas animation — canvas/webgl implied but no gameplay
        # ------------------------------------------------------------------
        if "canvas_required" in rt or _CANVAS_KEYWORDS.search(text):
            return VisualTaskClassification(
                artifact_type="canvas_animation",
                visual_intent="canvas_motion",
                interaction_intent=_map_interaction(normalized.interaction_types),
                runtime_requirements=_add_flags(rt, [
                    "browser_required", "canvas_required", "runtime_loop_required",
                ]),
                confidence=0.85,
                rationale="Canvas/WebGL rendering implied without gameplay mechanics",
            )

        # ------------------------------------------------------------------
        # 3. SVG visualisation
        # ------------------------------------------------------------------
        if "svg_required" in rt or _SVG_KEYWORDS.search(text):
            has_anim = bool(_ANIMATION_KEYWORDS.search(text)) or "animation_required" in rt
            return VisualTaskClassification(
                artifact_type="svg_visualization",
                visual_intent="data_visualization" if _CHART_KEYWORDS.search(text) else (
                    "element_animation" if has_anim else "static_render"
                ),
                interaction_intent=_map_interaction(normalized.interaction_types),
                runtime_requirements=_add_flags(rt, [
                    "browser_required", "svg_required",
                ] + (["animation_required"] if has_anim else [])),
                confidence=0.85,
                rationale="SVG rendering explicitly requested",
            )

        # ------------------------------------------------------------------
        # 4. Chart / data visualisation
        # ------------------------------------------------------------------
        if _CHART_KEYWORDS.search(text):
            return VisualTaskClassification(
                artifact_type="chart_visualization",
                visual_intent="data_visualization",
                interaction_intent=_map_interaction(normalized.interaction_types),
                runtime_requirements=_add_flags(rt, ["browser_required"]),
                confidence=0.88,
                rationale="Chart/graph/visualization keywords detected",
            )

        # ------------------------------------------------------------------
        # 5. Puzzle/solver HTML app — interactive stateful UI, not canvas unless explicit
        # ------------------------------------------------------------------
        has_interaction = bool(normalized.interaction_types) or bool(_ACTION_VERB_KEYWORDS.search(text))
        if (
            _RUBIK_SOLVER_KEYWORDS.search(text)
            and ("html_page" in normalized.artifact_type_hints or _HTML_KEYWORDS.search(text))
            and (has_interaction or _RUBIK_INTERACTION_KEYWORDS.search(text))
        ):
            return VisualTaskClassification(
                artifact_type="interactive_web_app",
                visual_intent="layout_interaction",
                interaction_intent=_map_interaction(normalized.interaction_types) if normalized.interaction_types else "click",
                runtime_requirements=_add_flags(rt, [
                    "browser_required", "input_required",
                ]),
                confidence=0.84,
                rationale="Rubik/cube solver HTML request with button/solve interaction; no canvas required",
            )

        # ------------------------------------------------------------------
        # 6. Interactive web app — app keywords + interaction or action verbs
        # ------------------------------------------------------------------
        if _APP_KEYWORDS.search(text) and has_interaction:
            return VisualTaskClassification(
                artifact_type="interactive_web_app",
                visual_intent="layout_interaction",
                interaction_intent=_map_interaction(normalized.interaction_types),
                runtime_requirements=_add_flags(rt, [
                    "browser_required", "input_required",
                ]),
                confidence=0.8,
                rationale="App keywords with explicit interaction requirements",
            )

        # ------------------------------------------------------------------
        # 7. UI component — form or component keywords
        # ------------------------------------------------------------------
        if _FORM_KEYWORDS.search(text):
            return VisualTaskClassification(
                artifact_type="ui_component",
                visual_intent="form_input",
                interaction_intent="form_submit",
                runtime_requirements=_add_flags(rt, [
                    "browser_required", "input_required",
                ]),
                confidence=0.85,
                rationale="Form/input keywords detected",
            )

        if _COMPONENT_KEYWORDS.search(text):
            return VisualTaskClassification(
                artifact_type="ui_component",
                visual_intent="layout_interaction" if normalized.interaction_types else "static_render",
                interaction_intent=_map_interaction(normalized.interaction_types),
                runtime_requirements=_add_flags(rt, ["browser_required"]),
                confidence=0.8,
                rationale="Component/widget keywords detected",
            )

        # ------------------------------------------------------------------
        # 8. Animated HTML page — DOM/CSS animations, no canvas
        # ------------------------------------------------------------------
        has_animation = (
            "animation_required" in rt
            or bool(_ANIMATION_KEYWORDS.search(text))
            or normalized.motion_types
            or normalized.color_types
        )
        if has_animation:
            # Determine visual intent
            vi: str
            if normalized.color_types and not normalized.motion_types:
                vi = "text_animation"
            elif normalized.motion_types:
                vi = "element_animation"
            else:
                vi = "element_animation"

            # audio/video
            extra_rt: list[str] = []
            if _AUDIO_KEYWORDS.search(text):
                extra_rt.append("audio_required")
            if _VIDEO_KEYWORDS.search(text):
                extra_rt.append("video_required")

            return VisualTaskClassification(
                artifact_type="animated_html_page",
                visual_intent=vi,
                interaction_intent=_map_interaction(normalized.interaction_types),
                runtime_requirements=_add_flags(rt, [
                    "browser_required", "animation_required",
                ] + extra_rt),
                confidence=0.82,
                rationale="Animation/motion/color-change keywords detected; no canvas required",
            )

        # ------------------------------------------------------------------
        # 9. Audio/video media
        # ------------------------------------------------------------------
        if _AUDIO_KEYWORDS.search(text) or _VIDEO_KEYWORDS.search(text):
            return VisualTaskClassification(
                artifact_type="interactive_web_app",
                visual_intent="media_playback",
                interaction_intent="click",
                runtime_requirements=_add_flags(rt, [
                    "browser_required",
                    "audio_required" if _AUDIO_KEYWORDS.search(text) else "",
                    "video_required" if _VIDEO_KEYWORDS.search(text) else "",
                ]),
                confidence=0.75,
                rationale="Audio/video media keywords detected",
            )

        # ------------------------------------------------------------------
        # 10. Static HTML page — page/document/display keywords, no motion
        # ------------------------------------------------------------------
        if _STATIC_KEYWORDS.search(text) or "html_page" in normalized.artifact_type_hints:
            return VisualTaskClassification(
                artifact_type="static_html_page",
                visual_intent="static_render",
                interaction_intent="none",
                runtime_requirements=_add_flags(rt, ["browser_required"]),
                confidence=0.75,
                rationale="Static page/document keywords; no animation or interaction detected",
            )

        # ------------------------------------------------------------------
        # 11. Unknown — not enough signal
        # ------------------------------------------------------------------
        return VisualTaskClassification(
            artifact_type="unknown",
            visual_intent="unknown",
            interaction_intent="unknown",
            runtime_requirements=_add_flags(rt, []),
            confidence=0.3,
            rationale="Insufficient keywords to classify confidently; defaulting to conservative contract",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_flags(existing: list[str], additions: list[str]) -> list[str]:
    """Merge lists, deduplicate, preserve order, drop empty strings."""
    seen: set[str] = set(existing)
    result = list(existing)
    for flag in additions:
        if flag and flag not in seen:
            seen.add(flag)
            result.append(flag)
    return result


def _map_interaction(interaction_types: list[str]) -> str:
    if not interaction_types:
        return "none"
    t = interaction_types[0]
    mapping = {
        "drag": "drag_drop",
        "form": "form_submit",
        "submit": "form_submit",
        "keyboard": "keyboard",
        "click": "click",
        "pointer": "pointer",
        "touch": "touch",
        "hover": "pointer",
        "scroll": "none",   # scroll is not user-input in the interaction sense
    }
    return mapping.get(t, "unknown")
