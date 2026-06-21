"""PR21: Frontier verification of weak-LLM evaluation results.

The weak local LLM (8080) produces evaluation outputs that the mechanical adapters
judge pass/fail. This module lets a **frontier model** independently verify, per
benchmark case, whether the weak/mechanical verdict actually reflects the case intent.

Crucial honesty rule: the frontier verdict is *advisory verification only*. It never
upgrades a weak-LLM result. A frontier ``over_claim`` (weak said passed but the case
intent was not really tested/met) or ``under_claim`` (weak said failed but the intent
was met) is recorded as a mismatch; the weak result is left unchanged. When no frontier
judge is configured the verdict is ``unavailable`` (never ``passed``).
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

# A frontier judge receives one case's context and returns (assessment, rationale).
# assessment is one of FRONTIER_ASSESSMENTS.
FrontierJudge = Callable[[dict], "tuple[str, str]"]

FRONTIER_ASSESSMENTS = {
    "confirms_pass",   # frontier agrees the weak 'passed' genuinely meets the case intent
    "confirms_fail",   # frontier agrees the weak 'failed'/'unavailable' is a real failure
    "over_claim",      # weak said passed, but the case intent was not actually tested/met
    "under_claim",     # weak said failed, but the case intent was actually met
    "cannot_assess",   # insufficient evidence to judge
    "unavailable",     # no frontier judge configured
}
_AGREEMENT = {"confirms_pass", "confirms_fail"}
_MISMATCH = {"over_claim", "under_claim"}


@dataclass
class FrontierVerdict:
    dimension: str
    case_id: str
    weak_outcome: str
    mechanical_detail: str
    assessment: str
    agrees: bool
    rationale: str


class StaticFrontierJudge:
    """Replay recorded frontier verdicts deterministically.

    This is an honest record of a frontier model's assessment (keyed by
    ``"{dimension}:{case_id}"``), not an algorithm pretending to reason like a frontier
    model. Unkeyed cases fall back to ``cannot_assess``.
    """

    def __init__(self, verdicts: dict[str, tuple[str, str]]) -> None:
        self._verdicts = dict(verdicts)

    def __call__(self, context: dict) -> tuple[str, str]:
        key = f"{context['dimension']}:{context['case_id']}"
        return self._verdicts.get(key, ("cannot_assess", "no_recorded_frontier_verdict"))


def _agrees(assessment: str, weak_outcome: str) -> bool:
    if assessment == "confirms_pass":
        return weak_outcome == "passed"
    if assessment == "confirms_fail":
        return weak_outcome in {"failed", "unavailable", "blocked"}
    return False


class FrontierVerificationHarness:
    """Pair each weak-LLM/mechanical result with a frontier verdict; flag mismatches."""

    def __init__(self, evidence_dir: str | Path, *, judge: FrontierJudge | None = None) -> None:
        self._evidence_dir = Path(evidence_dir)
        self._judge = judge

    def verify(
        self,
        *,
        run_id: str,
        provider_id: str,
        model_id: str,
        results: list[dict],
        raw_by_case: dict[str, str] | None = None,
    ) -> dict:
        raw_by_case = raw_by_case or {}
        verdicts: list[FrontierVerdict] = []
        for result in results:
            dimension = result["dimension"]
            case_id = result["case_id"]
            weak_outcome = result["outcome"]
            detail = result.get("detail", "")
            key = f"{dimension}:{case_id}"
            if self._judge is None:
                assessment, rationale = "unavailable", "no_frontier_judge_configured"
            else:
                assessment, rationale = self._judge({
                    "dimension": dimension,
                    "case_id": case_id,
                    "weak_outcome": weak_outcome,
                    "detail": detail,
                    "raw_output": raw_by_case.get(key, ""),
                })
                if assessment not in FRONTIER_ASSESSMENTS:
                    assessment, rationale = "cannot_assess", f"invalid_assessment:{assessment}"
            verdicts.append(FrontierVerdict(
                dimension=dimension,
                case_id=case_id,
                weak_outcome=weak_outcome,
                mechanical_detail=detail,
                assessment=assessment,
                agrees=_agrees(assessment, weak_outcome),
                rationale=rationale,
            ))

        assessed = [v for v in verdicts if v.assessment not in {"unavailable", "cannot_assess"}]
        mismatches = [v for v in verdicts if v.assessment in _MISMATCH]
        agreements = [v for v in verdicts if v.assessment in _AGREEMENT]
        if not assessed:
            proof_level = "frontier_verification_pending"
        elif mismatches:
            proof_level = "frontier_verification_mismatch"
        else:
            proof_level = "frontier_verification_passed"
        report = {
            "run_id": run_id,
            "verification_of": run_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "proof_level": proof_level,
            "total_cases": len(verdicts),
            "assessed_cases": len(assessed),
            "agreements": len(agreements),
            "mismatches": [asdict(v) for v in mismatches],
            "verdicts": [asdict(v) for v in verdicts],
            "note": "Frontier verdicts are advisory; weak-LLM results are never upgraded.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return self._write(report)

    def _write(self, report: dict) -> dict:
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        path = self._evidence_dir / f"frontier_verify_{report['run_id']}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_ref"] = str(path)
        return report
