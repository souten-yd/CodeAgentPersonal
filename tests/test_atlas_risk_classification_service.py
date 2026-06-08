from pathlib import Path

from app.atlas.risk_classification import create_risk_classification_record, read_risk_classification_record


def test_create_record_and_manifest_under_data_root(tmp_path: Path) -> None:
    project = tmp_path / "project"
    data_root = tmp_path / "data"
    project.mkdir()
    f = project / "README.md"
    f.write_text("hello", encoding="utf-8")
    before = f.read_text(encoding="utf-8")

    res = create_risk_classification_record(project_path=project, data_root=data_root, proposed_files=[{"relative_path": "docs/notes.md", "change_type": "modify"}])
    assert Path(res["risk_dir"]).is_relative_to(data_root)
    manifest_path = Path(res["manifest_path"])
    assert manifest_path.exists()
    manifest = read_risk_classification_record(manifest_path=manifest_path, data_root=data_root)["manifest"]
    for key in ["schema_version", "risk_id", "project_path", "data_root", "risk_level", "matched_rules", "proposed_files"]:
        assert key in manifest
    assert f.read_text(encoding="utf-8") == before


def test_risk_levels_and_flags(tmp_path: Path) -> None:
    p = tmp_path / "p"
    d = tmp_path / "d"
    p.mkdir()
    assert create_risk_classification_record(project_path=p, data_root=d, proposed_files=[{"relative_path": "docs/readme.md", "change_type": "modify"}])["manifest"]["risk_level"] == "low"
    test_level = create_risk_classification_record(project_path=p, data_root=d, proposed_files=[{"relative_path": "tests/test_x.py", "change_type": "modify"}])["manifest"]["risk_level"]
    assert test_level in {"low", "medium"}
    assert test_level != "strict_gate"
    assert create_risk_classification_record(project_path=p, data_root=d, proposed_files=[{"relative_path": "app/core.py", "change_type": "modify"}])["manifest"]["risk_level"] in {"medium", "high", "strict_gate"}
    for path in ["app/api/atlas_pipeline.py", "Dockerfile", "docs/atlas_autonomous_execution_readiness_policy.md", "web/js/atlas_dashboard.js", "app/atlas/patch_transaction.py"]:
        m = create_risk_classification_record(project_path=p, data_root=d, proposed_files=[{"relative_path": path, "change_type": "modify"}])["manifest"]
        assert m["risk_level"] == "strict_gate"
        assert m["human_approval_required"] is True


def test_unknown_and_invalid_paths_not_low(tmp_path: Path) -> None:
    p = tmp_path / "p"
    d = tmp_path / "d"
    p.mkdir()
    assert create_risk_classification_record(project_path=p, data_root=d, proposed_files=[])["manifest"]["risk_level"] == "unknown"
    assert create_risk_classification_record(project_path=p, data_root=d, proposed_files=[{"relative_path": "/abs.txt", "change_type": "modify"}])["manifest"]["risk_level"] == "unknown"
    assert create_risk_classification_record(project_path=p, data_root=d, proposed_files=[{"relative_path": "../escape.txt", "change_type": "modify"}])["manifest"]["risk_level"] == "unknown"


def test_ordinary_source_files_classified_by_change_type(tmp_path: Path) -> None:
    # External-project work (root-level source/asset files) must not fall into "unknown".
    p = tmp_path / "p"
    d = tmp_path / "d"
    p.mkdir()

    def level(rel: str, change_type: str) -> str:
        return create_risk_classification_record(
            project_path=p, data_root=d,
            proposed_files=[{"relative_path": rel, "change_type": change_type}],
        )["manifest"]["risk_level"]

    # Creating a new source/asset file is additive -> low.
    assert level("index.html", "create") == "low"
    assert level("script.js", "create") == "low"
    assert level("styles.css", "create") == "low"
    # Modifying an existing source file can break behaviour -> medium.
    assert level("script.js", "modify") == "medium"
    # An unrecognised file type is still treated conservatively as unknown.
    assert level("data.bin", "create") == "unknown"


def test_strict_gate_paths_still_protected_after_source_fallback(tmp_path: Path) -> None:
    # The new source-file fallback must not weaken strict-gate protection.
    p = tmp_path / "p"
    d = tmp_path / "d"
    p.mkdir()
    for rel in ["package.json", "main.py", "app/api/atlas_pipeline.py", ".github/workflows/ci.yml"]:
        m = create_risk_classification_record(
            project_path=p, data_root=d,
            proposed_files=[{"relative_path": rel, "change_type": "modify"}],
        )["manifest"]
        assert m["risk_level"] == "strict_gate"


def test_policy_flags_and_no_direct_ca_data_string() -> None:
    text = Path("app/atlas/risk_classification.py").read_text(encoding="utf-8")
    assert 'Path("ca_data")' not in text
