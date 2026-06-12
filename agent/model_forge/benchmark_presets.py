"""Benchmark preset registry and loader (PFG-13).

Selectable evaluation presets, one per task family (Quick / Web App / Game / UI / DB /
Repair / Greenfield). Pure data + validation — no model execution. Presets declare the
tasks, required evaluators, recommended routes, risk, runtime budget, and the profile
dimensions they exercise, so the Arena/UI can offer them and the evaluator/profile
store know what to score.
"""
from __future__ import annotations

from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import BenchmarkPreset

_BUILTIN_PRESETS: tuple[BenchmarkPreset, ...] = (
    BenchmarkPreset(
        preset_id="quick_standard", family_id="quick", display_name="Quick", category="quick", depth="quick",
        tasks=["json_dsl_adherence", "one_function_patch", "import_repair", "failure_classification"],
        required_evaluators=["format", "schema", "syntax", "focused_tests"],
        recommended_routes=[ForgeRoute.MICRO_PATCH, ForgeRoute.DIRECT_PATCH, ForgeRoute.PATCH_DSL],
        risk_level="low", runtime_budget_seconds=180,
        profile_dimensions=["json_dsl", "patch_generation", "speed"],
    ),
    BenchmarkPreset(
        preset_id="web_app_standard", family_id="web_app", display_name="Web App", category="web_app", depth="standard",
        tasks=["fastapi_route_add", "html_form_api_call"],
        required_evaluators=["syntax", "focused_tests", "api_smoke", "portal_preview"],
        recommended_routes=[ForgeRoute.PATCH_DSL, ForgeRoute.SLICED_IMPACT, ForgeRoute.TEST_FIRST],
        risk_level="medium", runtime_budget_seconds=600,
        profile_dimensions=["web_app", "api_backend", "multi_file"],
    ),
    BenchmarkPreset(
        preset_id="game_canvas_standard", family_id="game_canvas", display_name="Game / Canvas", category="game_canvas", depth="standard",
        tasks=["draw_loop", "input_handling", "collision", "score", "restart"],
        required_evaluators=["syntax", "focused_tests", "portal_preview", "visual_runtime"],
        recommended_routes=[ForgeRoute.PATCH_DSL, ForgeRoute.SLICED_IMPACT],
        risk_level="medium", runtime_budget_seconds=900,
        profile_dimensions=["game_canvas", "ui_visual", "multi_file"],
    ),
    BenchmarkPreset(
        preset_id="ui_visual_standard", family_id="ui_visual", display_name="UI / Visual", category="ui_visual", depth="standard",
        tasks=["responsive_cards", "modal", "state_change", "mobile_view"],
        required_evaluators=["syntax", "focused_tests", "portal_preview", "visual_runtime"],
        recommended_routes=[ForgeRoute.PATCH_DSL, ForgeRoute.SLICED_IMPACT],
        risk_level="medium", runtime_budget_seconds=600,
        profile_dimensions=["ui_visual", "web_app", "multi_file"],
    ),
    BenchmarkPreset(
        preset_id="db_persistence_standard", family_id="db_persistence", display_name="DB / Persistence", category="db_persistence", depth="standard",
        tasks=["sqlite_crud", "restart_persistence", "transaction_migration"],
        required_evaluators=["syntax", "focused_tests", "runtime_evidence"],
        recommended_routes=[ForgeRoute.PATCH_DSL, ForgeRoute.SLICED_IMPACT, ForgeRoute.TEST_FIRST],
        risk_level="high", runtime_budget_seconds=900,
        profile_dimensions=["db_persistence", "api_backend", "multi_file"],
    ),
    BenchmarkPreset(
        preset_id="repair_standard", family_id="repair", display_name="Repair", category="repair", depth="standard",
        tasks=["syntax_repair", "import_repair", "test_failure_repair", "runtime_repair", "visual_failure_repair"],
        required_evaluators=["syntax", "focused_tests", "runtime_evidence"],
        recommended_routes=[ForgeRoute.REPAIR_LOOP, ForgeRoute.MICRO_PATCH, ForgeRoute.PORTAL_REPLAY_REPAIR],
        risk_level="medium", runtime_budget_seconds=600,
        profile_dimensions=["repair", "failure_classification"],
    ),
    BenchmarkPreset(
        preset_id="greenfield_standard", family_id="greenfield", display_name="Greenfield", category="greenfield", depth="standard",
        tasks=["single_html", "small_asgi_app", "minimal_package_portal_run"],
        required_evaluators=["syntax", "focused_tests", "portal_preview"],
        recommended_routes=[ForgeRoute.GREENFIELD_SKELETON, ForgeRoute.SLICED_IMPACT],
        risk_level="medium", runtime_budget_seconds=1200,
        profile_dimensions=["greenfield", "web_app", "multi_file"],
    ),
)

_PRIMARY_FAMILY_RANK: dict[str, int] = {
    "quick": 0,
    "web_app": 1,
    "repair": 2,
    "greenfield": 3,
}


def validate_preset(preset: BenchmarkPreset) -> list[str]:
    """Every preset must declare tasks, required evaluators, and a positive runtime
    budget so a run can actually be scheduled and scored."""
    reasons: list[str] = []
    if not preset.preset_id.strip():
        reasons.append("missing_preset_id")
    if not (preset.family_id or preset.category).strip():
        reasons.append("missing_family_id")
    if not preset.tasks:
        reasons.append("no_tasks")
    if not preset.required_evaluators:
        reasons.append("no_required_evaluators")
    if preset.runtime_budget_seconds <= 0:
        reasons.append("non_positive_runtime_budget")
    return reasons


def load_presets() -> list[BenchmarkPreset]:
    """Return the built-in presets. Only valid presets are surfaced."""
    return [preset for preset in _BUILTIN_PRESETS if not validate_preset(preset)]


def get_preset(preset_id: str) -> BenchmarkPreset | None:
    for preset in _BUILTIN_PRESETS:
        if preset.preset_id == preset_id:
            return preset
    return None


def preset_listing() -> list[dict]:
    """API-ready summaries for the preset selector UI."""
    return [
        {
            "preset_id": preset.preset_id,
            "family_id": preset.family_id or preset.category,
            "primary_rank": _PRIMARY_FAMILY_RANK.get(preset.family_id or preset.category),
            "display_name": preset.display_name,
            "category": preset.category,
            "depth": preset.depth,
            "task_count": len(preset.tasks),
            "required_evaluators": list(preset.required_evaluators),
            "recommended_routes": [route.value for route in preset.recommended_routes],
            "risk_level": preset.risk_level,
            "runtime_budget_seconds": preset.runtime_budget_seconds,
            "profile_dimensions": list(preset.profile_dimensions),
        }
        for preset in load_presets()
    ]
