"""Route Matrix policy and selector (PFG-18).

Maps a change class (and task category) to an ordered list of candidate routes and
selects a route, recording the decision. Route selection is independent from model
selection (Forge scores route x model combinations elsewhere).

Hard safety rule: large and critical changes cannot be forced through unsafe micro
routes. A critical change always routes through ``critical_gate``. If a caller requests
a forbidden route for the change class, the selector overrides it and records why — it
never silently honours an unsafe request.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Callable

from pydantic import Field

from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel


class ChangeClass(StrEnum):
    TRIVIAL = "trivial"
    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    CRITICAL = "critical"
    GREENFIELD = "greenfield"


# Routes whose scope is too small to safely carry a large/critical change.
UNSAFE_MICRO_ROUTES: frozenset[ForgeRoute] = frozenset(
    {ForgeRoute.DETERMINISTIC, ForgeRoute.MICRO_PATCH, ForgeRoute.DIRECT_PATCH}
)

# Ordered candidate routes per change class (first = preferred default).
_DEFAULT_ROUTES: dict[ChangeClass, list[ForgeRoute]] = {
    ChangeClass.TRIVIAL: [ForgeRoute.DETERMINISTIC, ForgeRoute.MICRO_PATCH],
    ChangeClass.MICRO: [ForgeRoute.MICRO_PATCH, ForgeRoute.DIRECT_PATCH, ForgeRoute.PATCH_DSL],
    ChangeClass.SMALL: [ForgeRoute.DIRECT_PATCH, ForgeRoute.PATCH_DSL, ForgeRoute.TEST_FIRST],
    ChangeClass.MEDIUM: [ForgeRoute.PATCH_DSL, ForgeRoute.SLICED_IMPACT, ForgeRoute.TEST_FIRST],
    ChangeClass.LARGE: [ForgeRoute.SLICED_IMPACT, ForgeRoute.BLUEPRINT_SLICE, ForgeRoute.TEST_FIRST],
    ChangeClass.CRITICAL: [ForgeRoute.CRITICAL_GATE, ForgeRoute.BLUEPRINT_SLICE],
    ChangeClass.GREENFIELD: [ForgeRoute.GREENFIELD_SKELETON, ForgeRoute.BLUEPRINT_SLICE],
}

# Task categories that pull in repair-oriented routes regardless of size.
_REPAIR_TASK_CATEGORIES = {"repair", "failure", "bugfix", "portal_repair"}


def default_routes_for_class(change_class: ChangeClass | str) -> list[ForgeRoute]:
    return list(_DEFAULT_ROUTES.get(ChangeClass(change_class), [ForgeRoute.PATCH_DSL]))


class RoutePolicyEntry(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    change_class: ChangeClass
    candidate_routes: list[ForgeRoute] = Field(default_factory=list)
    # Routes explicitly disallowed for this change class.
    forbidden_routes: list[ForgeRoute] = Field(default_factory=list)
    critical_gate_required: bool = False


class RouteSelection(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    change_class: ChangeClass
    task_category: str = ""
    selected_route: ForgeRoute
    requested_route: ForgeRoute | None = None
    overridden: bool = False
    critical_gate_required: bool = False
    candidates_considered: list[ForgeRoute] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    decided_at: str = ""


class RouteMatrix:
    """Holds the change-class -> route policy. Defaults are evidence of intent only;
    they never force a large/critical change through an unsafe micro route."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def entry(self, change_class: ChangeClass | str, *, task_category: str = "") -> RoutePolicyEntry:
        change_class = ChangeClass(change_class)
        routes = default_routes_for_class(change_class)
        # Repair-style tasks prepend repair routes (still subject to safety filtering).
        if task_category.lower() in _REPAIR_TASK_CATEGORIES:
            for r in (ForgeRoute.PORTAL_REPLAY_REPAIR, ForgeRoute.REPAIR_LOOP):
                if r not in routes:
                    routes.insert(0, r)
        forbidden: list[ForgeRoute] = []
        critical_gate = change_class == ChangeClass.CRITICAL
        if change_class in (ChangeClass.LARGE, ChangeClass.CRITICAL):
            # Large/critical changes may never use an unsafe micro route.
            forbidden = sorted(UNSAFE_MICRO_ROUTES)
            routes = [r for r in routes if r not in UNSAFE_MICRO_ROUTES]
        if critical_gate and ForgeRoute.CRITICAL_GATE not in routes:
            routes.insert(0, ForgeRoute.CRITICAL_GATE)
        return RoutePolicyEntry(
            change_class=change_class, candidate_routes=routes,
            forbidden_routes=forbidden, critical_gate_required=critical_gate,
        )


class RouteSelector:
    def __init__(self, matrix: RouteMatrix, *, clock: Callable[[], datetime] | None = None) -> None:
        self._matrix = matrix
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def select(
        self,
        change_class: ChangeClass | str,
        *,
        task_category: str = "",
        requested_route: ForgeRoute | str | None = None,
    ) -> RouteSelection:
        change_class = ChangeClass(change_class)
        entry = self._matrix.entry(change_class, task_category=task_category)
        requested = ForgeRoute(requested_route) if requested_route is not None else None
        reasons: list[str] = []
        overridden = False

        if entry.critical_gate_required:
            # A critical change always passes through the critical gate.
            selected = ForgeRoute.CRITICAL_GATE
            if requested is not None and requested != ForgeRoute.CRITICAL_GATE:
                overridden = True
                reasons.append(f"critical_change_forces_critical_gate:requested_{requested}")
            else:
                reasons.append("critical_change_routes_through_critical_gate")
        elif requested is not None:
            if requested in entry.forbidden_routes:
                selected = entry.candidate_routes[0]
                overridden = True
                reasons.append(f"unsafe_micro_route_blocked_for_{change_class}:requested_{requested}")
            elif requested in entry.candidate_routes:
                selected = requested
                reasons.append("requested_route_allowed")
            else:
                # Requested route is not unsafe but not a recommended candidate either:
                # honour it only if it is not an unsafe micro route for this class.
                if requested in UNSAFE_MICRO_ROUTES and change_class in (ChangeClass.LARGE, ChangeClass.CRITICAL):
                    selected = entry.candidate_routes[0]
                    overridden = True
                    reasons.append(f"unsafe_micro_route_blocked_for_{change_class}:requested_{requested}")
                else:
                    selected = requested
                    reasons.append("requested_route_accepted_non_default")
        else:
            selected = entry.candidate_routes[0]
            reasons.append(f"default_route_for_{change_class}")

        return RouteSelection(
            change_class=change_class, task_category=task_category,
            selected_route=selected, requested_route=requested, overridden=overridden,
            critical_gate_required=entry.critical_gate_required,
            candidates_considered=entry.candidate_routes, reasons=reasons,
            decided_at=self._clock().isoformat(),
        )


__all__ = [
    "ChangeClass",
    "UNSAFE_MICRO_ROUTES",
    "RoutePolicyEntry",
    "RouteSelection",
    "RouteMatrix",
    "RouteSelector",
    "default_routes_for_class",
]
