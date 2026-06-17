"""Templated test-input repair for the plan-pool async-contract drift.

`POST /api/atlas/plan-pools` intentionally went async (returns ``{pool_id, status: queued}``); tests that
still read ``response['plan_pool']['items'][0]`` raise ``KeyError: 'plan_pool'`` — the largest failure
cluster, and TEST DEBT (the API is correct). The fix: request the synchronous path (``?sync=1``) and
supply a ``plan_payload`` so the pool has a real item.

This is now a thin specialisation of the generic, endpoint-parameterized ``sync_contract_repair`` — the
plan-pools drift turned out to be one instance of the same shape (an endpoint went async; add ``?sync=1``
to the ``.post`` call). Kept as a named entrypoint for the plan-pools cluster; new drifts should use
``sync_contract_repair.repair_sync_contracts`` with the relevant endpoint map.
"""
from __future__ import annotations

from agent.twin_control_plane.sync_contract_repair import PLAN_PAYLOAD_LITERAL, repair_sync_contracts

_PLAN_POOL_ENDPOINTS = {"/api/atlas/plan-pools": PLAN_PAYLOAD_LITERAL}


def repair_plan_pool_source(src: str) -> tuple[str, int]:
    """Rewrite plan-pool POST call sites to the synchronous-with-payload contract. Returns
    ``(new_src, n_changes)``; ``n_changes == 0`` means nothing matched (left unchanged)."""
    return repair_sync_contracts(src, endpoints=_PLAN_POOL_ENDPOINTS)
