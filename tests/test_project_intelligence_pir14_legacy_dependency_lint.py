"""PIR-14 legacy dependency lint tests."""

from __future__ import annotations

import json
from pathlib import Path

from agent.project_intelligence.legacy_dependency_lint import (
    build_allowlist,
    lint_legacy_dependencies,
    load_allowlist,
    write_lint_report,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = REPO_ROOT / "docs" / "generated" / "atlas_project_intelligence_legacy_dependency_allowlist.json"


def test_current_checkout_has_no_new_direct_legacy_consumers(tmp_path: Path) -> None:
    allowlist = load_allowlist(ALLOWLIST)
    report = lint_legacy_dependencies(REPO_ROOT, allowlist)

    assert report["passed"] is True
    assert report["violations"] == []
    assert report["summary"]["observed_dependency_count"] == allowlist["summary"]["allowed_dependency_count"]
    assert report["safety"] == {
        "consumer_cutover": False,
        "legacy_retirement": False,
    }

    output = tmp_path / "lint.json"
    written = write_lint_report(REPO_ROOT, allowlist, output)
    assert written == json.loads(output.read_text(encoding="utf-8"))


def test_allowlist_artifact_matches_current_schema() -> None:
    allowlist = load_allowlist(ALLOWLIST)

    assert allowlist["schema_version"] == 1
    assert allowlist["source"] == "python_ast_current_checkout_legacy_dependency_allowlist"
    assert allowlist["summary"]["allowed_dependency_count"] == 3
    assert allowlist["safety"] == {
        "allows_new_legacy_consumers": False,
        "consumer_cutover": False,
        "legacy_retirement": False,
    }
    assert not any(
        entry["legacy_module"] == "agent.atlas_verification_gate_service"
        and entry["consumer_path"] == "app/api/atlas_pipeline.py"
        for entry in allowlist["entries"]
    )


def test_lint_flags_new_direct_legacy_consumer(tmp_path: Path) -> None:
    root = tmp_path
    app_api = root / "app" / "api"
    app_api.mkdir(parents=True)
    (root / "agent").mkdir()
    (app_api / "new_consumer.py").write_text(
        "from agent.atlas_code_intel_service import AtlasCodeIntelService\n",
        encoding="utf-8",
    )

    empty_allowlist = {
        "schema_version": 1,
        "entries": [],
        "summary": {"allowed_dependency_count": 0},
    }
    report = lint_legacy_dependencies(root, empty_allowlist)

    assert report["passed"] is False
    assert report["summary"]["violation_count"] == 1
    assert report["violations"] == [
        {
            "legacy_module": "agent.atlas_code_intel_service",
            "capability": "legacy_code_intelligence",
            "consumer_path": "app/api/new_consumer.py",
        }
    ]


def test_build_allowlist_is_deterministic_for_current_checkout() -> None:
    a = build_allowlist(REPO_ROOT, generated_at="fixed")
    b = build_allowlist(REPO_ROOT, generated_at="fixed")
    assert a == b
