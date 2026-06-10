"""PI-10 Blueprint model, store, and lifecycle tests.

Acceptance criteria (implementation plan PI-10):
- activated revisions are immutable;
- revision creates a child;
- user decision cannot be fabricated by LLM output;
- project isolation and point-in-time reads pass.
Plus scopes, state machine, one-active policy, diff, and the no-planned-as-Actual guard.
"""

from __future__ import annotations

import pytest

from agent.architecture_blueprint.contracts import (
    BlueprintActivationRequest,
    BlueprintCreateRequest,
    BlueprintElement,
    BlueprintGetRevisionRequest,
    BlueprintReviewRequest,
    BlueprintRevision,
    BlueprintRevisionRequest,
)
from agent.architecture_blueprint.lifecycle import (
    ACTIVE,
    APPROVED,
    PROPOSED,
    SUPERSEDED,
    BlueprintDiff,
    assert_transition,
    can_transition,
    diff_revisions,
    planner_decision,
    user_decision,
    validate_planned_refs,
)
from agent.architecture_blueprint.module import ArchitectureBlueprintModuleImpl
from agent.architecture_blueprint.store import BlueprintStore, StoreError
from agent.project_intelligence.contracts import IntelligenceError


def _module() -> ArchitectureBlueprintModuleImpl:
    return ArchitectureBlueprintModuleImpl(BlueprintStore())


# --- State machine + scopes --------------------------------------------------

def test_state_machine_transitions() -> None:
    assert can_transition(PROPOSED, "reviewed")
    assert not can_transition(PROPOSED, ACTIVE)
    assert can_transition(APPROVED, ACTIVE)
    with pytest.raises(IntelligenceError):
        assert_transition(PROPOSED, ACTIVE)


def test_invalid_scope_rejected() -> None:
    # Scope is a Literal in the contract, so an unknown scope is rejected at the boundary.
    with pytest.raises(Exception):
        BlueprintCreateRequest(project_id="p1", workspace_id="w1", scope="nonsense")
    # And validate_scope guards any internally-constructed value.
    from agent.architecture_blueprint.lifecycle import validate_scope
    with pytest.raises(IntelligenceError):
        validate_scope("nonsense")


# --- Create / review / activate flow + immutability --------------------------

def test_create_review_activate_flow_and_immutability() -> None:
    m = _module()
    res = m.create(BlueprintCreateRequest(project_id="p1", workspace_id="w1", scope="change_set"))
    assert res.status == PROPOSED and res.revision is not None
    rid, bid = res.revision_id, res.blueprint_id

    review = m.review(BlueprintReviewRequest(project_id="p1", blueprint_id=bid, revision_id=rid))
    assert review.valid is True  # no unresolved decisions / bad refs -> approved

    active = m.activate(BlueprintActivationRequest(project_id="p1", blueprint_id=bid, revision_id=rid))
    assert active.status == ACTIVE and active.activated_at is not None

    # Activated content is immutable: re-saving the same revision id with different content fails.
    store = m._store
    with pytest.raises(StoreError):
        store.save_revision(project_id="p1", workspace_id="w1", blueprint_id=bid,
                            revision_id=rid, payload={"mutated": True})
    # The active revision in the store is the activated one.
    got = m.get_active_revision("p1", "w1", bid)
    assert got is not None and got.revision_id == rid and got.status == ACTIVE


def test_revise_creates_child() -> None:
    m = _module()
    res = m.create(BlueprintCreateRequest(project_id="p1", workspace_id="w1", scope="change_set"))
    child = m.revise(BlueprintRevisionRequest(project_id="p1", blueprint_id=res.blueprint_id,
                                              parent_revision_id=res.revision_id, reason="iterate"))
    assert child.revision_id != res.revision_id
    assert child.revision.parent_revision_id == res.revision_id  # child of the parent
    # Both revisions remain retrievable (parent not mutated).
    parent = m.get_revision(BlueprintGetRevisionRequest(project_id="p1", blueprint_id=res.blueprint_id,
                                                        revision_id=res.revision_id))
    assert parent.revision_id == res.revision_id


