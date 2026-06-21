"""Proof Ledger for Twin / Forge / Git Steward decisions."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from agent.twin_control_plane.contracts import ExecutionPolicy, TwinBrief, TwinControlPlaneModel
from agent.twin_control_plane.patch_impact_gate import PatchImpactReport


class ProofLedgerEntry(TwinControlPlaneModel):
    entry_id: str = Field(min_length=1)
    requirement_ref: str = ""
    plan_item_ref: str = ""
    policy_id: str = ""
    brief_id: str = ""
    model_id: str = ""
    provider_id: str = ""
    git_base_ref: str = ""
    git_head_ref: str = ""
    git_commit_sha: str = ""
    before_twin_revision_id: str = ""
    after_twin_revision_id: str = ""
    test_refs: list[str] = Field(default_factory=list)
    runtime_evidence_refs: list[str] = Field(default_factory=list)
    gate_refs: list[str] = Field(default_factory=list)
    decision: str = ""
    accepted: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    repair_reasons: list[str] = Field(default_factory=list)
    proof_requirements: list[str] = Field(default_factory=list)
    forge_stage: str = ""
    method_variant: str = ""
    method_fallbacks: list[str] = Field(default_factory=list)
    forge_evaluation_refs: list[str] = Field(default_factory=list)


class ProofLedger(TwinControlPlaneModel):
    ledger_id: str = Field(min_length=1)
    entries: list[ProofLedgerEntry] = Field(default_factory=list)


def create_proof_ledger_entry(
    *,
    requirement_ref: str,
    plan_item_ref: str,
    policy: ExecutionPolicy,
    brief: TwinBrief,
    patch_report: PatchImpactReport,
    model_id: str = "",
    provider_id: str = "",
) -> ProofLedgerEntry:
    """Create a ledger entry that explains accepted and blocked outcomes."""
    entry_id = f"proof_ledger:{plan_item_ref or 'plan'}:{patch_report.report_id}"
    return ProofLedgerEntry(
        entry_id=entry_id,
        requirement_ref=requirement_ref,
        plan_item_ref=plan_item_ref,
        policy_id=policy.policy_id,
        brief_id=brief.brief_id,
        model_id=model_id,
        provider_id=provider_id,
        git_base_ref=patch_report.base_ref,
        git_head_ref=patch_report.head_ref,
        git_commit_sha=patch_report.git_commit_sha,
        before_twin_revision_id=patch_report.before_twin_revision_id,
        after_twin_revision_id=patch_report.after_twin_revision_id,
        test_refs=[*patch_report.passed_evidence_refs, *patch_report.failed_evidence_refs, *patch_report.unavailable_evidence_refs],
        runtime_evidence_refs=[*patch_report.passed_evidence_refs, *patch_report.failed_evidence_refs, *patch_report.unavailable_evidence_refs],
        gate_refs=list(patch_report.gate_refs),
        decision=patch_report.decision.value,
        accepted=patch_report.accepted,
        blocked_reasons=list(patch_report.blocked_reasons),
        repair_reasons=list(patch_report.repair_reasons),
        proof_requirements=list(patch_report.proof_requirements),
    )


def append_proof_entry(ledger: ProofLedger, entry: ProofLedgerEntry) -> ProofLedger:
    entries = [existing for existing in ledger.entries if existing.entry_id != entry.entry_id]
    entries.append(entry)
    entries.sort(key=lambda item: item.entry_id)
    return ledger.model_copy(update={"entries": entries})


class ProofLedgerStore:
    """Durable, append-only Proof Ledger persistence (one JSONL file per ledger).

    Entries survive reload and are idempotent by ``entry_id``: re-appending the same
    entry id replaces the prior line rather than duplicating it, so a retried run does not
    inflate the ledger. Raw decision evidence is preserved; nothing is mutated in place
    beyond the same-id replacement."""

    def __init__(self, store_dir: str | Path) -> None:
        self._dir = Path(store_dir)

    def _path(self, ledger_id: str) -> Path:
        safe = (ledger_id or "default").replace("/", "_").replace(":", "_")
        return self._dir / f"{safe}.jsonl"

    def append(self, entry: ProofLedgerEntry, *, ledger_id: str = "default") -> ProofLedgerEntry:
        ledger = self.load(ledger_id)
        ledger = append_proof_entry(ledger, entry)
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path(ledger_id)
        with path.open("w", encoding="utf-8") as fh:
            for item in ledger.entries:
                fh.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return entry

    def load(self, ledger_id: str = "default") -> ProofLedger:
        path = self._path(ledger_id)
        entries: list[ProofLedgerEntry] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    entries.append(ProofLedgerEntry.model_validate_json(line))
        return ProofLedger(ledger_id=ledger_id or "default", entries=entries)


__all__ = [
    "ProofLedger",
    "ProofLedgerEntry",
    "ProofLedgerStore",
    "append_proof_entry",
    "create_proof_ledger_entry",
]
