"""Benchmark-derived route fitness for the Twin/Forge policy (route x injection).

A model's Forge benchmark profile (per task-family dimensions such as ``web_app`` /
``json_dsl``) tells us which generation routes it performs best at. This module turns those
benchmark scores into a per-``ForgeRoute`` fitness so the ExecutionPolicySelector can pick
the route that maximises the model's measured performance — but only AMONG the RouteMatrix's
safe candidates (the RouteMatrix stays the route authority; fitness only re-orders within
the safe set). Combined with the capability-driven injection level, this realises
"best route x right injection".
"""
from __future__ import annotations

from agent.model_forge.route_taxonomy import ForgeRoute


def derive_route_fitness(dimension_scores: dict[str, float]) -> dict[ForgeRoute, float]:
    """Map a model's benchmark profile dimensions onto a fitness score per ForgeRoute.

    Each benchmark preset declares ``profile_dimensions`` (the task-family skills it
    exercises) and ``recommended_routes``. A route's fitness is the mean of the model's
    scores on the dimensions of every preset that recommends that route. Routes with no
    benchmark evidence are simply absent (no fabricated fitness)."""
    from agent.model_forge.benchmark_presets import load_presets

    route_samples: dict[ForgeRoute, list[float]] = {}
    for preset in load_presets():
        vals = [dimension_scores[d] for d in preset.profile_dimensions if d in dimension_scores]
        if not vals:
            continue
        preset_score = sum(vals) / len(vals)
        for route in preset.recommended_routes:
            route_samples.setdefault(route, []).append(preset_score)
    return {route: round(sum(v) / len(v), 4) for route, v in route_samples.items() if v}


def best_route(candidates, fitness: dict[ForgeRoute, float]) -> ForgeRoute | None:
    """Pick the highest-fitness route among the supplied SAFE candidates, or None when no
    candidate has benchmark evidence (so the caller keeps the RouteMatrix default)."""
    scored = [(r, fitness.get(r, -1.0)) for r in candidates]
    scored = [(r, s) for r, s in scored if s >= 0.0]
    if not scored:
        return None
    # Highest fitness; deterministic tie-break by route value.
    return max(scored, key=lambda rs: (rs[1], rs[0].value))[0]


__all__ = ["derive_route_fitness", "best_route"]
