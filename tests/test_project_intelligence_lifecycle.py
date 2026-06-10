"""PI-4 project identity, mode detection, and lifecycle tests.

Acceptance criteria (implementation plan PI-4):
- empty directory creates a valid repository-level Twin;
- worktrees do not leak data;
- external changes mark stale or trigger refresh;
- corrupt DB fails closed and supports rebuild;
- restart resumes or safely retries jobs.
"""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.contracts import ProjectMode
from agent.project_intelligence.project_mode import detect_project_mode
from agent.project_intelligence.store import ProjectIntelligenceStore
from agent.project_twin.facade import TwinReadiness
from agent.project_twin.jobs import BUILD, ProjectionJobService
from agent.project_twin.lifecycle import (
    FULL_BUILD,
    INCREMENTAL_REFRESH,
    NO_REFRESH,
    LastBuildRecord,
    build_project_state,
    decide_refresh,
    evaluate_readiness,
)
from agent.project_twin.project_identity import compute_project_identity


# --- Project identity --------------------------------------------------------

def test_identity_is_stable_and_repository_level(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    id1 = compute_project_identity(tmp_path)
    id2 = compute_project_identity(tmp_path)
    assert id1.project_id == id2.project_id
    assert id1.project_id.startswith("proj_")
    assert id1.workspace_id.startswith("ws_")
    assert id1.working_tree_hash == id2.working_tree_hash


def test_empty_directory_yields_valid_identity(tmp_path: Path) -> None:
    # Acceptance: an empty directory still gets a valid repository-level identity.
    ident = compute_project_identity(tmp_path)
    assert ident.project_id.startswith("proj_")
    assert ident.project_path == str(tmp_path.resolve())


def test_worktrees_do_not_leak_identity(tmp_path: Path) -> None:
    # Two distinct working directories must get distinct project ids (no leakage).
    wt1 = tmp_path / "wt1"
    wt2 = tmp_path / "wt2"
    wt1.mkdir()
    wt2.mkdir()
    (wt1 / "a.py").write_text("x = 1\n", encoding="utf-8")
    (wt2 / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert compute_project_identity(wt1).project_id != compute_project_identity(wt2).project_id
    # An explicit workspace id is honoured (sandbox isolation).
    assert compute_project_identity(wt1, workspace_id="sandbox-A").workspace_id == "sandbox-A"


def test_working_tree_hash_changes_on_external_edit(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    before = compute_project_identity(tmp_path).working_tree_hash
    (tmp_path / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    after = compute_project_identity(tmp_path).working_tree_hash
    assert before != after


# --- Project mode detection --------------------------------------------------

def test_mode_empty_ignores_git_and_docs(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    (tmp_path / "README.md").write_text("# project\n", encoding="utf-8")
    assert detect_project_mode(tmp_path) == ProjectMode.EMPTY


def test_mode_greenfield_partial(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    assert detect_project_mode(tmp_path) == ProjectMode.GREENFIELD_PARTIAL


def test_mode_existing_with_tests(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("def g():\n    return 2\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_app.py").write_text("def test_f():\n    assert True\n", encoding="utf-8")
    assert detect_project_mode(tmp_path) == ProjectMode.EXISTING


def test_mode_generated_unverified(tmp_path: Path) -> None:
    for i in range(6):
        (tmp_path / f"mod{i}.py").write_text(f"v = {i}\n", encoding="utf-8")
    assert detect_project_mode(tmp_path) == ProjectMode.GENERATED_UNVERIFIED


# --- Readiness + refresh decisions -------------------------------------------

def _identity(tmp_path: Path):
    return compute_project_identity(tmp_path)


def test_readiness_disabled_and_absent(tmp_path: Path) -> None:
    ident = _identity(tmp_path)
    r, _ = evaluate_readiness(ident, None, disabled=True)
    assert r == TwinReadiness.DISABLED
    r2, _ = evaluate_readiness(ident, None)
    assert r2 == TwinReadiness.ABSENT
    assert decide_refresh(r2) == FULL_BUILD


def test_readiness_ready_then_stale_on_external_change(tmp_path: Path) -> None:
    ident = _identity(tmp_path)
    lb = LastBuildRecord(
        twin_revision_id="rev1",
        source_revision=ident.source_revision,
        working_tree_hash=ident.working_tree_hash,
        parser_versions={"py": "1"},
    )
    r, reasons = evaluate_readiness(ident, lb, current_parser_versions={"py": "1"})
    assert r == TwinReadiness.READY and reasons == []
    assert decide_refresh(r) == NO_REFRESH

    # External edit changes the working-tree hash -> stale -> incremental refresh.
    changed = ident.model_copy(update={"working_tree_hash": ident.working_tree_hash + "x"})
    r2, reasons2 = evaluate_readiness(changed, lb, current_parser_versions={"py": "1"})
    assert r2 == TwinReadiness.STALE
    assert "working_tree_changed" in reasons2
    assert decide_refresh(r2) == INCREMENTAL_REFRESH


def test_corrupt_fails_closed_and_rebuilds(tmp_path: Path) -> None:
    ident = _identity(tmp_path)
    state = build_project_state(ident, None, integrity_status="corrupt")
    assert state.readiness == TwinReadiness.CORRUPT
    assert state.diagnostics and state.diagnostics[0].code.value == "store_corrupt"
    assert decide_refresh(state.readiness) == FULL_BUILD


def test_parser_version_change_marks_stale(tmp_path: Path) -> None:
    ident = _identity(tmp_path)
    lb = LastBuildRecord(twin_revision_id="r", source_revision=ident.source_revision,
                         working_tree_hash=ident.working_tree_hash, parser_versions={"py": "1"})
    r, reasons = evaluate_readiness(ident, lb, current_parser_versions={"py": "2"})
    assert r == TwinReadiness.STALE
    assert "parser_version_changed" in reasons


# --- Projection jobs: restart recovery + bounded retry -----------------------

def test_jobs_run_to_done_and_recover_on_restart() -> None:
    store = ProjectIntelligenceStore()
    svc = ProjectionJobService(store)
    svc.schedule(project_id="p1", workspace_id="w1", job_id="j1", job_type=BUILD)

    ran: list[dict] = []
    outcome = svc.run_one("p1", "j1", lambda payload: ran.append(payload))
    assert outcome.status == "done" and len(ran) == 1

    # Simulate an interrupted job: enqueue + claim (leaves it running), then restart.
    svc.schedule(project_id="p1", workspace_id="w1", job_id="j2", job_type=BUILD)
    store.claim_job("p1", "j2")
    assert svc.recover_on_startup("p1") == 1
    assert store.get_job("p1", "j2")["status"] == "queued"


def test_jobs_failed_handler_is_retryable_then_failed() -> None:
    store = ProjectIntelligenceStore()
    svc = ProjectionJobService(store, max_attempts=2)
    svc.schedule(project_id="p1", workspace_id="w1", job_id="j1", job_type=BUILD)

    def boom(_payload):
        raise RuntimeError("projection failed")

    o1 = svc.run_one("p1", "j1", boom)  # attempt 1 -> retryable (back to queued)
    assert o1.status == "queued"
    o2 = svc.run_one("p1", "j1", boom)  # attempt 2 reaches max -> failed, never 'done'
    assert o2.status == "failed"
    assert store.get_job("p1", "j1")["status"] == "failed"
