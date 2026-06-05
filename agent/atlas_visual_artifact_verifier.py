"""
Static contract verifier for HTML/CSS/JS visual artifacts.

Observable data-atlas-* attributes that generated artifacts may expose:
  data-atlas-animation-running  — "true" when animation is active
  data-atlas-motion-phase       — current phase value (e.g. "0.42")
  data-atlas-color-phase        — current hue/color phase value
  data-atlas-state              — current component/game state label
  data-atlas-frame              — integer frame counter (incremented each rAF tick)
  data-atlas-interaction-state  — describes the last interaction result
  data-atlas-contract           — the contract_id this artifact targets

These attributes are non-invasive verification aids.  Their presence is optional
in hand-written code; Atlas-generated artifacts should expose them when runtime
behavior must be detected.  The verifier supports both explicit attributes and
computed browser state (style, transform, colour, canvas pixels).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from agent.atlas_artifact_asset_utils import collect_linked_asset_text

if TYPE_CHECKING:
    from agent.atlas_visual_contract_registry import VisualContract

# Static signals checked in HTML/CSS/JS visual artifacts
_ANIMATION_SIGNALS = [
    (re.compile(r'\brequestAnimationFrame\b'), 'requestAnimationFrame'),
    (re.compile(r'@keyframes\s+\w+', re.IGNORECASE), 'css_keyframes'),
    (re.compile(r'\banimation\s*:', re.IGNORECASE), 'css_animation'),
    (re.compile(r'\btransition(?:-property)?\s*:', re.IGNORECASE), 'css_transition'),
    (re.compile(r'<\s*(?:animate|animateTransform|animateMotion|set)\b', re.IGNORECASE), 'svg_smil_animation'),
]
_COLOR_SIGNALS = [
    (re.compile(r'\bstyle\.setProperty\s*\(\s*[\'"]--[^\'"]*(?:color|hue|fill)', re.IGNORECASE), 'style_setProperty_color'),
    (re.compile(r'\bstyle\.(?:color|backgroundColor|background)\s*=', re.IGNORECASE), 'style_color_assignment'),
    (re.compile(r'\bhsl\s*\(', re.IGNORECASE), 'hsl'),
    (re.compile(r'\brgb\s*\(', re.IGNORECASE), 'rgb'),
    (re.compile(r'style\.color\b'), 'style_color'),
    (re.compile(r'--[a-z][\w-]*(?:color|hue|fill)[^:]*:', re.IGNORECASE), 'css_color_variable'),
    (re.compile(r'\bhue-rotate\b'), 'hue_rotate'),
]
_MOTION_SIGNALS = [
    (re.compile(r'\bstyle\.transform\s*=', re.IGNORECASE), 'style_transform_assignment'),
    (re.compile(r'\btransform\s*[:(]', re.IGNORECASE), 'transform'),
    (re.compile(r'<\s*animateTransform\b|<\s*animateMotion\b', re.IGNORECASE), 'svg_smil_motion'),
    (re.compile(r'\btranslate[XYZ]?\s*\(', re.IGNORECASE), 'translate'),
    (re.compile(r'\bcanvas\b.*\bcontext\b|\bgetContext\s*\(', re.IGNORECASE), 'canvas_context'),
]
_WAVE_PHASE_SIGNALS = [
    (re.compile(r'\bMath\.sin\b'), 'math_sin'),
    (re.compile(r'\bMath\.cos\b'), 'math_cos'),
    (re.compile(r'\bphase\b', re.IGNORECASE), 'phase'),
    (re.compile(r'\bamplitude\b', re.IGNORECASE), 'amplitude'),
    (re.compile(r'\bfrequency\b', re.IGNORECASE), 'frequency'),
    # CSS-based wave: translateY with a numeric offset (pre-calculated sine values in @keyframes)
    (re.compile(r'\btranslateY\s*\(\s*-?\d+(?:\.\d+)?(?:px|em|rem|%|vh)?\s*\)', re.IGNORECASE), 'css_translateY_offset'),
    # Any direct sin() call (e.g. in CSS calc() or GLSL)
    (re.compile(r'\bsin\s*\(', re.IGNORECASE), 'sin_call'),
]

# Keywords that suggest an animation task in task_description / goal
_ANIMATION_TASK_KEYWORDS = re.compile(
    r'\b(animat\w*|wave\w*|oscillat\w*|bounce\w*|spin\w*|rotat\w*|pulse\w*|fade\w*|mov\w*|motion|color\s*chang\w*|hue)\b',
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
    r'\b(mov\w*|motion|wave\w*|oscillat\w*|bounce\w*|spin\w*|rotat\w*|slide\w*|drift\w*|orbit\w*|translat\w*|scroll\w*|fall\w*|jump\w*|fly\w*|shake\w*|swing\w*)\b',
    re.IGNORECASE,
)
_HUE_ROTATE_TASK_KEYWORDS = re.compile(r'\bhue\s*-?\s*rotat\w*\b', re.IGNORECASE)


def _is_animation_task_description(task_description: str) -> bool:
    return bool(_ANIMATION_TASK_KEYWORDS.search(task_description or ""))


def _wants_color_task(task_description: str) -> bool:
    return bool(_COLOR_TASK_KEYWORDS.search(task_description or ""))


def _wants_motion_task(task_description: str) -> bool:
    text = task_description or ""
    if _HUE_ROTATE_TASK_KEYWORDS.search(text):
        return False
    return bool(_MOTION_TASK_KEYWORDS.search(text))


class AtlasVisualArtifactVerifier:
    """Static contract verifier for HTML/CSS/JS visual artifacts.

    File existence alone is never a pass. This checks structural signals
    for animation, color mutation, motion, and wave/phase.

    When a VisualContract is supplied the verifier selects required checks from
    contract.required_signals and skips signals listed in contract.forbidden_signals.
    When contract is None the legacy keyword-based behaviour is used, ensuring
    no regressions for callers that have not yet been updated.
    """

    def verify_static(
        self,
        html_path: str | Path,
        *,
        task_description: str = "",
        contract: "VisualContract | None" = None,
        extra_required_signals: list[str] | None = None,
    ) -> dict:
        html_path = Path(html_path)
        if not html_path.exists():
            return self._result("failed", checks=[], missing=["html_file_missing"],
                                contract_id=contract.contract_id if contract else None)

        try:
            html_content = html_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return self._result("failed", checks=[], missing=[f"html_read_error: {exc}"],
                                contract_id=contract.contract_id if contract else None)

        # Generated apps routinely split logic into external files (e.g. index.html +
        # js/game.js + css/style.css), so the animation/color/motion signals live outside
        # the entry HTML. Scan the linked/sibling CSS & JS too — checking only the HTML
        # produces a false-negative "visual_contract_failed" for any multi-file artifact.
        content = html_content + "\n" + collect_linked_asset_text(html_path, html_content)

        # When a contract is provided, use its required/forbidden signals to gate checks.
        if contract is not None:
            return self._verify_with_contract(
                content, html_path, contract, task_description,
                extra_required_signals=extra_required_signals or [],
            )

        # Legacy keyword-based path (backwards compatible).
        task_desc = task_description.lower()
        is_animation_task = _is_animation_task_description(task_desc)
        is_wave_task = bool(_WAVE_TASK_KEYWORDS.search(task_desc))
        wants_color = _wants_color_task(task_desc)
        wants_motion = _wants_motion_task(task_desc)

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
        color_found = (
            self._check_signals(content, _COLOR_SIGNALS)
            or self._keyframe_color_mutation(content)
            or self._transition_color_mutation(content)
        )
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

    # ------------------------------------------------------------------
    # Contract-aware verification path
    # ------------------------------------------------------------------

    def _verify_with_contract(
        self,
        content: str,
        html_path: Path,
        contract: "VisualContract",
        task_description: str = "",
        extra_required_signals: list[str] | None = None,
    ) -> dict:
        """
        Verify against an explicit VisualContract.

        Signals in contract.required_signals and extra_required_signals are
        mandatory.  Signals in contract.forbidden_signals are skipped entirely.
        This prevents cross-contamination (e.g. animation tasks do not receive
        canvas/game checks; static tasks do not receive animation checks).

        extra_required_signals lets the caller promote task-specific optional
        signals to required (e.g. motion_detectable when motion is requested).
        """
        checks: list[dict] = []
        missing: list[str] = []
        forbidden = set(contract.forbidden_signals)
        # Merge contract required + caller overrides (minus forbidden)
        req = set(contract.required_signals) | set(extra_required_signals or [])
        req -= forbidden

        def _record_static(name: str, found: str | None, *, required: bool) -> None:
            if name in forbidden:
                return  # skip — not relevant for this artifact type
            if found:
                checks.append({"check": name, "status": "passed", "detail": found})
            elif required:
                checks.append({"check": name, "status": "failed", "detail": None})
                missing.append(name)
            else:
                checks.append({"check": name, "status": "advisory", "detail": None})

        # page_loads — file exists (already confirmed by the caller)
        if "page_loads" not in forbidden:
            checks.append({"check": "page_loads", "status": "passed", "detail": "file_exists"})

        # expected_structure — any body content present
        if "expected_structure" in req or "expected_structure" not in forbidden:
            has_body = bool(re.search(r'<body\b[^>]*>.*?</body>', content, re.I | re.S))
            required_struct = "expected_structure" in req
            _record_static("expected_structure", "body_found" if has_body else None,
                           required=required_struct)

        # animation_signal
        if "animation_signal" not in forbidden:
            anim_found = self._check_signals(content, _ANIMATION_SIGNALS)
            _record_static("animation_signal", anim_found, required="animation_signal" in req)

        # color_change_detectable
        if "color_change_detectable" not in forbidden:
            color_found = (
                self._check_signals(content, _COLOR_SIGNALS)
                or self._keyframe_color_mutation(content)
                or self._transition_color_mutation(content)
            )
            _record_static("color_change_detectable", color_found,
                           required="color_change_detectable" in req)

        # motion_detectable
        if "motion_detectable" not in forbidden:
            motion_found = self._check_signals(content, _MOTION_SIGNALS)
            _record_static("motion_detectable", motion_found, required="motion_detectable" in req)

        # wave_phase_detectable
        if "wave_phase_detectable" not in forbidden:
            wave_found = self._check_signals(content, _WAVE_PHASE_SIGNALS)
            _record_static("wave_phase_detectable", wave_found,
                           required="wave_phase_detectable" in req)

        # canvas_exists — presence of <canvas> tag or getContext() call
        if "canvas_exists" not in forbidden:
            canvas_found = bool(
                re.search(r'<canvas\b', content, re.I)
                or re.search(r'\bgetContext\s*\(', content, re.I)
            )
            _record_static("canvas_exists", "canvas_tag_or_context" if canvas_found else None,
                           required="canvas_exists" in req)

        # chart_element_exists
        if "chart_element_exists" not in forbidden:
            chart_found = bool(
                re.search(r'<svg\b', content, re.I)
                or re.search(r'\bnew\s+Chart\s*\(', content, re.I)
                or re.search(r'\becharts\b|\bplotly\b|\bd3\b', content, re.I)
                or re.search(r'canvas[^>]*id=["\']chart', content, re.I)
            )
            _record_static("chart_element_exists",
                           "chart_element_found" if chart_found else None,
                           required="chart_element_exists" in req)

        # data_points_visible — any numeric data binding pattern
        if "data_points_visible" not in forbidden:
            data_found = bool(
                re.search(r'data\s*:\s*\[', content, re.I)
                or re.search(r'\b(labels|datasets|series|values)\s*:', content, re.I)
            )
            _record_static("data_points_visible",
                           "data_binding_found" if data_found else None,
                           required="data_points_visible" in req)

        # required_controls_exist — buttons, inputs, selects
        if "required_controls_exist" not in forbidden:
            controls_found = bool(
                re.search(r'<button\b|<input\b|<select\b|<textarea\b', content, re.I)
            )
            _record_static("required_controls_exist",
                           "controls_found" if controls_found else None,
                           required="required_controls_exist" in req)

        status = "failed" if missing else "passed"
        return self._result(status, checks=checks, missing=missing,
                            contract_id=contract.contract_id)

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

    def _transition_color_mutation(self, content: str) -> str | None:
        """Detect CSS transitions whose property list includes color mutation."""
        transition_patterns = (
            r'\btransition\s*:\s*[^;{}]*(?:background-)?color\b',
            r'\btransition-property\s*:\s*[^;{}]*(?:background-)?color\b',
        )
        for pattern in transition_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return 'transition_color_mutation'
        return None

    @staticmethod
    def _result(
        status: str,
        *,
        checks: list,
        missing: list,
        contract_id: str | None = None,
    ) -> dict:
        result = {"status": status, "checks": checks, "missing": missing}
        if contract_id is not None:
            result["contract_id"] = contract_id
        return result
