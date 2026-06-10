from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "atlas-project-intelligence-recovery.yml"


def test_pir14_recovery_ci_workflow_exists_with_required_suites() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for suite in (
        "focused-regression",
        "integration",
        "restart-fault",
        "fixture-e2e",
        "cutover-platform-contracts",
    ):
        assert suite in text
    assert "python -m pytest -q tests/test_project_intelligence_recovery_baseline.py" in text
    assert "--junitxml artifacts/pir14-ci/focused-regression.xml" in text
    assert "--junitxml artifacts/pir14-ci/fixture-e2e.xml" in text
    assert "actions/upload-artifact@v4" in text
    assert "$GITHUB_STEP_SUMMARY" in text
    assert '- "codex/**"' in text
    assert 'CODEAGENT_CA_DATA_DIR="$RUNNER_TEMP/ca_data"' in text
    assert 'CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR="$RUNNER_TEMP/style_bert_vits2/models"' in text
    assert "pytest fastapi uvicorn requests pydantic psutil httpx websockets python-multipart" in text
    assert "pytest fastapi uvicorn requests pydantic psutil httpx websockets python-multipart playwright" in text
    assert "python -m playwright install --with-deps chromium" in text


def test_pir14_recovery_ci_does_not_claim_live_model_or_cutover() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "tools/run_pir13_live_greenfield.py --output-json" not in text
    assert "RUN_ATLAS_LIVE_MODEL" not in text
    assert "legacy retirement" not in text.lower()
    assert "consumer-zero" not in text.lower()


def test_pir14_recovery_ci_covers_current_recovery_entrypoints() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    for test_path in (
        "tests/test_project_intelligence_recovery_baseline.py",
        "tests/test_project_intelligence_pir11_generation_apply.py",
        "tests/test_project_intelligence_pir12_verification_recovery.py",
        "tests/test_project_intelligence_pir13_entrypoint_scenarios.py",
        "tests/test_pir13_live_greenfield_runner.py",
        "tests/test_project_intelligence_consolidation.py",
        "tests/test_project_intelligence_hardening.py",
        "tests/test_project_intelligence_benchmark.py",
    ):
        assert test_path in text
