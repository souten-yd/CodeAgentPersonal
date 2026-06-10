"""PIR-3 concrete Digital Twin source refresh lifecycle tests."""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.contracts import ProjectIdentity
from agent.project_twin.facade import (
    OpenTwinRequest,
    RefreshTwinRequest,
    TwinHealthRequest,
    TwinQueryRequest,
    TwinReadiness,
)
from agent.project_twin.module import DigitalTwinModuleImpl


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _identity(root: Path) -> ProjectIdentity:
    return ProjectIdentity(project_id="p1", workspace_id="w1", project_path=str(root))


def test_open_real_project_builds_ready_source_backed_twin(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "app.py", "def hello():\n    return 1\n")
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")

    opened = twin.open_project(OpenTwinRequest(project=_identity(root)))
    query = twin.query(TwinQueryRequest(project_id="p1", workspace_id="w1", refs=["py://app.py#hello"]))
    twin.close()

    assert opened.readiness == TwinReadiness.READY
    assert opened.twin_revision_id is not None
    assert opened.parser_versions["source_adapter"].startswith("source_adapter.")
    assert [item.ref for item in query.items] == ["py://app.py#hello"]


def test_last_successful_build_record_survives_reopen_without_rebuild(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "app.py", "def hello():\n    return 1\n")
    db = tmp_path / "twin.db"
    twin = DigitalTwinModuleImpl(db)
    first = twin.open_project(OpenTwinRequest(project=_identity(root)))
    twin.close()

    reopened = DigitalTwinModuleImpl(db)
    second = reopened.open_project(OpenTwinRequest(project=_identity(root)))
    reopened.close()

    assert second.readiness == TwinReadiness.READY
    assert second.twin_revision_id == first.twin_revision_id


def test_incremental_refresh_preserves_unaffected_file_facts(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "a.py", "def fa():\n    return 1\n")
    _write(root, "b.py", "def fb():\n    return 2\n")
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")
    opened = twin.open_project(OpenTwinRequest(project=_identity(root)))
    before = twin.query(TwinQueryRequest(project_id="p1", workspace_id="w1", refs=["py://b.py#fb"]))

    _write(root, "a.py", "def fa():\n    return 99\n")
    refreshed = twin.refresh(RefreshTwinRequest(project=_identity(root), changed_paths=["a.py"]))
    after = twin.query(TwinQueryRequest(project_id="p1", workspace_id="w1", refs=["py://b.py#fb"]))
    twin.close()

    assert refreshed.readiness == TwinReadiness.READY
    assert refreshed.twin_revision_id != opened.twin_revision_id
    assert before.items and after.items
    assert before.twin_revision_id == opened.twin_revision_id
    assert after.items[0].ref == "py://b.py#fb"


def test_deleted_source_fact_is_invalidated(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "a.py", "def f():\n    return 1\n\ndef g():\n    return 2\n")
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")
    twin.open_project(OpenTwinRequest(project=_identity(root)))

    _write(root, "a.py", "def f():\n    return 1\n")
    refreshed = twin.refresh(RefreshTwinRequest(project=_identity(root), changed_paths=["a.py"]))
    invalidated = twin.query(
        TwinQueryRequest(project_id="p1", workspace_id="w1", refs=["py://a.py#g"], statuses=["invalidated"])
    )
    twin.close()

    assert refreshed.invalidation_count >= 1
    assert [item.ref for item in invalidated.items] == ["py://a.py#g"]
    assert invalidated.items[0].status == "invalidated"


def test_failed_refresh_retains_prior_active_source_revision(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "a.py", "def f():\n    return 1\n")
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")
    opened = twin.open_project(OpenTwinRequest(project=_identity(root)))

    failed = twin.refresh(
        RefreshTwinRequest(
            project=_identity(root),
            changed_paths=["a.py"],
            expected_revision_id="not-current",
        )
    )
    health = twin.health(TwinHealthRequest(project_id="p1", workspace_id="w1"))
    twin.close()

    assert failed.readiness == TwinReadiness.DEGRADED
    assert failed.twin_revision_id == opened.twin_revision_id
    assert health.twin_revision_id == opened.twin_revision_id
