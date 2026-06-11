"""Forge route taxonomy (PFG-5).

Stable route IDs. Route selection is independent from model selection; Forge scores
route x model combinations in later packages. Pure taxonomy code.
"""
from __future__ import annotations

from enum import StrEnum


class ForgeRoute(StrEnum):
    DETERMINISTIC = "deterministic"
    MICRO_PATCH = "micro_patch"
    DIRECT_PATCH = "direct_patch"
    PATCH_DSL = "patch_dsl"
    TEST_FIRST = "test_first"
    REPAIR_LOOP = "repair_loop"
    SLICED_IMPACT = "sliced_impact"
    BLUEPRINT_SLICE = "blueprint_slice"
    CRITICAL_GATE = "critical_gate"
    GREENFIELD_SKELETON = "greenfield_skeleton"
    PORTAL_REPLAY_REPAIR = "portal_replay_repair"


def all_routes() -> list[ForgeRoute]:
    return list(ForgeRoute)


def is_valid_route(value: object) -> bool:
    try:
        ForgeRoute(value)  # type: ignore[arg-type]
        return True
    except ValueError:
        return False
