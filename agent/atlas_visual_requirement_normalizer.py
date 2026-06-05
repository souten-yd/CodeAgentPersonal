"""
Requirement normalization for visual generation tasks.

Transforms raw user requirement text into a structured NormalizedVisualRequirement
without losing the original text. Uses regex/keyword extraction only — no LLM call —
so results are deterministic and fast.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Normalised output model
# ---------------------------------------------------------------------------

@dataclass
class NormalizedVisualRequirement:
    raw_requirement: str

    # Inferred hints about the desired output type
    artifact_type_hints: list[str] = field(default_factory=list)
    # e.g. ["html_page", "canvas", "svg", "chart", "game", "component", "app"]

    # Timing / frequency
    animation_duration_seconds: float | None = None
    animation_frequency_hz: float | None = None   # 1 Hz == once per second

    # Motion / colour / interaction categories
    motion_types: list[str] = field(default_factory=list)
    # e.g. ["wave", "bounce", "rotate", "fade", "scroll", "pulse"]

    color_types: list[str] = field(default_factory=list)
    # e.g. ["rainbow", "hue-cycle", "gradient", "random-color"]

    interaction_types: list[str] = field(default_factory=list)
    # e.g. ["click", "keyboard", "drag", "touch", "form"]

    # Rendering target (most specific one wins)
    rendering_target: str | None = None
    # "html" | "css" | "svg" | "canvas" | "webgl" | None

    # Coarse runtime flags surfaced from the text
    runtime_requirements: list[str] = field(default_factory=list)
    # subset of: browser_required, animation_required, runtime_loop_required,
    #             input_required, canvas_required, svg_required, webgl_required

    # Provenance / audit
    source_phrases: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unresolved_ambiguities: list[str] = field(default_factory=list)

    # Clarification is required only when ambiguity affects file scope,
    # runtime permissions, or destructive behaviour — never for cosmetic defaults.
    clarification_required: bool = False

    confidence: float = 1.0   # 0.0–1.0


# ---------------------------------------------------------------------------
# Lookup tables
# ---------------------------------------------------------------------------

# (compiled-regex, canonical-name, runtime-requirement-flags)
_ARTIFACT_HINTS: list[tuple[re.Pattern, str, list[str]]] = [
    (re.compile(r"\bcanvas\b", re.I),          "canvas",    ["canvas_required", "browser_required"]),
    (re.compile(r"\bwebgl\b",  re.I),          "webgl",     ["webgl_required",  "canvas_required", "browser_required"]),
    (re.compile(r"\bsvg\b",    re.I),          "svg",       ["svg_required",    "browser_required"]),
    (re.compile(r"\bgame\b",   re.I),          "game",      ["canvas_required", "browser_required", "input_required",
                                                               "runtime_loop_required"]),
    (re.compile(r"\b(chart|graph|visuali[sz]ation|plot|diagram)\b", re.I),
                                               "chart",     ["browser_required"]),
    (re.compile(r"\b(component|widget|form|input\s+field)\b", re.I),
                                               "component", ["browser_required"]),
    (re.compile(r"\b(app|application|webapp|web\s+app|dashboard)\b", re.I),
                                               "app",       ["browser_required"]),
    (re.compile(r"\bhtml?\b",  re.I),          "html_page", ["browser_required"]),
    (re.compile(r"\bpage\b",   re.I),          "html_page", ["browser_required"]),
]

_MOTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bwave[s\b]?",         re.I), "wave"),
    (re.compile(r"\bbounc(e|ing)\b",     re.I), "bounce"),
    (re.compile(r"\brot(ate|ating|ation)\b", re.I), "rotate"),
    (re.compile(r"\bfade?s?\b",          re.I), "fade"),
    (re.compile(r"\bpuls(e|ing|es)\b",   re.I), "pulse"),
    (re.compile(r"\bscroll(ing)?\b",     re.I), "scroll"),
    (re.compile(r"\bslide?s?\b",         re.I), "slide"),
    (re.compile(r"\borbit(ing)?\b",      re.I), "orbit"),
    (re.compile(r"\bdrift(ing)?\b",      re.I), "drift"),
    (re.compile(r"\bfall(ing)?\b",       re.I), "fall"),
    (re.compile(r"\bfly(ing)?\b",        re.I), "fly"),
    (re.compile(r"\bshak(e|ing)\b",      re.I), "shake"),
    (re.compile(r"\bswing(ing)?\b",      re.I), "swing"),
    (re.compile(r"\btranslat(e|ing|ion)\b", re.I), "translate"),
    (re.compile(r"\boscillat(e|ing|ion)\b", re.I), "oscillate"),
    (re.compile(r"\b(move|moving|motion)\b", re.I), "move"),
    (re.compile(r"\bspin(ning)?\b",      re.I), "spin"),
    (re.compile(r"\bflicker(ing)?\b",    re.I), "flicker"),
    (re.compile(r"\bblink(ing)?\b",      re.I), "blink"),
    (re.compile(r"\bzooming?\b",         re.I), "zoom"),
]

_COLOR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\brainbow\b",                         re.I), "rainbow"),
    (re.compile(r"\bhue[\s\-]?(cycle|shift|rotat|change)", re.I), "hue-cycle"),
    (re.compile(r"\bhue\b",                             re.I), "hue-cycle"),
    (re.compile(r"\bgradi?ent\b",                       re.I), "gradient"),
    (re.compile(r"\bcolou?r[\s\-]?(chang|cycl|shift)", re.I), "color-cycle"),
    (re.compile(r"\bpalette\b",                         re.I), "palette"),
    (re.compile(r"\bspectrum\b",                        re.I), "spectrum"),
    (re.compile(r"\bchromat",                           re.I), "chromatic"),
    (re.compile(r"\brandom[\s\-]colou?r",               re.I), "random-color"),
    (re.compile(r"\btheme[\s\-]colou?r",                re.I), "theme-color"),
    (re.compile(r"\btint\b",                            re.I), "tint"),
]

_INTERACTION_PATTERNS: list[tuple[re.Pattern, str, list[str]]] = [
    (re.compile(r"\bclick(able|ing|s)?\b",              re.I), "click",    ["input_required"]),
    (re.compile(r"\bdrag[\s\-]?drop\b",                 re.I), "drag",     ["input_required"]),
    (re.compile(r"\bdrag(ging)?\b",                     re.I), "drag",     ["input_required"]),
    (re.compile(r"\bkeyboard\b",                        re.I), "keyboard", ["input_required"]),
    (re.compile(r"\b(key\s*press|keydown|keyup)\b",     re.I), "keyboard", ["input_required"]),
    (re.compile(r"\bpointer\b",                         re.I), "pointer",  ["input_required"]),
    (re.compile(r"\btouch\b",                           re.I), "touch",    ["input_required"]),
    (re.compile(r"\bform\b",                            re.I), "form",     ["input_required"]),
    (re.compile(r"\b(submit|button)\b",                 re.I), "submit",   ["input_required"]),
    (re.compile(r"\bscroll(ing)?\b",                    re.I), "scroll",   []),   # scroll ≠ user input
    (re.compile(r"\bhover(ing)?\b",                     re.I), "hover",    ["input_required"]),
]

# Frequency patterns — normalise to Hz
_FREQ_PATTERNS: list[tuple[re.Pattern, callable]] = [
    # "2 Hz", "2Hz", "2.5 hz"
    (re.compile(r"(\d+(?:\.\d+)?)\s*hz", re.I),
     lambda m: float(m.group(1))),
    # "once per second", "1 per second"
    (re.compile(r"(?:once|1)\s+(?:a|per)\s+second", re.I),
     lambda m: 1.0),
    # "N times per second"
    (re.compile(r"(\d+(?:\.\d+)?)\s+times?\s+per\s+second", re.I),
     lambda m: float(m.group(1))),
    # "N cycles per second"
    (re.compile(r"(\d+(?:\.\d+)?)\s+cycles?\s+per\s+second", re.I),
     lambda m: float(m.group(1))),
    # "60 fps" / "60fps" → not strictly Hz but expressed as per-frame frequency
    (re.compile(r"(\d+)\s*fps", re.I),
     lambda m: float(m.group(1)) / 60.0),  # store relative to 60fps baseline
    # "per frame" — mark as runtime_loop_required; no numeric Hz
]

# Duration patterns — normalise to seconds
_DUR_PATTERNS: list[tuple[re.Pattern, callable]] = [
    # "3 seconds", "3s", "3.5 sec"
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:seconds?|secs?)\b", re.I),
     lambda m: float(m.group(1))),
    # "2 minutes", "2min"
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:minutes?|mins?)\b", re.I),
     lambda m: float(m.group(1)) * 60),
    # "500ms", "500 ms", "500 milliseconds"
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:ms|milliseconds?)\b", re.I),
     lambda m: float(m.group(1)) / 1000),
    # "loop forever" / "infinite loop" / "infinite animation"
    (re.compile(r"(?:loop\s+forever|infinite\s+(?:loop|animation)|loops?\s+indefinitely)", re.I),
     lambda m: -1.0),  # -1 sentinel = infinite
]

# Ambiguous expressions that should be flagged
_AMBIGUOUS_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"\banimation\s+speed\b", re.I),
     "animation speed has no unit",
     "Assumed moderate speed (1 Hz); specify Hz, fps, or seconds for precision"),
    (re.compile(r"\bfast\b", re.I),
     "'fast' is subjective",
     "Assumed moderately fast; specify a concrete speed if exact timing matters"),
    (re.compile(r"\bslow\b", re.I),
     "'slow' is subjective",
     "Assumed moderately slow; specify a concrete duration if exact timing matters"),
    (re.compile(r"\bsmooth\b", re.I),
     "'smooth' is vague",
     "Assumed CSS/JS easing (ease-in-out) as default; override with explicit easing function if needed"),
]


# ---------------------------------------------------------------------------
# Normaliser
# ---------------------------------------------------------------------------

class VisualRequirementNormalizer:
    """
    Converts raw user requirement text into a NormalizedVisualRequirement.

    Pure keyword/regex extraction — deterministic, no LLM. The normalizer:
    - Captures which phrases triggered each inference (source_phrases)
    - Records explicit assumptions when safe defaults are chosen
    - Flags clarification_required only when ambiguity affects file scope,
      runtime permissions, or destructive behaviour
    """

    def normalize(self, raw: str) -> NormalizedVisualRequirement:
        text = raw or ""
        result = NormalizedVisualRequirement(raw_requirement=text)
        seen_artifact_hints: set[str] = set()
        seen_runtime: set[str] = set()

        # --- Artifact type hints ---
        for pattern, hint, rt_flags in _ARTIFACT_HINTS:
            m = pattern.search(text)
            if m and hint not in seen_artifact_hints:
                seen_artifact_hints.add(hint)
                result.artifact_type_hints.append(hint)
                result.source_phrases.append(m.group(0))
                for flag in rt_flags:
                    if flag not in seen_runtime:
                        seen_runtime.add(flag)
                        result.runtime_requirements.append(flag)

        # --- Animation / motion triggers browser_required ---
        _any_anim = False

        # --- Motion types ---
        # Pre-compute positions consumed by hue-rotate color phrases so the
        # word "rotate" is not double-counted as spatial motion.
        _hue_rotate_spans: list[tuple[int, int]] = [
            m.span()
            for m in re.finditer(r"\bhue[\s\-]?rotat\w*", text, re.I)
        ]

        def _in_hue_rotate(match: re.Match) -> bool:
            s, e = match.span()
            return any(hs <= s and e <= he for hs, he in _hue_rotate_spans)

        seen_motion: set[str] = set()
        for pattern, name in _MOTION_PATTERNS:
            m = pattern.search(text)
            if m and name not in seen_motion and not _in_hue_rotate(m):
                seen_motion.add(name)
                result.motion_types.append(name)
                result.source_phrases.append(m.group(0))
                _any_anim = True

        # --- Color types ---
        seen_color: set[str] = set()
        for pattern, name in _COLOR_PATTERNS:
            m = pattern.search(text)
            if m and name not in seen_color:
                seen_color.add(name)
                result.color_types.append(name)
                result.source_phrases.append(m.group(0))
                _any_anim = True

        if _any_anim:
            if "animation_required" not in seen_runtime:
                seen_runtime.add("animation_required")
                result.runtime_requirements.append("animation_required")
            if "browser_required" not in seen_runtime:
                seen_runtime.add("browser_required")
                result.runtime_requirements.append("browser_required")

        # --- Interaction types ---
        seen_interaction: set[str] = set()
        for pattern, name, rt_flags in _INTERACTION_PATTERNS:
            m = pattern.search(text)
            if m and name not in seen_interaction:
                seen_interaction.add(name)
                result.interaction_types.append(name)
                result.source_phrases.append(m.group(0))
                for flag in rt_flags:
                    if flag not in seen_runtime:
                        seen_runtime.add(flag)
                        result.runtime_requirements.append(flag)

        # --- Frequency ---
        for pattern, converter in _FREQ_PATTERNS:
            m = pattern.search(text)
            if m:
                try:
                    result.animation_frequency_hz = converter(m)
                    result.source_phrases.append(m.group(0))
                    if "animation_required" not in seen_runtime:
                        seen_runtime.add("animation_required")
                        result.runtime_requirements.append("animation_required")
                except (ValueError, IndexError):
                    pass
                break

        # per-frame → runtime loop
        if re.search(r"\bper[\s\-]frame\b", text, re.I):
            result.source_phrases.append("per-frame")
            if "runtime_loop_required" not in seen_runtime:
                seen_runtime.add("runtime_loop_required")
                result.runtime_requirements.append("runtime_loop_required")

        # --- Duration ---
        for pattern, converter in _DUR_PATTERNS:
            m = pattern.search(text)
            if m:
                try:
                    result.animation_duration_seconds = converter(m)
                    result.source_phrases.append(m.group(0))
                    if "animation_required" not in seen_runtime:
                        seen_runtime.add("animation_required")
                        result.runtime_requirements.append("animation_required")
                except (ValueError, IndexError):
                    pass
                break

        # --- Rendering target (most specific wins) ---
        if "webgl" in seen_artifact_hints:
            result.rendering_target = "webgl"
        elif "canvas" in seen_artifact_hints:
            result.rendering_target = "canvas"
        elif "svg" in seen_artifact_hints:
            result.rendering_target = "svg"
        elif "html_page" in seen_artifact_hints:
            result.rendering_target = "html"

        # --- Ambiguous terms ---
        for pattern, ambiguity_desc, assumption_text in _AMBIGUOUS_PATTERNS:
            if pattern.search(text):
                result.unresolved_ambiguities.append(ambiguity_desc)
                result.assumptions.append(assumption_text)
                # Cosmetic ambiguities do not require clarification
                result.confidence = min(result.confidence, 0.8)

        # --- browser_required is implied by any visual output ---
        if result.artifact_type_hints and "browser_required" not in seen_runtime:
            seen_runtime.add("browser_required")
            result.runtime_requirements.append("browser_required")

        # Deduplicate source phrases (keep order)
        seen_phrases: set[str] = set()
        deduped: list[str] = []
        for p in result.source_phrases:
            lp = p.lower()
            if lp not in seen_phrases:
                seen_phrases.add(lp)
                deduped.append(p)
        result.source_phrases = deduped

        return result
