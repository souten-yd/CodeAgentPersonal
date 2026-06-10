"""PIR-5 verification ingestion, test selection, and bounded context tests."""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.contracts import ProjectIdentity
from agent.project_twin.facade import (
    OpenTwinRequest,
    RuntimeIngestRequest,
    TwinContextRequest,
    TwinQueryKind,
    TwinQueryRequest,
)
from agent.project_twin.module import DigitalTwinModuleImpl
from agent.project_twin.runtime.collectors import normalize_pytest


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _identity(root: Path) -> ProjectIdentity:
    return ProjectIdentity(project_id="p1", workspace_id="w1", project_path=str(root))


def test_per_test_coverage_drives_targeted_test_selection(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "app.py", "def f():\n    return 1\n\ndef g():\n    return 2\n")
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")
    opened = twin.open_project(OpenTwinRequest(project=_identity(root)))
    observations = normalize_pytest(
        {
            "tests": [
                {"nodeid": "tests/test_app.py::test_f", "outcome": "passed", "coverage": {"app.py": ["f"]}},
                {"nodeid": "tests/test_app.py::test_g", "outcome": "passed", "coverage": {"app.py": ["g"]}},
            ]
        },
        project_id="p1",
        workspace_id="w1",
        source_revision=opened.project.source_revision,
        run_id="run1",
    )
    twin.ingest_runtime(RuntimeIngestRequest(project=_identity(root), observations=observations))

    selected = twin.query(
        TwinQueryRequest(
            project_id="p1",
            workspace_id="w1",
            kind=TwinQueryKind.TEST_SELECTION,
            refs=["py://app.py#f"],
        )
    )
    twin.close()

    assert [item.ref for item in selected.items] == ["test://tests/test_app.py::test_f"]


def test_stale_verification_is_diagnosed_and_not_selected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "app.py", "def f():\n    return 1\n")
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")
    twin.open_project(OpenTwinRequest(project=_identity(root)))
    observations = normalize_pytest(
        {"tests": [{"nodeid": "tests/test_app.py::test_f", "outcome": "passed", "coverage": {"app.py": ["f"]}}]},
        project_id="p1",
        workspace_id="w1",
        source_revision="stale-source",
    )
    result = twin.ingest_runtime(RuntimeIngestRequest(project=_identity(root), observations=observations))
    selected = twin.query(
        TwinQueryRequest(
            project_id="p1",
            workspace_id="w1",
            kind=TwinQueryKind.TEST_SELECTION,
            refs=["py://app.py#f"],
        )
    )
    twin.close()

    assert any("does not match current source revision" in diagnostic.message for diagnostic in result.diagnostics)
    assert selected.items == []


def test_context_contains_symbol_range_excerpt_and_runtime_evidence(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "app.py", "def helper():\n    return 1\n\n\ndef target():\n    return helper()\n")
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")
    opened = twin.open_project(OpenTwinRequest(project=_identity(root)))
    observations = normalize_pytest(
        {"tests": [{"nodeid": "tests/test_app.py::test_target", "outcome": "passed", "coverage": {"app.py": ["target"]}}]},
        project_id="p1",
        workspace_id="w1",
        source_revision=opened.project.source_revision,
    )
    twin.ingest_runtime(RuntimeIngestRequest(project=_identity(root), observations=observations))

    package = twin.build_context(
        TwinContextRequest(
            project_id="p1",
            workspace_id="w1",
            phase="planning",
            target_refs=["py://app.py#target"],
            token_budget=800,
        )
    )
    twin.close()

    assert package.symbols and package.symbols[0].ref == "py://app.py#target"
    assert package.tests and package.tests[0].ref == "test://tests/test_app.py::test_target"
    assert package.runtime_evidence
    assert package.source_material
    excerpt = package.source_material[0]
    assert excerpt.path == "app.py"
    assert excerpt.start_line == 5
    assert "def target" in excerpt.excerpt
    assert package.manifest.included_refs
    assert package.manifest.used_tokens <= package.manifest.token_budget


def test_context_token_budget_truncates_nonessential_items(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _write(root, "app.py", "\n".join(f"def f{i}():\n    return {i}" for i in range(20)))
    twin = DigitalTwinModuleImpl(tmp_path / "twin.db")
    twin.open_project(OpenTwinRequest(project=_identity(root)))

    package = twin.build_context(
        TwinContextRequest(
            project_id="p1",
            workspace_id="w1",
            phase="generation",
            objective="f",
            token_budget=80,
        )
    )
    twin.close()

    assert package.manifest.truncated is True
    assert package.manifest.used_tokens <= 80
    assert "token_budget_overflow" in package.manifest.excluded_refs
