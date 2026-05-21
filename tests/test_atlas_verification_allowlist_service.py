from pathlib import Path

from app.atlas.verification_allowlist import classify_verification_command, create_verification_allowlist_record


def test_allowlist_record_and_policy(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "tests").mkdir()
    (project / "app").mkdir(parents=True)
    (project / "web/js").mkdir(parents=True)

    rec = create_verification_allowlist_record(
        project_path=project,
        data_root=tmp_path / "data",
        proposed_commands=[
            "pytest -q tests/test_example.py",
            "pytest -q tests/test_example.py::test_name",
            "python -m py_compile app/foo.py",
            "node --check web/js/foo.js",
            "pytest",
            "git push origin main",
            "rm -rf x",
            "pip install x",
            "pytest -q /tmp/a.py",
            "pytest -q tests/../x.py",
            "unknown cmd",
        ],
        risk_level="medium",
    )
    mpath = Path(rec["manifest_path"])
    assert mpath.exists()
    m = rec["manifest"]
    for k in ["schema_version", "allowlist_id", "project_path", "data_root", "proposed_commands", "command_results", "policy", "summary"]:
        assert k in m
    assert m["automatic_verification_enabled"] is False
    assert all(r["automatic_execution_enabled"] is False for r in m["command_results"])
    assert any(r["allowed"] and r["category"] == "pytest_targeted" for r in m["command_results"])
    assert any((not r["allowed"]) and r["reason"] == "broad_pytest_forbidden" for r in m["command_results"])
    assert any(
        (not r["allowed"]) and "shell_metacharacter" in r["reason"]
        for r in [classify_verification_command(command="pytest -q tests/x.py; whoami", project_path=project, risk_level="low")]
    )
    assert "ca_data" not in str(mpath)


def test_targeted_pytest_contracts(tmp_path: Path) -> None:
    p = tmp_path / "project"
    p.mkdir()
    (p / "tests").mkdir()

    file_only = classify_verification_command(command="pytest -q tests/test_example.py", project_path=p, risk_level="low")
    assert file_only["allowed"] is True
    assert file_only["category"] == "pytest_targeted"
    assert file_only["matched_rule"] == "pytest_q_tests_target"

    test_case = classify_verification_command(command="pytest -q tests/test_example.py::test_name", project_path=p, risk_level="low")
    assert test_case["allowed"] is True
    assert test_case["category"] == "pytest_targeted"
    assert test_case["matched_rule"] == "pytest_q_tests_target"

    broad = classify_verification_command(command="pytest", project_path=p, risk_level="low")
    assert broad["allowed"] is False
    assert broad["reason"] == "broad_pytest_forbidden"


def test_py_compile_command_is_allowlisted_metadata_only(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "app").mkdir()
    result = classify_verification_command(
        command="python -m py_compile app/foo.py",
        project_path=project,
        risk_level="low",
    )
    assert result["allowed"] is True
    assert result["category"] == "python_syntax_check"
    assert result["matched_rule"] == "python_m_py_compile"
    assert result["reason"] == "allowlisted_py_compile"
    assert result["normalized_command"] == "python -m py_compile app/foo.py"
    assert result["execution_supported"] is False
    assert result["automatic_execution_enabled"] is False


def test_py_compile_blocked_cases(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "app").mkdir()
    blocked = [
        "python -m py_compile /tmp/foo.py",
        "python -m py_compile ../foo.py",
        "python app/foo.py",
        'python -c "print(1)"',
        "python -m pip install x",
    ]
    for command in blocked:
        r = classify_verification_command(command=command, project_path=project, risk_level="low")
        assert r["allowed"] is False
        assert r["execution_supported"] is False
        assert r["automatic_execution_enabled"] is False


def test_node_check_command_is_allowlisted_metadata_only(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "web/js").mkdir(parents=True)
    result = classify_verification_command(
        command="node --check web/js/foo.js",
        project_path=project,
        risk_level="low",
    )
    assert result["allowed"] is True
    assert result["category"] == "node_syntax_check"
    assert result["matched_rule"] == "node_check_web_js_target"
    assert result["reason"] == "allowlisted_node_check"
    assert result["normalized_command"] == "node --check web/js/foo.js"
    assert result["execution_supported"] is False
    assert result["automatic_execution_enabled"] is False


def test_node_check_blocked_cases(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "web/js").mkdir(parents=True)
    blocked = [
        "node web/js/foo.js",
        "node --check /tmp/foo.js",
        "node --check ../foo.js",
        "node --check scripts/foo.js",
        "npm install",
    ]
    for command in blocked:
        r = classify_verification_command(command=command, project_path=project, risk_level="low")
        assert r["allowed"] is False
        assert r["execution_supported"] is False
        assert r["automatic_execution_enabled"] is False


def test_blocked_command_classes_remain_blocked(tmp_path: Path) -> None:
    p = tmp_path / "project"
    p.mkdir()
    (p / "tests").mkdir()
    blocked = [
        "pytest -q tests/test_x.py; whoami",
        "pytest -q tests/test_x.py && echo ok",
        "pytest -q tests/test_x.py | cat",
        "git push",
        "git pull",
        "git clone",
        "git fetch",
        "rm -rf x",
        "del x",
        "sudo pytest -q tests/test_x.py",
        "curl http://example.com",
        "wget http://example.com",
        "pip install x",
        "npm install",
        "apt-get install x",
    ]
    for command in blocked:
        r = classify_verification_command(command=command, project_path=p, risk_level="low")
        assert r["allowed"] is False
        assert r["automatic_execution_enabled"] is False
        assert r["execution_supported"] is False


def test_classification_does_not_modify_files(tmp_path: Path) -> None:
    p = tmp_path / "project"
    p.mkdir()
    f = p / "keep.txt"
    f.write_text("x", encoding="utf-8")
    before = f.read_text(encoding="utf-8")
    r = classify_verification_command(command="pytest -q tests/test_example.py", project_path=p, risk_level="high")
    assert r["requires_human_approval"] is True
    assert f.read_text(encoding="utf-8") == before


def test_unknown_risk_is_blocked(tmp_path: Path) -> None:
    p = tmp_path / "p"
    p.mkdir()
    (p / "tests").mkdir()
    r = classify_verification_command(command="pytest -q tests/test_example.py", project_path=p, risk_level="mystery")
    assert r["allowed"] is False
    assert r["automatic_execution_enabled"] is False
