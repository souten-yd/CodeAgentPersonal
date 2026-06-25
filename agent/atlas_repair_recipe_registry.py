from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from agent.atlas_repair_recipes import WEBGL_2D_OPTIONS, repair_webgl_2d_conflict


class RepairRecipe(Protocol):
    id: str
    violation_code: str
    contract_type: str
    applies_to: list[str]

    def options(self, violation: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        ...

    def apply_selected(
        self,
        option_id: str,
        violation: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class WebGLCanvas2DRepairRecipe:
    id: str = "webgl_canvas_2d_context_conflict"
    violation_code: str = "webgl_canvas_2d_context_conflict"
    contract_type: str = "resource"
    applies_to: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(self, "applies_to", ["js", "mjs", "cjs", "jsx", "ts", "tsx", "html"])

    def options(self, violation: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        return [dict(option) for option in WEBGL_2D_OPTIONS]

    def apply_selected(
        self,
        option_id: str,
        violation: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        path = str(violation.get("path") or context.get("path") or "")
        content_by_path = context.get("content_by_path") if isinstance(context.get("content_by_path"), dict) else {}
        content = str(content_by_path.get(path) if path else context.get("content") or "")
        resource_contract = context.get("resource_contract") if isinstance(context.get("resource_contract"), dict) else {}
        canvas_id = str(resource_contract.get("primary_canvas") or (violation.get("evidence") or {}).get("primary_canvas") or "")
        if not content:
            return {"applied": False, "reason": "repair_content_missing", "recipe": self.id, "path": path}
        if not canvas_id:
            return {"applied": False, "reason": "repair_canvas_missing", "recipe": self.id, "path": path}
        result = repair_webgl_2d_conflict(content, canvas_id, selected_option_id=option_id)
        result.setdefault("recipe", self.id)
        result["path"] = path
        return result


class RepairRecipeRegistry:
    def __init__(self, recipes: list[RepairRecipe] | None = None):
        self._recipes: dict[tuple[str, str], RepairRecipe] = {}
        for recipe in recipes or [WebGLCanvas2DRepairRecipe()]:
            self.register(recipe)

    def register(self, recipe: RepairRecipe) -> None:
        self._recipes[(str(recipe.contract_type), str(recipe.violation_code))] = recipe

    def find(self, violation: dict[str, Any]) -> RepairRecipe | None:
        key = (str(violation.get("contract_type") or ""), str(violation.get("code") or ""))
        return self._recipes.get(key)

    def options(self, violation: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        recipe = self.find(violation)
        if recipe is None:
            return {"available": False, "reason": "no_recipe", "options": []}
        return {
            "available": True,
            "recipe": recipe.id,
            "options": recipe.options(violation, context or {}),
        }

    def apply_selected(
        self,
        *,
        option_id: str = "",
        violation: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        recipe = self.find(violation)
        if recipe is None:
            return {"applied": False, "reason": "no_recipe"}
        return recipe.apply_selected(str(option_id or ""), violation, context or {})


def default_repair_recipe_registry() -> RepairRecipeRegistry:
    return RepairRecipeRegistry()


def repair_options_for_violation(violation: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    return default_repair_recipe_registry().options(violation, context or {})


def apply_repair_for_violation(
    *,
    violation: dict[str, Any],
    context: dict[str, Any] | None = None,
    selected_option_id: str = "",
) -> dict[str, Any]:
    return default_repair_recipe_registry().apply_selected(
        option_id=selected_option_id,
        violation=violation,
        context=context or {},
    )

