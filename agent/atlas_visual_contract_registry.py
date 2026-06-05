"""
Visual contract registry for Atlas.

A VisualContract defines what must be true for a generated browser artifact to
satisfy the visual requirement.  Contract selection is deterministic: the same
VisualTaskClassification always produces the same contract_id.

Seven built-in contracts cover the full range of common artifact types.  The
registry is conservative by default: unknown or low-confidence classifications
fall back to the minimal static_html_visual_v1 contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from agent.atlas_visual_task_classifier import VisualTaskClassification


# ---------------------------------------------------------------------------
# Contract model
# ---------------------------------------------------------------------------

@dataclass
class VisualContract:
    contract_id: str
    display_name: str
    required_signals: list[str]
    optional_signals: list[str]
    # Signals that are NEVER expected for this artifact type — if the verifier
    # or repair planner tries to check/suggest them, that is a bug.
    forbidden_signals: list[str]
    # "static_only"    — browser smoke is not needed
    # "smoke_optional" — smoke test adds confidence but is not required
    # "smoke_required" — must run browser smoke to satisfy contract
    verification_method: str
    repair_profile: str
    # Template used to generate human-readable failure messages.
    # Use {signal} placeholder for the failed signal name.
    failure_message_template: str
    description: str = ""


# ---------------------------------------------------------------------------
# Built-in contracts
# ---------------------------------------------------------------------------

_CONTRACTS: dict[str, VisualContract] = {}


def _reg(c: VisualContract) -> VisualContract:
    _CONTRACTS[c.contract_id] = c
    return c


_reg(VisualContract(
    contract_id="static_html_visual_v1",
    display_name="Static HTML visual",
    description="Plain HTML page with text/structure but no animation requirement.",
    required_signals=["page_loads", "expected_structure"],
    optional_signals=["expected_text", "accessibility_labels"],
    forbidden_signals=[
        "animation_signal", "canvas_exists", "game_loop_runs",
        "frame_changes_over_time", "hud_exists", "input_handling_exists",
    ],
    verification_method="static_only",
    repair_profile="static_html_repair",
    failure_message_template="Static HTML contract failed: {signal} was not satisfied.",
))

_reg(VisualContract(
    contract_id="animated_dom_visual_v1",
    display_name="Animated DOM visual",
    description=(
        "HTML page with CSS/JS animation — colour change, motion, or transform over time. "
        "No canvas or gameplay required."
    ),
    required_signals=["page_loads", "animation_signal", "style_change_over_time"],
    optional_signals=[
        "expected_text", "color_change_detectable", "motion_detectable",
        "wave_phase_detectable", "reduced_motion_support",
    ],
    forbidden_signals=[
        "canvas_exists", "game_loop_runs", "hud_exists",
        "input_handling_exists", "collision_detection",
    ],
    verification_method="smoke_optional",
    repair_profile="animated_dom_repair",
    failure_message_template="Animated DOM contract failed: {signal} was not detected.",
))

_reg(VisualContract(
    contract_id="ui_component_visual_v1",
    display_name="UI component",
    description=(
        "A UI component such as a form, widget, panel, or modal. "
        "Requires controls to exist; interaction is verified only when requested."
    ),
    required_signals=["page_loads", "required_controls_exist"],
    optional_signals=[
        "accessibility_labels", "aria_attributes", "keyboard_focusable",
        "state_changes_on_interaction",
    ],
    forbidden_signals=[
        "game_loop_runs", "canvas_exists", "hud_exists", "collision_detection",
    ],
    verification_method="smoke_optional",
    repair_profile="ui_component_repair",
    failure_message_template="UI component contract failed: {signal} was not satisfied.",
))

_reg(VisualContract(
    contract_id="interactive_web_app_visual_v1",
    display_name="Interactive web app",
    description=(
        "A web application with state, routing, or significant user interaction. "
        "Key interactions must change visible state."
    ),
    required_signals=[
        "page_loads", "controls_exist", "state_changes_on_interaction",
    ],
    optional_signals=["accessibility_labels", "keyboard_navigable", "reduced_motion_support"],
    forbidden_signals=["game_loop_runs", "hud_exists", "collision_detection"],
    verification_method="smoke_required",
    repair_profile="interactive_web_app_repair",
    failure_message_template="Interactive web app contract failed: {signal} was not satisfied.",
))

_reg(VisualContract(
    contract_id="canvas_animation_visual_v1",
    display_name="Canvas animation",
    description=(
        "A <canvas> animation (particles, physics, drawing loop). "
        "Input handling and gameplay are NOT required unless explicitly requested."
    ),
    required_signals=["canvas_exists", "frame_changes_over_time"],
    optional_signals=[
        "rendering_context_initialised", "animation_signal",
        "motion_detectable", "color_change_detectable",
    ],
    forbidden_signals=[
        "game_loop_runs", "hud_exists", "input_handling_exists",
        "collision_detection", "score_exists", "lives_exists",
    ],
    verification_method="smoke_required",
    repair_profile="canvas_animation_repair",
    failure_message_template="Canvas animation contract failed: {signal} was not detected.",
))

_reg(VisualContract(
    contract_id="canvas_game_visual_v1",
    display_name="Canvas game",
    description=(
        "A browser game with game loop, input, and game state. "
        "Collision and HUD are only verified when they are part of the requirement."
    ),
    required_signals=["canvas_exists", "game_loop_runs", "frame_changes_over_time"],
    optional_signals=[
        "input_handling_exists", "score_exists", "hud_exists",
        "collision_detection", "lives_exists",
    ],
    forbidden_signals=[],
    verification_method="smoke_required",
    repair_profile="canvas_game_repair",
    failure_message_template="Canvas game contract failed: {signal} was not satisfied.",
))

_reg(VisualContract(
    contract_id="chart_visualization_v1",
    display_name="Chart / data visualisation",
    description=(
        "A chart or data visualisation (bar, line, pie, scatter, etc.). "
        "Axes, labels, and legend are checked when present in the requirement."
    ),
    required_signals=["page_loads", "chart_element_exists", "data_points_visible"],
    optional_signals=[
        "axes_exist", "labels_exist", "legend_exists",
        "tooltip_on_hover", "accessible_description",
    ],
    forbidden_signals=[
        "animation_signal", "game_loop_runs", "canvas_exists",
        "hud_exists", "input_handling_exists",
    ],
    verification_method="smoke_optional",
    repair_profile="chart_repair",
    failure_message_template="Chart contract failed: {signal} was not found.",
))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class VisualContractRegistry:
    """
    Selects the appropriate VisualContract for a given VisualTaskClassification.

    Selection is deterministic — same input always yields same contract_id.
    Falls back to the conservative static_html_visual_v1 for unknown or
    low-confidence classifications.
    """

    # Direct mapping from artifact_type to contract_id
    _ARTIFACT_MAP: dict[str, str] = {
        "static_html_page":    "static_html_visual_v1",
        "animated_html_page":  "animated_dom_visual_v1",
        "ui_component":        "ui_component_visual_v1",
        "interactive_web_app": "interactive_web_app_visual_v1",
        "canvas_animation":    "canvas_animation_visual_v1",
        "canvas_game":         "canvas_game_visual_v1",
        "svg_visualization":   "animated_dom_visual_v1",   # DOM-style contract; no canvas
        "chart_visualization": "chart_visualization_v1",
        "document":            "static_html_visual_v1",
        "test_only":           "static_html_visual_v1",
        "unknown":             "static_html_visual_v1",
    }

    _FALLBACK_CONTRACT_ID = "static_html_visual_v1"
    _LOW_CONFIDENCE_THRESHOLD = 0.4

    def select(self, classification: VisualTaskClassification) -> VisualContract:
        """Return the appropriate contract for the given classification."""
        # Safety guards — never escalate to complex contracts on low confidence
        if classification.confidence < self._LOW_CONFIDENCE_THRESHOLD:
            return _CONTRACTS[self._FALLBACK_CONTRACT_ID]

        # Never select canvas_game unless explicitly classified as such
        if (
            classification.artifact_type != "canvas_game"
            and "canvas_game_visual_v1" == self._ARTIFACT_MAP.get(
                classification.artifact_type, self._FALLBACK_CONTRACT_ID
            )
        ):
            return _CONTRACTS[self._FALLBACK_CONTRACT_ID]

        # Never select canvas_animation unless canvas_required is in runtime requirements
        if (
            classification.artifact_type == "canvas_animation"
            and "canvas_required" not in classification.runtime_requirements
        ):
            # Demote to animated DOM contract
            return _CONTRACTS["animated_dom_visual_v1"]

        contract_id = self._ARTIFACT_MAP.get(
            classification.artifact_type, self._FALLBACK_CONTRACT_ID
        )
        return _CONTRACTS.get(contract_id, _CONTRACTS[self._FALLBACK_CONTRACT_ID])

    def get(self, contract_id: str) -> VisualContract | None:
        """Retrieve a contract by ID. Returns None if not found."""
        return _CONTRACTS.get(contract_id)

    def all_ids(self) -> list[str]:
        return list(_CONTRACTS.keys())

    def all_contracts(self) -> list[VisualContract]:
        return list(_CONTRACTS.values())
