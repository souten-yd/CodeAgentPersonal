"""PI-20 Greenfield bootstrap orchestrator tests.

Acceptance criteria (implementation plan PI-20):
- empty directory is supported;
- no broad file generation without reviewed Blueprint;
- interruption resumes safely;
- the orchestrator cannot bypass Safe Apply.
Plus: dependency-ordered slices; Actual Twin refresh + Convergence after each apply.
"""

from __future__ import annotations

import pytest

from agent.architecture_blueprint.generator import BlueprintSpec, FileSpec, generate_blueprint
from agent.project_intelligence.contracts import IntelligenceError
from agent.project_intelligence.greenfield import GreenfieldOrchestrator, GreenfieldSession


def _active_blueprint():
    spec = BlueprintSpec(
        requirements=["R1", "R2"],
        files=[
            FileSpec(path="app/models.py", requirement_ids=["R1"], acceptance=["defines User"]),
            FileSpec(path="app/service.py", requirement_ids=["R2"], depends_on=["app/models.py"],
                     acceptance=["create_user"]),
        ],
        entrypoint="app/main.py", build_command="pip install -e .",
        start_command="uvicorn app.main:app", test_command="pytest -q",
    )
    bp = generate_blueprint(project_id="p1", workspace_id="w1", spec=spec, project_mode="empty")
    # promote to active for the orchestrator.
    return bp.model_copy(update={"status": "active"})


# --- Empty project supported + dependency-ordered slices ---------------------

def test_empty_project_bootstrap_and_slices() -> None:
    orch = GreenfieldOrchestrator()
    session = orch.start(project_id="p1", workspace_id="w1", project_mode="empty",
                         blueprint=_active_blueprint())
    assert session.slices  # has slices
    # models must come before service (dependency order across slices).
    flat = [i for layer in session.slices for i in layer]
    assert flat.index("item:el:app/models.py") < flat.index("item:el:app/service.py")


# --- No broad generation without a reviewed/active/valid Blueprint -----------

def test_no_generation_without_active_blueprint() -> None:
    orch = GreenfieldOrchestrator()
    bp = _active_blueprint().model_copy(update={"status": "proposed"})  # not active
    with pytest.raises(IntelligenceError):
        orch.start(project_id="p1", workspace_id="w1", project_mode="empty", blueprint=bp)


def test_non_greenfield_mode_rejected() -> None:
    orch = GreenfieldOrchestrator()
    with pytest.raises(IntelligenceError):
        orch.start(project_id="p1", workspace_id="w1", project_mode="existing",
                   blueprint=_active_blueprint())


# --- One coherent slice at a time + refresh/convergence after apply ----------

def test_one_slice_at_a_time_with_refresh_and_convergence() -> None:
    orch = GreenfieldOrchestrator()
    session = orch.start(project_id="p1", workspace_id="w1", project_mode="empty",
                         blueprint=_active_blueprint())
    work = orch.next_slice(session)
    assert work is not None and work.slice_index == 0
    assert work.must_use_safe_apply is True  # apply intents only
    res = orch.complete_slice(session, 0, applied=True)
    assert res.refresh_requested is True and res.convergence_requested is True
    # next slice advances and is different.
    assert res.next_index is not None and res.next_index != 0


def test_completes_after_all_slices() -> None:
    orch = GreenfieldOrchestrator()
    session = orch.start(project_id="p1", workspace_id="w1", project_mode="empty",
                         blueprint=_active_blueprint())
    while True:
        work = orch.next_slice(session)
        if work is None:
            break
        orch.complete_slice(session, work.slice_index, applied=True)
    assert orch.is_complete(session) is True


# --- Cannot bypass Safe Apply ------------------------------------------------

def test_orchestrator_cannot_write_workspace() -> None:
    orch = GreenfieldOrchestrator()
    assert orch.requires_safe_apply is True
    # The orchestrator exposes no apply/write method (generation must go via Safe Apply).
    for attr in dir(orch):
        assert not any(w in attr.lower() for w in ("apply_patch", "write_file", "commit", "merge"))
    work = orch.next_slice(orch.start(project_id="p1", workspace_id="w1", project_mode="empty",
                                      blueprint=_active_blueprint()))
    assert work.must_use_safe_apply is True


# --- Interruption resumes safely ---------------------------------------------

def test_interruption_resumes_safely() -> None:
    orch = GreenfieldOrchestrator()
    session = orch.start(project_id="p1", workspace_id="w1", project_mode="empty",
                         blueprint=_active_blueprint())
    orch.complete_slice(session, 0, applied=True)
    # Serialize (e.g. to a checkpoint) and restore after a restart.
    state = session.to_state()
    restored = GreenfieldSession.from_state(state)
    assert restored.completed_slices == [0]
    # Continue from where we left off; slice 0 is not regenerated.
    work = orch.next_slice(restored)
    assert work is None or work.slice_index != 0
