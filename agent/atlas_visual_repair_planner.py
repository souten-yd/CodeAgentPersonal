"""
Task-aware repair planner for visual verification failures.

The repair profile is selected from the chosen VisualContract — not inferred
from error text — so repair guidance is always appropriate for the artifact type.

Key guarantees:
- Non-game contracts never produce game/canvas repair guidance.
- Static HTML contracts never suggest adding animation or game loops.
- Repair is bounded to changed_files only; no broad rewrites.
- Each instruction includes a rationale tied to the failed signal.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent.atlas_visual_contract_registry import VisualContract
from agent.atlas_visual_failure_taxonomy import VisualVerificationFailure
from agent.atlas_visual_task_classifier import VisualTaskClassification


# ---------------------------------------------------------------------------
# Repair profile definitions
# ---------------------------------------------------------------------------

@dataclass
class RepairInstruction:
    action: str       # short imperative
    rationale: str    # why this action addresses the failed signal
    signals: list[str] = field(default_factory=list)  # signals this helps fix


@dataclass
class RepairProfile:
    profile_id: str
    display_name: str
    do_instructions: list[RepairInstruction]
    # Hard "do not" list — prevents cross-contamination between artifact types
    do_not: list[str]
    # Whether the repair planner may attempt automatic repair without user approval
    auto_repair_default: bool = True
    # Hard limit on retry attempts for this profile
    max_retries: int = 2


_PROFILES: dict[str, RepairProfile] = {}


def _rp(p: RepairProfile) -> RepairProfile:
    _PROFILES[p.profile_id] = p
    return p


_rp(RepairProfile(
    profile_id="static_html_repair",
    display_name="Static HTML repair",
    do_instructions=[
        RepairInstruction(
            action="Add or restore the expected content / text",
            rationale="expected_structure requires the correct DOM elements to be present",
            signals=["expected_structure", "expected_text"],
        ),
        RepairInstruction(
            action="Fix invalid HTML syntax (unclosed tags, missing doctype)",
            rationale="page_loads requires valid HTML that the browser will parse correctly",
            signals=["page_loads"],
        ),
        RepairInstruction(
            action="Resolve load errors (missing linked CSS/JS files, broken paths)",
            rationale="page_loads can fail when linked assets are not found",
            signals=["page_loads", "browser_load_failed"],
        ),
    ],
    do_not=[
        "add animation or CSS transitions",
        "add requestAnimationFrame or animation loops",
        "add a game loop or canvas rendering",
        "add event listeners or interactivity unless explicitly requested",
        "add canvas or WebGL unless requested",
    ],
    auto_repair_default=True,
    max_retries=2,
))

_rp(RepairProfile(
    profile_id="animated_dom_repair",
    display_name="Animated DOM repair",
    do_instructions=[
        RepairInstruction(
            action="Ensure the animated element exists in the DOM",
            rationale="animation_signal requires a target element to animate",
            signals=["animation_signal", "expected_structure"],
        ),
        RepairInstruction(
            action=(
                "Add or fix the animation mechanism: @keyframes, CSS animation property, "
                "Web Animations API, or requestAnimationFrame loop changing style properties"
            ),
            rationale="animation_signal requires a detectable animation source",
            signals=["animation_signal"],
        ),
        RepairInstruction(
            action="Ensure style properties (transform, opacity, color, background-color) change over time",
            rationale="style_change_over_time requires at least one CSS property to differ between frames",
            signals=["style_change_over_time", "motion_not_detected", "color_change_not_detected"],
        ),
        RepairInstruction(
            action="Prefer transform/opacity for smooth animation (avoids layout thrashing)",
            rationale="Performance: transform and opacity are GPU-composited and do not trigger reflow",
            signals=["style_change_over_time"],
        ),
        RepairInstruction(
            action=(
                "Add @media (prefers-reduced-motion) support if the animation is continuous "
                "or decorative"
            ),
            rationale="Accessibility: reduced-motion support is expected for DOM animations",
            signals=["reduced_motion_support", "animation_signal", "style_change_over_time"],
        ),
        RepairInstruction(
            action=(
                "Expose data-atlas-animation-running='true' when the animation is active "
                "(optional but helps verification)"
            ),
            rationale="Observable signals allow verifiers to sample animation state directly",
            signals=["animation_signal", "runtime_signal_missing"],
        ),
    ],
    do_not=[
        "add a <canvas> element unless the requirement explicitly requests canvas",
        "add a game loop (score, lives, collision detection)",
        "add HUD elements (score display, health bar, game timer)",
        "add collision detection",
        "add keyboard/mouse input handlers unless interaction is requested",
        "use WebGL unless the requirement explicitly requests WebGL",
    ],
    auto_repair_default=True,
    max_retries=3,
))

_rp(RepairProfile(
    profile_id="ui_component_repair",
    display_name="UI component repair",
    do_instructions=[
        RepairInstruction(
            action="Add missing controls (buttons, inputs, selects, checkboxes)",
            rationale="required_controls_exist verifies that declared UI elements are present",
            signals=["required_controls_exist"],
        ),
        RepairInstruction(
            action="Add missing labels and aria-* attributes for interactive elements",
            rationale="Accessibility: form controls and buttons must have associated labels",
            signals=["accessibility_labels", "accessibility_check_failed"],
        ),
        RepairInstruction(
            action="Fix event binding so that declared interactions (click, change, submit) trigger state updates",
            rationale="state_changes_on_interaction requires the component to respond to events",
            signals=["state_changes_on_interaction", "interaction_not_detected"],
        ),
        RepairInstruction(
            action="Ensure keyboard focus management is correct (tab order, focus visible)",
            rationale="Keyboard navigability is required for interactive components",
            signals=["keyboard_focusable"],
        ),
    ],
    do_not=[
        "add a game loop or canvas element",
        "add collision detection or game state",
        "add HUD elements",
        "add canvas or WebGL unless explicitly requested",
    ],
    auto_repair_default=True,
    max_retries=2,
))

_rp(RepairProfile(
    profile_id="interactive_web_app_repair",
    display_name="Interactive web app repair",
    do_instructions=[
        RepairInstruction(
            action="Ensure all required controls and their initial states are present",
            rationale="controls_exist verifies the app renders its key UI elements",
            signals=["controls_exist"],
        ),
        RepairInstruction(
            action="Fix state management so key interactions update visible state",
            rationale="state_changes_on_interaction requires observable UI changes after user action",
            signals=["state_changes_on_interaction", "interaction_not_detected"],
        ),
        RepairInstruction(
            action="Verify routing works when multiple views are required",
            rationale="Navigation links must produce visible view changes",
            signals=["state_changes_on_interaction"],
        ),
    ],
    do_not=[
        "add a game loop or canvas element",
        "add collision detection or game mechanics",
        "add HUD elements",
    ],
    auto_repair_default=True,
    max_retries=2,
))

_rp(RepairProfile(
    profile_id="canvas_animation_repair",
    display_name="Canvas animation repair",
    do_instructions=[
        RepairInstruction(
            action="Ensure a <canvas> element is present with the correct id/dimensions",
            rationale="canvas_exists is the primary contract signal",
            signals=["canvas_exists"],
        ),
        RepairInstruction(
            action="Initialise the 2D or WebGL rendering context (getContext('2d') or getContext('webgl'))",
            rationale="rendering_context_initialised is required before any drawing can occur",
            signals=["rendering_context_initialised", "canvas_frame_not_detected"],
        ),
        RepairInstruction(
            action="Ensure the animation loop calls requestAnimationFrame and draws every frame",
            rationale="frame_changes_over_time requires the canvas pixel hash to differ between samples",
            signals=["frame_changes_over_time", "canvas_frame_not_detected"],
        ),
        RepairInstruction(
            action="Expose data-atlas-frame (incremented each frame) to aid verification sampling",
            rationale="Observable signals allow verifiers to detect animation without pixel diffing",
            signals=["frame_changes_over_time"],
        ),
        RepairInstruction(
            action="Bound the animation work (e.g. max particles, max iterations) to prevent runaway loops",
            rationale="Performance: unbounded canvas loops can stall verification or crash the tab",
            signals=["frame_changes_over_time"],
        ),
    ],
    do_not=[
        "add a game loop with score, lives, or level state",
        "add collision detection",
        "add HUD elements (score display, health bar, game timer)",
        "add keyboard/mouse input handling unless interaction is explicitly requested",
        "switch to DOM/CSS animation — canvas was requested",
    ],
    auto_repair_default=True,
    max_retries=3,
))

_rp(RepairProfile(
    profile_id="canvas_game_repair",
    display_name="Canvas game repair",
    do_instructions=[
        RepairInstruction(
            action="Ensure the game loop calls requestAnimationFrame and updates state each frame",
            rationale="game_loop_runs requires a running animation loop",
            signals=["game_loop_runs", "frame_changes_over_time"],
        ),
        RepairInstruction(
            action="Ensure input handling (keyboard / pointer) is wired to game state",
            rationale="Input is required for game_controls interaction intent",
            signals=["input_handling_exists"],
        ),
        RepairInstruction(
            action="Add collision detection only when the requirement includes it",
            rationale="Collision is an optional signal — only add when gameplay requires it",
            signals=["collision_detection"],
        ),
        RepairInstruction(
            action="Add score/HUD display only when the requirement includes score or status tracking",
            rationale="HUD is an optional signal — only add when score/lives/timer is required",
            signals=["score_exists", "hud_exists"],
        ),
    ],
    do_not=[],   # Game repair has no forbidden directions
    auto_repair_default=False,  # Game repairs are complex; prefer user review
    max_retries=2,
))

_rp(RepairProfile(
    profile_id="chart_repair",
    display_name="Chart / visualisation repair",
    do_instructions=[
        RepairInstruction(
            action="Ensure the chart element (SVG, canvas, or library root) is present",
            rationale="chart_element_exists is the primary contract signal",
            signals=["chart_element_exists"],
        ),
        RepairInstruction(
            action="Ensure data points, bars, lines, or slices are rendered",
            rationale="data_points_visible verifies the chart has actual data rendered",
            signals=["data_points_visible"],
        ),
        RepairInstruction(
            action="Add or fix axis labels, tick marks, and chart title when required",
            rationale="axes_exist and labels_exist are optional but expected when the requirement mentions them",
            signals=["axes_exist", "labels_exist"],
        ),
        RepairInstruction(
            action="Add a legend when multiple data series are present",
            rationale="legend_exists is expected when the chart has more than one series",
            signals=["legend_exists"],
        ),
    ],
    do_not=[
        "add requestAnimationFrame animation loops unless animation is requested",
        "add game loop or canvas game mechanics",
        "add collision detection or game state",
        "add HUD elements",
        "add input handling beyond tooltip/hover unless interaction is requested",
    ],
    auto_repair_default=True,
    max_retries=2,
))


# ---------------------------------------------------------------------------
# Repair plan output
# ---------------------------------------------------------------------------

@dataclass
class VisualRepairPlan:
    profile_id: str
    display_name: str
    instructions: list[dict]         # {action, rationale, relevant_signals}
    do_not: list[str]
    target_files: list[str]          # bounded to changed_files
    auto_repair_allowed: bool
    retry_allowed: bool
    max_retries: int
    rationale_per_failure: list[dict]  # {failed_signal, explanation, instruction}
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "display_name": self.display_name,
            "instructions": self.instructions,
            "do_not": self.do_not,
            "target_files": self.target_files,
            "auto_repair_allowed": self.auto_repair_allowed,
            "retry_allowed": self.retry_allowed,
            "max_retries": self.max_retries,
            "rationale_per_failure": self.rationale_per_failure,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class VisualRepairPlanner:
    """
    Produces a bounded, task-aware repair plan for a set of verification failures.

    Profile selection comes from contract.repair_profile — never from parsing
    error text.  The plan always lists what NOT to do so downstream agents
    cannot inadvertently introduce unrelated concepts.
    """

    def plan_repair(
        self,
        failures: list[VisualVerificationFailure],
        classification: VisualTaskClassification,
        contract: VisualContract,
        diagnostics: dict,
        changed_files: list[str],
    ) -> VisualRepairPlan:
        profile = _PROFILES.get(contract.repair_profile)
        warnings: list[str] = []

        if profile is None:
            # Unknown profile — safe fallback
            profile = _PROFILES["static_html_repair"]
            warnings.append(
                f"No repair profile found for '{contract.repair_profile}'; "
                "falling back to static_html_repair. Review the contract registry."
            )

        # Collect the set of failed signals across all failures
        failed_signals: set[str] = {f.failed_signal for f in failures}

        # Build rationale mapping: which instruction addresses which failure
        rationale_per_failure: list[dict] = []
        for failure in failures:
            matching = [
                instr for instr in profile.do_instructions
                if failure.failed_signal in instr.signals
                or any(s in failure.failed_signal for s in instr.signals)
            ]
            if not matching:
                # Fallback: include the first instruction as general guidance
                matching = profile.do_instructions[:1]
                warnings.append(
                    f"No specific instruction found for signal '{failure.failed_signal}'; "
                    "including general repair guidance."
                )
            rationale_per_failure.append({
                "failed_signal": failure.failed_signal,
                "explanation": failure.explanation,
                "instruction": matching[0].action if matching else "",
                "rationale": matching[0].rationale if matching else "",
            })

        # Filter instructions to those relevant to the actual failures
        # (always include all if failures are empty — general repair)
        if failed_signals:
            relevant_instructions = [
                instr for instr in profile.do_instructions
                if not instr.signals
                or any(sig in failed_signals for sig in instr.signals)
                or any(
                    any(fs in sig or sig in fs for fs in failed_signals)
                    for sig in instr.signals
                )
            ]
            if not relevant_instructions:
                relevant_instructions = profile.do_instructions
        else:
            relevant_instructions = profile.do_instructions

        # Limit to changed_files only
        target_files = _filter_target_files(changed_files, classification.artifact_type)
        if not target_files and changed_files:
            target_files = changed_files[:5]
            warnings.append(
                "Could not narrow target files by artifact type; "
                "using all changed files (limited to 5)."
            )

        # Determine auto_repair_allowed: profile default + per-failure overrides
        auto_repair_allowed = profile.auto_repair_default
        if any(not f.auto_repair_allowed for f in failures):
            auto_repair_allowed = False
            warnings.append(
                "One or more failures are marked auto_repair_allowed=False; "
                "repair requires user review."
            )

        return VisualRepairPlan(
            profile_id=profile.profile_id,
            display_name=profile.display_name,
            instructions=[
                {
                    "action": instr.action,
                    "rationale": instr.rationale,
                    "relevant_signals": instr.signals,
                }
                for instr in relevant_instructions
            ],
            do_not=list(profile.do_not),
            target_files=target_files,
            auto_repair_allowed=auto_repair_allowed,
            retry_allowed=True,
            max_retries=profile.max_retries,
            rationale_per_failure=rationale_per_failure,
            warnings=warnings,
        )


def _filter_target_files(changed_files: list[str], artifact_type: str) -> list[str]:
    """Return HTML/CSS/JS files from changed_files for browser artifact types."""
    if not changed_files:
        return []

    browser_types = {
        "static_html_page", "animated_html_page", "ui_component",
        "interactive_web_app", "canvas_animation", "canvas_game",
        "svg_visualization", "chart_visualization",
    }
    if artifact_type not in browser_types:
        return changed_files[:5]

    html_files = [f for f in changed_files if f.endswith((".html", ".htm"))]
    css_files = [f for f in changed_files if f.endswith(".css")]
    js_files = [f for f in changed_files if f.endswith((".js", ".ts", ".mjs"))]

    # Prioritise: HTML first, then JS, then CSS
    ordered = html_files + js_files + css_files
    # Dedup while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for f in ordered:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result or changed_files[:5]
