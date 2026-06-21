"""TA15: Default generation routing presets.

Explicit, auditable safe-default route/method/Twin-injection recommendations for when a
model is unbenchmarked or Forge optimal routing is OFF. These are descriptive/preview
only — RouteMatrix and ExecutionPolicySelector keep execution authority — but they let the
UI/API show "if there is no benchmark, this is the safe fallback" and let a test assert the
presets never contradict the RouteMatrix safe candidate set.
"""
from __future__ import annotations

from copy import deepcopy

from agent.model_forge.route_matrix import ChangeClass, RouteMatrix
from agent.model_forge.route_taxonomy import ForgeRoute

# Routes that must never be used for a large/critical change (unsafe micro edits).
UNSAFE_MICRO_ROUTES_FOR_LARGE = {"deterministic", "direct_patch", "micro_patch"}

DEFAULT_GENERATION_PRESETS: dict[str, dict[str, dict[str, object]]] = {
    "unbenchmarked_safe": {
        "trivial": {"route": "deterministic", "method": "deterministic_text_patch", "injection": 0},
        "micro": {"route": "micro_patch", "method": "structured_patch_json", "injection": 1},
        "small": {"route": "direct_patch", "method": "structured_patch_json", "injection": 2},
        "medium": {"route": "patch_dsl", "method": "patch_dsl_json", "injection": 2},
        "large": {"route": "sliced_impact", "method": "structured_patch_json", "injection": 3},
        "critical": {"route": "critical_gate", "method": "review_only", "injection": 4},
        "greenfield": {"route": "greenfield_skeleton", "method": "structured_patch_json", "injection": 4},
    },
}

# Advisory note for the OFF case (route stays the RouteMatrix default; profile may still
# adjust method/injection).
OPTIMAL_ROUTING_OFF_NOTE = (
    "same_as_route_matrix_default_but_profile_can_adjust_method_and_injection"
)


def default_generation_presets() -> dict:
    """Return a deep copy of the presets plus the optimal-routing-off note."""
    return {
        "presets": deepcopy(DEFAULT_GENERATION_PRESETS),
        "optimal_routing_off": OPTIMAL_ROUTING_OFF_NOTE,
    }


def validate_presets_against_route_matrix(matrix: RouteMatrix | None = None) -> list[str]:
    """Return a list of violations where a preset route is not a RouteMatrix safe candidate
    for that change class (or is a forbidden/unsafe route). Empty list == consistent."""
    matrix = matrix or RouteMatrix()
    violations: list[str] = []
    for preset_name, by_class in DEFAULT_GENERATION_PRESETS.items():
        for class_name, spec in by_class.items():
            try:
                change = ChangeClass(class_name)
                route = ForgeRoute(str(spec["route"]))
            except ValueError:
                violations.append(f"{preset_name}.{class_name}: invalid change_class or route")
                continue
            entry = matrix.entry(change)
            candidates = set(entry.candidate_routes)
            forbidden = set(entry.forbidden_routes)
            if route in forbidden:
                violations.append(f"{preset_name}.{class_name}: route {route.value} is forbidden")
            elif route not in candidates:
                violations.append(
                    f"{preset_name}.{class_name}: route {route.value} not in safe candidates "
                    f"{[r.value for r in entry.candidate_routes]}"
                )
            if entry.critical_gate_required and route != ForgeRoute.CRITICAL_GATE:
                violations.append(f"{preset_name}.{class_name}: critical change must use critical_gate")
            if change in {ChangeClass.LARGE, ChangeClass.CRITICAL} and route.value in UNSAFE_MICRO_ROUTES_FOR_LARGE:
                violations.append(f"{preset_name}.{class_name}: unsafe micro route {route.value} for {class_name}")
    return violations


__all__ = [
    "DEFAULT_GENERATION_PRESETS",
    "OPTIMAL_ROUTING_OFF_NOTE",
    "UNSAFE_MICRO_ROUTES_FOR_LARGE",
    "default_generation_presets",
    "validate_presets_against_route_matrix",
]
