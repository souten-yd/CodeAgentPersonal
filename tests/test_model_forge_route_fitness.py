"""I1 — benchmark profile -> per-route fitness; best safe route picked."""
from __future__ import annotations

from agent.model_forge.route_fitness import best_route, derive_route_fitness
from agent.model_forge.route_taxonomy import ForgeRoute


def test_fitness_maps_benchmark_dims_to_routes():
    # web_app/api_backend/multi_file strong, quick skills weak.
    fitness = derive_route_fitness({"web_app": 0.9, "api_backend": 0.9, "multi_file": 0.9,
                                    "json_dsl": 0.1, "patch_generation": 0.1, "speed": 0.1})
    # web_app preset recommends PATCH_DSL/SLICED_IMPACT/TEST_FIRST -> high fitness.
    assert fitness.get(ForgeRoute.TEST_FIRST, 0) > fitness.get(ForgeRoute.MICRO_PATCH, 1)
    assert ForgeRoute.SLICED_IMPACT in fitness


def test_routes_without_evidence_are_absent():
    fitness = derive_route_fitness({"web_app": 0.8})  # only web_app dim known
    # DETERMINISTIC route (no preset recommends it / no dims) is absent.
    assert ForgeRoute.DETERMINISTIC not in fitness


def test_best_route_picks_strongest_safe_candidate():
    fitness = {ForgeRoute.MICRO_PATCH: 0.2, ForgeRoute.PATCH_DSL: 0.9, ForgeRoute.DIRECT_PATCH: 0.5}
    candidates = [ForgeRoute.MICRO_PATCH, ForgeRoute.DIRECT_PATCH, ForgeRoute.PATCH_DSL]
    assert best_route(candidates, fitness) == ForgeRoute.PATCH_DSL


def test_best_route_none_without_evidence():
    candidates = [ForgeRoute.MICRO_PATCH, ForgeRoute.DIRECT_PATCH]
    assert best_route(candidates, {ForgeRoute.PATCH_DSL: 0.9}) is None  # no candidate has evidence


def test_empty_profile_yields_no_fitness():
    assert derive_route_fitness({}) == {}
