from __future__ import annotations

import re
from pathlib import Path

from agent.atlas_artifact_asset_utils import collect_linked_asset_text

# Static signals checked in HTML/CSS/JS visual artifacts
_ANIMATION_SIGNALS = [
    (re.compile(r'\brequestAnimationFrame\b'), 'requestAnimationFrame'),
    (re.compile(r'@keyframes\s+\w+', re.IGNORECASE), 'css_keyframes'),
]
_COLOR_SIGNALS = [
    (re.compile(r'\bhsl\s*\(', re.IGNORECASE), 'hsl'),
    (re.compile(r'\brgb\s*\(', re.IGNORECASE), 'rgb'),
    (re.compile(r'style\.color\b'), 'style_color'),
    (re.compile(r'--[a-z][\w-]*(?:color|hue|fill)[^:]*:', re.IGNORECASE), 'css_color_variable'),
    (re.compile(r'\bhue-rotate\b'), 'hue_rotate'),
]
_MOTION_SIGNALS = [
    (re.compile(r'\btransform\s*[:(]', re.IGNORECASE), 'transform'),
    (re.compile(r'\btranslate[XYZ]?\s*\(', re.IGNORECASE), 'translate'),
    (re.compile(r'\bcanvas\b.*\bcontext\b|\bgetContext\s*\(', re.IGNORECASE), 'canvas_context'),
]
_WAVE_PHASE_SIGNALS = [
    (re.compile(r'\bMath\.sin\b'), 'math_sin'),
    (re.compile(r'\bMath\.cos\b'), 'math_cos'),
    (re.compile(r'\bphase\b', re.IGNORECASE), 'phase'),
    (re.compile(r'\bamplitude\b', re.IGNORECASE), 'amplitude'),
    (re.compile(r'\bfrequency\b', re.IGNORECASE), 'frequency'),
]

# Keywords that suggest an animation task in task_description / goal
_ANIMATION_TASK_KEYWORDS = re.compile(
    r'\b(animat|wave|oscillat|bounce|spin\w*|rotat|pulse|fade|mov\w+|motion|color\s*chang|hue)',
    re.IGNORECASE,
)
_WAVE_TASK_KEYWORDS = re.compile(
    r'\b(wave|sine|sinusoid|oscillat|linear.?phase|phase.?shift)',
    re.IGNORECASE,
)
_COLOR_TASK_KEYWORDS = re.compile(
    r'\b(colou?r|hue|rainbow|gradient|chromat|tint|palette|spectrum)',
    re.IGNORECASE,
)
_MOTION_TASK_KEYWORDS = re.compile(
    r'\b(mov\w*|motion|wave|oscillat|bounce|spin\w*|rotat\w*|slide|drift|orbit|translat\w*|scroll|fall\w*|jump\w*|fly\w*|shake|swing)',
    re.IGNORECASE,
)


class AtlasVisualArtifactVerifier:
    """Static contract verifier for HTML/CSS/JS visual artifacts.

    File existence alone is never a pass. This checks structural signals
    for animation, color mutation, motion, and wave/phase.
    """

    def verify_static(self, html_path: str | Path, *, task_description: str = "") -> dict:
        html_path = Path(html_path)
        if not html_path.exists():
            return self._result("failed", checks=[], missing=["html_file_missing"])

        try:
            html_content = html_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return self._result("failed", checks=[], missing=[f"html_read_error: {exc}"])

        # Generated apps routinely split logic into external files (e.g. index.html +
        # js/game.js + css/style.css), so the animation/color/motion signals live outside
        # the entry HTML. Scan the linked/sibling CSS & JS too — checking only the HTML
        # produces a false-negative "visual_contract_failed" for any multi-file artifact.
        content = html_content + "\n" + collect_linked_asset_text(html_path, html_content)

        task_desc = task_description.lower()
        is_animation_task = bool(_ANIMATION_TASK_KEYWORDS.search(task_desc))
        is_wave_task = bool(_WAVE_TASK_KEYWORDS.search(task_desc))
        wants_color = bool(_COLOR_TASK_KEYWORDS.search(task_desc))
        wants_motion = bool(_MOTION_TASK_KEYWORDS.search(task_desc))

        checks: list[dict] = []
        missing: list[str] = []

        def _record(name: str, found: str | None, *, required: bool) -> None:
            if found:
                checks.append({"check": name, "status": "passed", "detail": found})
            elif required:
                checks.append({"check": name, "status": "failed", "detail": None})
                missing.append(name)
            else:
                checks.append({"check": name, "status": "advisory", "detail": None})

        # 1. Animation signal (required for animation tasks; advisory for all)
        anim_found = self._check_signals(content, _ANIMATION_SIGNALS)
        if is_animation_task:
            if anim_found:
                checks.append({"check": "animation_signal", "status": "passed", "detail": anim_found})
            else:
                checks.append({"check": "animation_signal", "status": "failed", "detail": None})
                missing.append("animation_signal")
        else:
            checks.append({"check": "animation_signal", "status": "passed" if anim_found else "advisory",
                           "detail": anim_found})

        # 2. Color mutation signal (required only for animation tasks that ask for color)
        color_found = self._check_signals(content, _COLOR_SIGNALS) or self._keyframe_color_mutation(content)
        _record("color_mutation_signal", color_found, required=is_animation_task and wants_color)

        # 3. Motion signal (required only for animation tasks that ask for motion)
        motion_found = self._check_signals(content, _MOTION_SIGNALS)
        _record("motion_signal", motion_found, required=is_animation_task and wants_motion)
        if is_animation_task and not wants_color and not wants_motion and not (color_found or motion_found):
            checks.append({"check": "visual_change_signal", "status": "failed", "detail": None})
            missing.append("visual_change_signal")

        # 4. Wave/linear phase signal (required for wave tasks)
        if is_wave_task:
            wave_found = self._check_signals(content, _WAVE_PHASE_SIGNALS)
            if wave_found:
                checks.append({"check": "wave_phase_signal", "status": "passed", "detail": wave_found})
            else:
                checks.append({"check": "wave_phase_signal", "status": "failed", "detail": None})
                missing.append("wave_phase_signal")

        # 5. Abrupt value check for wave tasks (warn if no smooth progression)
        if is_wave_task and not self._check_signals(content, _WAVE_PHASE_SIGNALS):
            checks.append({"check": "smooth_phase_progression", "status": "warned",
                           "detail": "no Math.sin/phase/amplitude/frequency found"})

        if missing:
            status = "failed"
        else:
            status = "passed"

        return self._result(status, checks=checks, missing=missing)

    def _check_signals(self, content: str, signals: list) -> str | None:
        """Return the name of the first matching signal, or None."""
        for pattern, name in signals:
            if pattern.search(content):
                return name
        return None

    def _keyframe_color_mutation(self, content: str) -> str | None:
        """Detect named-color CSS mutations inside @keyframes blocks."""
        for match in re.finditer(r'@keyframes\s+[\w-]+\s*\{', content, re.IGNORECASE):
            start = match.end() - 1
            depth = 0
            block = content[start:]
            for i in range(start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        block = content[start:i + 1]
                        break
            values = re.findall(r'(?:background-)?color\s*:\s*([^;}\n]+)', block, re.IGNORECASE)
            if len({value.strip().lower() for value in values}) >= 2:
                return 'keyframe_color_mutation'
        return None

    @staticmethod
    def _result(status: str, *, checks: list, missing: list) -> dict:
        return {"status": status, "checks": checks, "missing": missing}
