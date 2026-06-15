from __future__ import annotations

from agent.twin_control_plane.anti_pattern_memory import (
    AntiPatternEntry,
    AntiPatternMemory,
    AntiPatternSource,
    GuardrailStrength,
    guardrail_hints,
    record_anti_pattern,
    record_from_proof_ledger,
    record_from_repair_compass,
)
from agent.twin_control_plane.proof_ledger import ProofLedgerEntry
from agent.twin_control_plane.repair_compass import RepairCompassReport, RepairInstruction, RepairCategory


def test_repeated_test_weakening_attempts_become_hard_guardrail_hint() -> None:
    memory = AntiPatternMemory(memory_id="memory1")
    entry = AntiPatternEntry(
        pattern_id="test_weakening",
        title="Model weakens failing tests instead of fixing behavior",
        description="Rejected patch tried to delete or weaken required tests.",
        source=AntiPatternSource.REJECTED_PATCH,
        categories=["test_weakening"],
        evidence_refs=["proof://1"],
        model_ids=["local-coder"],
        routes=["blueprint_slice"],
        confidence=0.72,
    )

    memory = record_anti_pattern(memory, entry)
    memory = record_anti_pattern(memory, entry.model_copy(update={"evidence_refs": ["proof://2"], "confidence": 0.86}))
    hints = guardrail_hints(memory, model_id="local-coder", route="blueprint_slice")

    assert len(hints) == 1
    assert hints[0].strength == GuardrailStrength.HARD
    assert hints[0].confidence == 0.86
    assert hints[0].evidence_refs == ["proof://1", "proof://2"]
    assert "Do not weaken tests or gates" in hints[0].text


def test_environment_issue_is_not_memorized_as_product_regression_truth() -> None:
    report = RepairCompassReport(
        report_id="repair1",
        patch_report_id="patch1",
        policy_id="policy1",
        environment_unavailable_refs=["runtime://portal"],
        instructions=[
            RepairInstruction(
                instruction_id="repair1:environment",
                category=RepairCategory.ENVIRONMENT_UNAVAILABLE,
                summary="runtime unavailable",
            )
        ],
    )

    memory = record_from_repair_compass(
        AntiPatternMemory(memory_id="memory1"),
        report,
        source_ref="repair://1",
        confidence=0.65,
    )
    hint = guardrail_hints(memory)[0]

    assert memory.entries[0].environment_related is True
    assert memory.entries[0].product_regression is False
    assert hint.strength == GuardrailStrength.ADVISORY
    assert "Keep unavailable evidence separate" in hint.text


def test_memory_entry_round_trips_with_evidence_refs_and_confidence() -> None:
    entry = AntiPatternEntry(
        pattern_id="schema_migration_gap",
        title="Migration proof omitted",
        description="Schema change accepted without migration proof in a rejected patch.",
        source=AntiPatternSource.PROOF_LEDGER,
        categories=["schema", "migration"],
        evidence_refs=["ledger://1", "schema://finding"],
        routes=["macro_feature"],
        project_refs=["agent/service.py"],
        confidence=0.81,
        occurrences=2,
    )

    restored = AntiPatternEntry.model_validate(entry.model_dump())

    assert restored.evidence_refs == ["ledger://1", "schema://finding"]
    assert restored.confidence == 0.81
    assert restored.occurrences == 2


def test_low_confidence_or_evidence_free_entries_do_not_become_guardrails() -> None:
    memory = AntiPatternMemory(memory_id="memory1", entries=[
        AntiPatternEntry(
            pattern_id="no_evidence",
            title="Unproven claim",
            description="No evidence should prevent prompt guardrail promotion.",
            source=AntiPatternSource.RUNTIME_INCIDENT,
            categories=["state"],
            confidence=0.9,
        ),
        AntiPatternEntry(
            pattern_id="low_confidence",
            title="Weak signal",
            description="Low confidence should stay out of guardrails.",
            source=AntiPatternSource.RUNTIME_INCIDENT,
            categories=["state"],
            evidence_refs=["runtime://1"],
            confidence=0.2,
        ),
    ])

    assert guardrail_hints(memory, min_confidence=0.5) == []


def test_proof_ledger_source_records_model_and_route_specific_weakness() -> None:
    ledger_entry = ProofLedgerEntry(
        entry_id="ledger://entry",
        test_refs=["test://failed"],
        gate_refs=["proof://gate"],
        repair_reasons=["verification_failed"],
    )
    memory = record_from_proof_ledger(
        AntiPatternMemory(memory_id="memory1"),
        ledger_entry,
        pattern_id="local_model_missed_contract",
        title="Local model missed contract-preservation proof",
        categories=["contract", "missing_proof"],
        confidence=0.77,
        model_id="local-coder",
        route="blueprint_slice",
    )
    hints = guardrail_hints(memory, model_id="local-coder", route="blueprint_slice")

    assert memory.entries[0].product_regression is True
    assert hints[0].model_ids == ["local-coder"]
    assert hints[0].routes == ["blueprint_slice"]
    assert hints[0].evidence_refs == ["ledger://entry", "proof://gate", "test://failed"]
