"""Baseline-versus-assisted evaluation through AtlasPatchProposalService."""
from __future__ import annotations

import json
import shutil
import time
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.atlas_journal import AtlasJournal
from agent.atlas_patch_proposal_schema import AtlasPatchProposalRequest, AtlasPatchProposalResult
from agent.atlas_patch_proposal_service import AtlasPatchProposalService
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from agent.model_forge.twin_assist_compiler import compile_assist_metadata
from agent.model_forge.twin_assist_contracts import (
    TwinAssistAttemptResult,
    TwinAssistEvaluationReport,
    TwinAssistRunRequest,
)
from agent.model_forge.twin_assist_eval_packs import (
    aggregate_comparisons,
    compare_twin_assist_case,
    load_twin_assist_cases,
    validate_fixture,
)
from agent.model_forge.twin_assist_taxonomy import TwinAssistMode

ServiceFactory = Callable[[Path, Callable[[str, str], dict | None]], AtlasPatchProposalService]
_EXTERNAL_PROVIDERS = {"openrouter", "openrouter_api"}


class TwinAssistRunner:
    def __init__(self, evidence_root: str | Path, *, service_factory: ServiceFactory | None = None) -> None:
        self._evidence_root = Path(evidence_root)
        self._service_factory = service_factory or self._default_service

    def run(self, request: TwinAssistRunRequest) -> TwinAssistEvaluationReport:
        run_id = "twin_assist_" + uuid4().hex[:12]
        created_at = datetime.now(timezone.utc).isoformat()
        run_root = self._evidence_root / run_id
        run_root.mkdir(parents=True, exist_ok=True)
        cases = load_twin_assist_cases(request.case_ids)
        comparisons = []
        for case in cases:
            baseline = self._run_one(case, TwinAssistMode.NONE, request, run_id, run_root) if request.run_baseline else None
            selected = request.assist_modes or case.assist_modes
            selected = [mode for mode in selected if mode != TwinAssistMode.NONE and mode in case.assist_modes]
            assisted = [self._run_one(case, mode, request, run_id, run_root) for mode in selected]
            comparisons.append(compare_twin_assist_case(case.case_id, baseline, assisted))
        aggregates = aggregate_comparisons(comparisons)
        scored = [item for item in comparisons if item.best_assist_mode is not None]
        recommended = sorted({item.best_assist_mode for item in scored}, key=lambda mode: mode.value)
        status = "passed" if scored else "unavailable"
        report = TwinAssistEvaluationReport(
            run_id=run_id,
            provider_id=request.provider_id,
            model_id=request.model_id,
            status=status,
            comparisons=comparisons,
            aggregate_scores=aggregates,
            recommended_twin_injection_level=max((self._injection_level(mode) for mode in recommended), default=0),
            recommended_assist_modes=recommended,
            evidence_refs=[str(run_root / "report.json")],
            created_at=created_at,
        )
        (run_root / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report

    def _run_one(self, case, mode, request, run_id: str, run_root: Path) -> TwinAssistAttemptResult:
        if request.provider_id in _EXTERNAL_PROVIDERS and request.source_mode.value == "local_only":
            return self._unavailable(case, mode, request, "external_provider_blocked_in_local_only")
        fixture_root = Path(request.project_fixture_root)
        missing = validate_fixture(case, fixture_root)
        if missing:
            return self._unavailable(case, mode, request, "fixture_missing:" + ",".join(missing))
        attempt_id = f"{case.case_id}__{mode.value}"
        attempt_root = run_root / attempt_id
        workspace = attempt_root / "workspace"
        shutil.copytree(fixture_root / case.project_fixture_id, workspace)
        data_root = attempt_root / "ca_data"
        pool_id = "pool_" + uuid4().hex[:10]
        item_id = "item_" + uuid4().hex[:10]
        item = AtlasPlanItem(
            item_id=item_id,
            pool_id=pool_id,
            title=case.title,
            goal=case.user_goal,
            item_type="implementation",
            risk_level="medium",
            status="ready",
            target_files=case.target_files,
            done_definition=[case.expected_behavior] if case.expected_behavior else [],
            metadata={"verification_contract": {"recommended_tests": case.expected_tests}},
        )
        pool = AtlasPlanPool(pool_id=pool_id, root_goal=case.user_goal, project_path=str(workspace), items=[item])
        storage = AtlasPlanPoolStorage(data_root)
        storage.save_pool(pool)
        llm = self._llm_json_fn(request)
        service = self._service_factory(data_root, llm)
        evidence = {
            "safe_edit_briefing": {"target_files": case.target_files, "recommended_tests": case.expected_tests},
            "impact": {"required_refs": case.required_refs},
            "slot": case.metadata.get("slot", {}),
            "deterministic_anchor": case.metadata.get("deterministic_anchor", {}),
        }
        metadata = compile_assist_metadata(assist_mode=mode, evidence=evidence, case=case)
        started = time.monotonic()
        result = service.propose_for_item(AtlasPatchProposalRequest(
            pool_id=pool_id,
            item_id=item_id,
            run_id=f"{run_id}_{uuid4().hex[:6]}",
            source_type="plan_item",
            metadata={**metadata, "twin_assist_evaluation": True},
        ))
        latency_ms = int((time.monotonic() - started) * 1000)
        return self._assess(case, mode, request, result, latency_ms)

    @staticmethod
    def _default_service(data_root: Path, llm_json_fn):
        return AtlasPatchProposalService(
            journal=AtlasJournal(data_root),
            storage=AtlasPlanPoolStorage(data_root),
            llm_json_fn=llm_json_fn,
        )

    @staticmethod
    def _llm_json_fn(request: TwinAssistRunRequest):
        endpoint = request.base_url.rstrip("/") + "/v1/chat/completions"

        def call(system_prompt: str, user_prompt: str) -> dict | None:
            payload = json.dumps({
                "model": request.model_id,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0,
                "stream": False,
            }).encode("utf-8")
            req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=request.timeout_seconds) as response:  # noqa: S310 - operator-selected local endpoint.
                body = json.loads(response.read().decode("utf-8"))
            content = str(body["choices"][0]["message"]["content"] or "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(content)

        return call

    @staticmethod
    def _assess(case, mode, request, result: AtlasPatchProposalResult, latency_ms: int) -> TwinAssistAttemptResult:
        proposal = result.proposal
        metadata = proposal.metadata if proposal is not None else {}
        patch_available = bool((result.metadata or {}).get("patch_content_available"))
        touched = list(proposal.target_files if proposal is not None else [])
        forbidden = [ref for ref in touched if ref in case.forbidden_refs]
        symbols = list(metadata.get("implemented_symbols") or [])
        verification = list(proposal.verification_plan if proposal is not None else [])
        checks = [
            patch_available,
            bool(touched) and set(touched).issubset(set(case.target_files)),
            not forbidden,
            not case.expected_symbols or bool(set(case.expected_symbols) & set(symbols)),
            not case.expected_tests or any(test in " ".join(verification) for test in case.expected_tests),
        ]
        score = round(sum(checks) / len(checks), 4)
        passed = result.status == "proposed" and patch_available and not forbidden
        status = "passed" if passed else ("blocked" if result.status == "blocked" else "failed")
        reasons = [*result.errors, *result.warnings]
        return TwinAssistAttemptResult(
            case_id=case.case_id,
            assist_mode=mode,
            provider_id=request.provider_id,
            model_id=request.model_id,
            status=status,
            score=score,
            patch_content_available=patch_available,
            semantic_passed=passed,
            verification_passed=checks[-1],
            touched_files=touched,
            forbidden_touched=forbidden,
            implemented_symbols=symbols,
            verification_cases=verification,
            latency_ms=latency_ms,
            raw_output_ref=result.proposal_json_path,
            proposal_ref=result.proposal_json_path,
            evidence_refs=[ref for ref in [result.proposal_json_path, result.proposal_md_path] if ref],
            blocked_reasons=reasons if status == "blocked" else [],
            failed_reasons=reasons if status == "failed" else [],
        )

    @staticmethod
    def _unavailable(case, mode, request, reason: str) -> TwinAssistAttemptResult:
        return TwinAssistAttemptResult(
            case_id=case.case_id,
            assist_mode=mode,
            provider_id=request.provider_id,
            model_id=request.model_id,
            status="unavailable",
            unavailable_reasons=[reason],
        )

    @staticmethod
    def _injection_level(mode: TwinAssistMode) -> int:
        return {
            TwinAssistMode.NONE: 0,
            TwinAssistMode.POLICY_ONLY: 1,
            TwinAssistMode.CONSTRAINTS_AND_REFS: 2,
            TwinAssistMode.IMPACT_AND_SAFE_EDIT: 3,
            TwinAssistMode.STRICT_TWIN_BRIEF: 4,
            TwinAssistMode.TWIN_LOCALIZED_SLOT: 4,
            TwinAssistMode.TWIN_DETERMINISTIC_ANCHOR: 4,
        }[mode]