def test_one_active_revision_supersedes_prior() -> None:
    m = _module()
    r1 = m.create(BlueprintCreateRequest(project_id="p1", workspace_id="w1", scope="full_project"))
    m.review(BlueprintReviewRequest(project_id="p1", blueprint_id=r1.blueprint_id, revision_id=r1.revision_id))
    m.activate(BlueprintActivationRequest(project_id="p1", blueprint_id=r1.blueprint_id, revision_id=r1.revision_id))
    # A child revision, reviewed + activated, supersedes the first.
    c = m.revise(BlueprintRevisionRequest(project_id="p1", blueprint_id=r1.blueprint_id,
                                          parent_revision_id=r1.revision_id))
    m.review(BlueprintReviewRequest(project_id="p1", blueprint_id=r1.blueprint_id, revision_id=c.revision_id))
    m.activate(BlueprintActivationRequest(project_id="p1", blueprint_id=r1.blueprint_id, revision_id=c.revision_id))
    active = m.get_active_revision("p1", "w1", r1.blueprint_id)
    assert active.revision_id == c.revision_id
    assert m._status[("p1", r1.revision_id)] == SUPERSEDED


# --- Authority: user decision cannot be fabricated by LLM ---------------------

def test_llm_cannot_fabricate_user_decision() -> None:
    d = planner_decision("d1", "db choice", [], "opt1", ["fast"])
    assert d.authority == "planner_recommendation"
    # The only path to user_decision requires explicit confirmation.
    with pytest.raises(IntelligenceError):
        user_decision("d2", "db choice", [], "opt1", confirmed_by_user=False)
    confirmed = user_decision("d2", "db choice", [], "opt1", confirmed_by_user=True)
    assert confirmed.authority == "user_decision"


# --- No planned element represented as an Actual reference -------------------

def test_planned_elements_cannot_use_actual_refs() -> None:
    bad = BlueprintRevision(
        blueprint_id="b", revision_id="r", project_id="p1", scope="change_set",
        selected_architecture=planner_decision("d", "t", [], "", []),
        elements=[BlueprintElement(element_id="e1", canonical_ref="py://app#handler",
                                   element_type="symbol")],
    )
    assert validate_planned_refs(bad) == ["e1"]
    ok = BlueprintRevision(
        blueprint_id="b", revision_id="r2", project_id="p1", scope="change_set",
        selected_architecture=planner_decision("d", "t", [], "", []),
        elements=[BlueprintElement(element_id="e1", canonical_ref="bp://app/handler",
                                   element_type="symbol",
                                   expected_actual_refs=["py://app#handler"])],
    )
    assert validate_planned_refs(ok) == []


# --- Diff --------------------------------------------------------------------

def test_diff_revisions() -> None:
    dec = planner_decision("d", "t", [], "", [])
    parent = BlueprintRevision(blueprint_id="b", revision_id="r1", project_id="p1", scope="change_set",
                               selected_architecture=dec,
                               elements=[BlueprintElement(element_id="e1", canonical_ref="bp://a", element_type="file"),
                                         BlueprintElement(element_id="e2", canonical_ref="bp://b", element_type="file")])
    child = BlueprintRevision(blueprint_id="b", revision_id="r2", project_id="p1", scope="change_set",
                              selected_architecture=dec,
                              elements=[BlueprintElement(element_id="e2", canonical_ref="bp://b2", element_type="file"),
                                        BlueprintElement(element_id="e3", canonical_ref="bp://c", element_type="file")])
    d = diff_revisions(parent, child)
    assert d.added_elements == ["e3"] and d.removed_elements == ["e1"] and d.changed_elements == ["e2"]


# --- Project isolation + point-in-time ---------------------------------------

def test_project_isolation_and_point_in_time() -> None:
    m = _module()
    r1 = m.create(BlueprintCreateRequest(project_id="p1", workspace_id="w1", scope="change_set"))
    r2 = m.create(BlueprintCreateRequest(project_id="p2", workspace_id="w1", scope="change_set"))
    # Different projects -> isolated; p2 cannot read p1's revision.
    assert m._store.get_revision("p2", r1.revision_id) is None
    assert m._store.get_revision("p1", r1.revision_id) is not None
    # Point-in-time read over the blueprint group works.
    hist = m._store.list_revisions("p1", r1.blueprint_id)
    assert len(hist) == 1
