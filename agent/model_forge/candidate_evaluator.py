"""Candidate evaluator foundation (PFG-15).

Mechanically evaluate an Arena/Forge candidate's output. This is deliberately a
non-LLM evaluator: it runs contract/schema/syntax/static checks, applies workspace
and safety policy, folds in any supplied test/runtime evidence, and aggregates a
score with explicit rejection reasons.

Three invariants:

- invalid outputs are rejected (hard reject conditions short-circuit the verdict);
- an evaluator with no evidence is reported ``unavailable`` and is NEVER counted as
  passed (``unavailable`` does not raise the score and does not satisfy a required
  evaluator);
- an LLM judge is not required; any LLM review may only be advisory and must not
  override a mechanical failure.

Evidence is optional: a field left ``None`` means "no evidence supplied" and yields
``unavailable``. An explicit value means the caller measured it.
"""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent.model_forge.schema import (
    FORGE_SCHEMA_VERSION,
    CandidateScore,
    ForgeExecutionResult,
    ForgeModel,
)


class EvaluatorOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    # No evidence available. Explicitly distinct from PASSED.
    UNAVAILABLE = "unavailable"


class EvaluatorResult(ForgeModel):
    name: str
    outcome: EvaluatorOutcome
    # 0.0..1.0 contribution; only meaningful for PASSED/FAILED.
    score: float = 0.0
    detail: str = ""
    # When True a FAILED outcome immediately rejects the candidate.
    hard_gate: bool = False


class CandidateEvaluationInput(ForgeModel):
    """Mechanical evidence about one candidate. Optional bool fields use ``None`` to
    mean "not measured" (-> unavailable); a concrete value means the caller measured it.
    """

    candidate_id: str = Field(min_length=1)
    execution_result: ForgeExecutionResult
    # Output contract: "json" | "text" | "patch" | "" (unknown). Drives schema check.
    output_contract: str = ""
    raw_output: str = ""
    # Provide for json contract: the already-parsed object (None -> evaluator parses raw).
    parsed_output: object | None = None
    # Code artifacts {path: source} and the language used for static checks.
    code_artifacts: dict[str, str] = Field(default_factory=dict)
    code_language: str = ""

    # --- workspace / safety policy evidence ---
    changed_paths: list[str] | None = None
    allowed_paths: list[str] | None = None
    test_deletion_detected: bool | None = None
    public_api_changed: bool | None = None
    blueprint_approved_api_change: bool = False
    privacy_violation_detected: bool | None = None
    unsafe_runtime_path_detected: bool | None = None
    bypass_safe_apply_detected: bool | None = None

    # --- test / runtime evidence ---
    focused_tests_passed: bool | None = None
    related_tests_passed: bool | None = None
    portal_runtime_passed: bool | None = None
    requirement_coverage_ratio: float | None = None

    # --- cost / latency / privacy penalty inputs ---
    latency_budget_ms: int | None = None
    cost_budget_units: float | None = None
    cost_units: float | None = None
    privacy_penalty: float | None = None


