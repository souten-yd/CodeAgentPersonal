"""Answering a clarification must reuse the original reserved pool_id.

When planning pauses for clarification, the plan-create request has already reserved a pool_id and
its job is parked at waiting_for_clarification. Answering re-plans and must rebind the resulting pool
to that same id (instead of minting a new one), so the id the caller has been tracking stays valid
rather than 404ing while a surprise new pool appears.
"""
from agent.atlas_clarification_schema import AtlasClarificationSession, AtlasClarificationSubmitRequest
from agent.atlas_clarification_service import AtlasClarificationService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool


def test_session_captures_original_pool_id_from_request():
    svc = AtlasClarificationService(journal=None)
    sess = svc.create_session_from_plan_response(
        "goal", {"questions": [], "requirement": {}}, {"pool_id": "pool_ORIG", "workspace_id": "default"})
    assert sess.original_pool_id == "pool_ORIG"


def test_session_captures_original_pool_id_from_response_fallback():
    svc = AtlasClarificationService(journal=None)
    sess = svc.create_session_from_plan_response(
        "goal", {"questions": [], "requirement": {}, "pool_id": "pool_RESP"}, {})
    assert sess.original_pool_id == "pool_RESP"


def test_session_default_original_pool_id_empty():
    assert AtlasClarificationSession(session_id="s", original_input="g").original_pool_id == ""


def test_submit_request_has_pool_id_field():
    req = AtlasClarificationSubmitRequest(session_id="s", pool_id="pool_X")
    assert req.pool_id == "pool_X"


def _rebind(pool: AtlasPlanPool, orig_pool_id: str) -> AtlasPlanPool:
    """Mirror the endpoint's rebind so the rule is unit-tested independent of the HTTP flow."""
    if orig_pool_id and orig_pool_id != pool.pool_id:
        pool.pool_id = orig_pool_id
        for it in (pool.items or []):
            it.pool_id = orig_pool_id
    return pool


def test_rebind_reuses_pool_id_on_pool_and_items():
    pool = AtlasPlanPool(
        pool_id="pool_NEW", root_goal="g",
        items=[AtlasPlanItem(item_id="step_1", pool_id="pool_NEW", title="t", goal="g")],
    )
    _rebind(pool, "pool_ORIG")
    assert pool.pool_id == "pool_ORIG"
    assert pool.items[0].pool_id == "pool_ORIG"


def test_rebind_noop_when_no_original():
    pool = AtlasPlanPool(pool_id="pool_NEW", root_goal="g", items=[])
    _rebind(pool, "")
    assert pool.pool_id == "pool_NEW"
