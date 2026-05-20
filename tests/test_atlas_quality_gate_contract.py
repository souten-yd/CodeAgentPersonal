from pathlib import Path


def _assert_contains(path: str, expected: list[str]) -> None:
    text = Path(path).read_text(encoding="utf-8")
    for phrase in expected:
        assert phrase in text, f"Missing '{phrase}' in {path}"


def test_quality_gate_constitution_contract() -> None:
    _assert_contains(
        "docs/atlas_development_constitution.md",
        [
            "Contract Test Quality Rule",
            "Tests must not only assert that strings exist",
            "runtime chain",
            "DOM ID",
            "AtlasPipelineAPI helper",
            "event binding inside bind/init",
            "response unwrap",
            "final `})();`",
            "IIFE-local variables",
            "Definition of Done",
        ],
    )


def test_quality_gate_preflight_contract() -> None:
    _assert_contains(
        "docs/atlas_preflight_checklist.md",
        [
            "Runtime Chain Test Design Preflight",
            "broken cases",
            "Stop implementation",
        ],
    )


def test_quality_gate_postflight_contract() -> None:
    _assert_contains(
        "docs/atlas_postflight_checklist.md",
        [
            "Adversarial Self-Review",
            "Runtime chain verified",
            "Broken cases covered by tests",
            "Remaining untested gaps",
        ],
    )


def test_quality_gate_pr_template_contract() -> None:
    _assert_contains(
        "docs/atlas_pr_template.md",
        [
            "Runtime Chain Evidence",
            "Broken Cases Covered",
            "Adversarial Self-Review",
            "Test that fails if code is outside the IIFE",
        ],
    )


def test_quality_gate_checkpoint_handoff_contract() -> None:
    docs = [
        "docs/atlas_development_handoff.md",
        "docs/atlas_unified_autopilot_checkpoint.md",
        "docs/atlas_autopilot_current_status.md",
        "docs/atlas_autopilot_scale_master_plan.md",
        "docs/atlas_scale_master_roadmap.md",
    ]
    for doc in docs:
        _assert_contains(doc, ["PR-ATLAS-DOCS-QUALITY-GATE-01", "PR-ATLAS-SCALE-65B"])