class CandidateEvaluation(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    candidate_id: str
    evaluators: list[EvaluatorResult] = Field(default_factory=list)
    score: CandidateScore

    @property
    def verdict(self) -> str:
        return self.score.verdict


VERDICT_ELIGIBLE = "eligible"
VERDICT_REJECTED = "rejected"


class CandidateEvaluator:
    """Run mechanical evaluators in the design's order and aggregate a score."""

    def evaluate(self, inp: CandidateEvaluationInput) -> CandidateEvaluation:
        results: list[EvaluatorResult] = [
            self._contract_parse(inp),
            self._schema_format(inp),
            self._syntax_static(inp),
            self._workspace_policy(inp),
            self._focused_tests(inp),
            self._related_tests(inp),
            self._portal_runtime(inp),
            self._requirement_coverage(inp),
            self._risk_minimality(inp),
            self._cost_latency_privacy(inp),
        ]

        blocked: list[str] = []
        # Hard gates reject immediately and unconditionally.
        for r in results:
            if r.hard_gate and r.outcome == EvaluatorOutcome.FAILED:
                blocked.append(f"{r.name}:{r.detail}" if r.detail else r.name)
        # Any non-gate mechanical failure also rejects (e.g. failing focused tests).
        for r in results:
            if not r.hard_gate and r.outcome == EvaluatorOutcome.FAILED:
                blocked.append(f"{r.name}:{r.detail}" if r.detail else r.name)

        scored = [r for r in results if r.outcome in (EvaluatorOutcome.PASSED, EvaluatorOutcome.FAILED)]
        if scored:
            final = round(sum(r.score for r in scored) / len(scored), 4)
        else:
            final = 0.0

        verdict = VERDICT_REJECTED if blocked else VERDICT_ELIGIBLE
        if verdict == VERDICT_REJECTED:
            final = 0.0

        score = CandidateScore(
            candidate_id=inp.candidate_id,
            scores={r.name: r.score for r in results},
            final_score=final,
            verdict=verdict,
            blocked_reasons=blocked,
        )
        return CandidateEvaluation(candidate_id=inp.candidate_id, evaluators=results, score=score)

    # ----- individual evaluators -----

    @staticmethod
    def _contract_parse(inp: CandidateEvaluationInput) -> EvaluatorResult:
        res: ForgeExecutionResult = inp.execution_result
        if not res.contract_valid:
            detail = ";".join(res.errors) if res.errors else "contract_invalid"
            return EvaluatorResult(name="contract_parse", outcome=EvaluatorOutcome.FAILED,
                                   score=0.0, detail=detail, hard_gate=True)
        if not (inp.raw_output or res.raw_output_ref or inp.parsed_output is not None):
            return EvaluatorResult(name="contract_parse", outcome=EvaluatorOutcome.FAILED,
                                   score=0.0, detail="empty_output", hard_gate=True)
        return EvaluatorResult(name="contract_parse", outcome=EvaluatorOutcome.PASSED, score=1.0)

    @staticmethod
    def _schema_format(inp: CandidateEvaluationInput) -> EvaluatorResult:
        contract = (inp.output_contract or "").lower()
        if contract == "json":
            obj = inp.parsed_output
            if obj is None and inp.raw_output:
                import json
                try:
                    obj = json.loads(inp.raw_output)
                except (ValueError, TypeError) as exc:
                    return EvaluatorResult(name="schema_format", outcome=EvaluatorOutcome.FAILED,
                                           score=0.0, detail=f"json_parse_error:{type(exc).__name__}",
                                           hard_gate=True)
            if obj is None:
                return EvaluatorResult(name="schema_format", outcome=EvaluatorOutcome.UNAVAILABLE,
                                       detail="no_json_payload")
            if not isinstance(obj, (dict, list)):
                return EvaluatorResult(name="schema_format", outcome=EvaluatorOutcome.FAILED,
                                       score=0.0, detail="json_not_object_or_array", hard_gate=True)
            return EvaluatorResult(name="schema_format", outcome=EvaluatorOutcome.PASSED, score=1.0)
        if not contract:
            return EvaluatorResult(name="schema_format", outcome=EvaluatorOutcome.UNAVAILABLE,
                                   detail="no_output_contract")
        # text/patch/other: format presence only.
        ok = bool(inp.raw_output or inp.execution_result.raw_output_ref)
        return EvaluatorResult(name="schema_format",
                               outcome=EvaluatorOutcome.PASSED if ok else EvaluatorOutcome.UNAVAILABLE,
                               score=1.0 if ok else 0.0,
                               detail="" if ok else "no_output_to_check")

    @staticmethod
    def _syntax_static(inp: CandidateEvaluationInput) -> EvaluatorResult:
        if not inp.code_artifacts:
            return EvaluatorResult(name="syntax_static", outcome=EvaluatorOutcome.UNAVAILABLE,
                                   detail="no_code_artifacts")
        lang = (inp.code_language or "").lower()
        if lang != "python":
            return EvaluatorResult(name="syntax_static", outcome=EvaluatorOutcome.UNAVAILABLE,
                                   detail=f"no_static_checker_for:{lang or 'unknown'}")
        for path, source in inp.code_artifacts.items():
            try:
                compile(source, path or "<candidate>", "exec")
            except SyntaxError as exc:
                return EvaluatorResult(name="syntax_static", outcome=EvaluatorOutcome.FAILED,
                                       score=0.0, detail=f"syntax_error:{path}:{exc.lineno}", hard_gate=True)
        return EvaluatorResult(name="syntax_static", outcome=EvaluatorOutcome.PASSED, score=1.0)

    @staticmethod
    def _workspace_policy(inp: CandidateEvaluationInput) -> EvaluatorResult:
        # Hard safety gates first.
        if inp.bypass_safe_apply_detected:
            return EvaluatorResult(name="workspace_policy", outcome=EvaluatorOutcome.FAILED,
                                   score=0.0, detail="safe_apply_bypass", hard_gate=True)
        if inp.test_deletion_detected:
            return EvaluatorResult(name="workspace_policy", outcome=EvaluatorOutcome.FAILED,
                                   score=0.0, detail="test_deletion_or_weakening", hard_gate=True)
        if inp.public_api_changed and not inp.blueprint_approved_api_change:
            return EvaluatorResult(name="workspace_policy", outcome=EvaluatorOutcome.FAILED,
                                   score=0.0, detail="public_api_change_without_blueprint", hard_gate=True)
        if inp.privacy_violation_detected:
            return EvaluatorResult(name="workspace_policy", outcome=EvaluatorOutcome.FAILED,
                                   score=0.0, detail="privacy_policy_violation", hard_gate=True)
        if inp.unsafe_runtime_path_detected:
            return EvaluatorResult(name="workspace_policy", outcome=EvaluatorOutcome.FAILED,
                                   score=0.0, detail="unsafe_runtime_path", hard_gate=True)
        if inp.changed_paths is not None and inp.allowed_paths is not None:
            allowed = set(inp.allowed_paths)
            unrelated = [p for p in inp.changed_paths if p not in allowed]
            if unrelated:
                return EvaluatorResult(name="workspace_policy", outcome=EvaluatorOutcome.FAILED,
                                       score=0.0, detail=f"unrelated_edit:{unrelated[0]}", hard_gate=True)
            return EvaluatorResult(name="workspace_policy", outcome=EvaluatorOutcome.PASSED, score=1.0)
        return EvaluatorResult(name="workspace_policy", outcome=EvaluatorOutcome.UNAVAILABLE,
                               detail="no_change_summary")

    @staticmethod
    def _bool_evaluator(name: str, value: bool | None, missing_detail: str) -> EvaluatorResult:
        if value is None:
            return EvaluatorResult(name=name, outcome=EvaluatorOutcome.UNAVAILABLE, detail=missing_detail)
        if value:
            return EvaluatorResult(name=name, outcome=EvaluatorOutcome.PASSED, score=1.0)
        return EvaluatorResult(name=name, outcome=EvaluatorOutcome.FAILED, score=0.0, detail="failed")

    def _focused_tests(self, inp: CandidateEvaluationInput) -> EvaluatorResult:
        return self._bool_evaluator("focused_tests", inp.focused_tests_passed, "no_focused_test_evidence")

    def _related_tests(self, inp: CandidateEvaluationInput) -> EvaluatorResult:
        return self._bool_evaluator("related_tests", inp.related_tests_passed, "no_related_test_evidence")

    def _portal_runtime(self, inp: CandidateEvaluationInput) -> EvaluatorResult:
        return self._bool_evaluator("portal_runtime", inp.portal_runtime_passed, "no_portal_runtime_evidence")

    @staticmethod
    def _requirement_coverage(inp: CandidateEvaluationInput) -> EvaluatorResult:
        ratio = inp.requirement_coverage_ratio
        if ratio is None:
            return EvaluatorResult(name="requirement_coverage", outcome=EvaluatorOutcome.UNAVAILABLE,
                                   detail="no_coverage_evidence")
        ratio = max(0.0, min(1.0, ratio))
        if ratio <= 0.0:
            return EvaluatorResult(name="requirement_coverage", outcome=EvaluatorOutcome.FAILED,
                                   score=0.0, detail="zero_coverage")
        return EvaluatorResult(name="requirement_coverage", outcome=EvaluatorOutcome.PASSED, score=ratio)

    @staticmethod
    def _risk_minimality(inp: CandidateEvaluationInput) -> EvaluatorResult:
        # Mechanical minimality proxy: a bounded change-set is lower risk. Without a
        # change summary this stays explicitly unavailable (never a silent pass).
        if inp.changed_paths is None:
            return EvaluatorResult(name="risk_minimality", outcome=EvaluatorOutcome.UNAVAILABLE,
                                   detail="no_change_summary")
        n = len(inp.changed_paths)
        score = 1.0 if n <= 1 else max(0.0, 1.0 - 0.1 * (n - 1))
        return EvaluatorResult(name="risk_minimality", outcome=EvaluatorOutcome.PASSED,
                               score=round(score, 4), detail=f"changed_files:{n}")

    @staticmethod
    def _cost_latency_privacy(inp: CandidateEvaluationInput) -> EvaluatorResult:
        penalties: list[str] = []
        score = 1.0
        measured = False
        latency = inp.execution_result.latency_ms
        if inp.latency_budget_ms is not None and latency:
            measured = True
            if latency > inp.latency_budget_ms:
                over = latency / max(1, inp.latency_budget_ms)
                score -= min(0.5, 0.25 * (over - 1.0))
                penalties.append(f"latency_over_budget:{latency}>{inp.latency_budget_ms}")
        if inp.cost_budget_units is not None and inp.cost_units is not None:
            measured = True
            if inp.cost_units > inp.cost_budget_units:
                score -= min(0.5, 0.25)
                penalties.append("cost_over_budget")
        if inp.privacy_penalty is not None:
            measured = True
            score -= max(0.0, min(1.0, inp.privacy_penalty))
            if inp.privacy_penalty > 0:
                penalties.append("privacy_penalty")
        if not measured:
            return EvaluatorResult(name="cost_latency_privacy", outcome=EvaluatorOutcome.UNAVAILABLE,
                                   detail="no_cost_latency_privacy_evidence")
        return EvaluatorResult(name="cost_latency_privacy", outcome=EvaluatorOutcome.PASSED,
                               score=round(max(0.0, score), 4), detail=";".join(penalties))


__all__ = [
    "EvaluatorOutcome",
    "EvaluatorResult",
    "CandidateEvaluationInput",
    "CandidateEvaluation",
    "CandidateEvaluator",
    "VERDICT_ELIGIBLE",
    "VERDICT_REJECTED",
]
