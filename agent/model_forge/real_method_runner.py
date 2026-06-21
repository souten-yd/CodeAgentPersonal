"""Real OpenAI-compatible Method evaluation with durable, truthful evidence."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.model_forge.candidate_evaluator import EvaluatorOutcome
from agent.model_forge.eval_packs import CapabilityCase, CaseResult
from agent.model_forge.method_contracts import MethodRequest
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.remaining_adapters import build_method_registry
from agent.model_forge.route_taxonomy import ForgeRoute


HttpPost = Callable[[str, dict, dict[str, str], float], tuple[int, str]]

_METHOD_BY_DIMENSION = {
    "structured_output_fidelity": MethodVariant.STRUCTURED_PATCH_JSON,
    "patch_protocol_fidelity": MethodVariant.PATCH_DSL_JSON,
    "edit_intent_quality": MethodVariant.EDIT_INTENT_LIST,
    "anchor_selection_quality": MethodVariant.ANCHORED_EDIT_BLOCK,
    # PR19: extend live coverage to method-backed dimensions. Dimensions without a
    # mechanical method adapter (abstraction_tolerance, scope_boundary_discipline,
    # context_overload_sensitivity, fallback_recovery) stay mechanical_evaluator_unavailable.
    "large_file_editing": MethodVariant.ANCHORED_EDIT_BLOCK,
    "evidence_discipline": MethodVariant.REVIEW_ONLY,
    "repair_discipline": MethodVariant.REPAIR_COMPASS_STEPS,
}
_EXTERNAL_PROVIDERS = {"openrouter", "openrouter_api"}


def _default_post(url: str, payload: dict, headers: dict[str, str], timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-selected provider URL.
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")


class RealMethodRunner:
    def __init__(self, evidence_dir: str | Path, *, http_post: HttpPost | None = None) -> None:
        self._evidence_dir = Path(evidence_dir)
        self._http_post = http_post or _default_post

    def run_cases(
        self,
        *,
        provider_id: str,
        model_id: str,
        base_url: str,
        cases: list[CapabilityCase],
        source_mode: str = "local_only",
        credential_env: str = "",
        timeout_seconds: float = 120.0,
    ) -> list[CaseResult]:
        if provider_id in _EXTERNAL_PROVIDERS and source_mode == "local_only":
            return [self._unavailable(case, "external_provider_blocked_in_local_only") for case in cases]
        headers: dict[str, str] = {}
        if provider_id in _EXTERNAL_PROVIDERS:
            env_name = credential_env or "OPENROUTER_API_KEY"
            token = os.environ.get(env_name, "")
            if not token:
                return [self._unavailable(case, "credential_unavailable") for case in cases]
            headers["Authorization"] = f"Bearer {token}"
        endpoint = base_url.rstrip("/") + "/v1/chat/completions"
        registry = build_method_registry()
        results: list[CaseResult] = []
        for case in cases:
            method = _METHOD_BY_DIMENSION.get(case.dimension)
            if method is None or not registry.supports(method):
                results.append(self._unavailable(case, "mechanical_evaluator_unavailable"))
                continue
            adapter = registry.get(method)
            request = MethodRequest(
                request_id=f"real-{case.case_id}-{uuid4().hex[:8]}",
                route=ForgeRoute.PATCH_DSL,
                method_variant=method,
                model_id=model_id,
                provider_id=provider_id,
                goal=self._case_goal(case, method),
                allowed_refs=["eval_target.txt"],
                output_contract="Follow the selected method contract exactly.",
                verification_contract="No file is applied; output is contract-evaluated only.",
            )
            prompt = adapter.prepare_prompt(request)
            started = time.monotonic()
            raw = ""
            usage: dict = {}
            response_id = ""
            error = ""
            try:
                status, body = self._http_post(endpoint, {
                    "model": model_id,
                    "messages": [
                        {"role": "system", "content": prompt.system_text},
                        {"role": "user", "content": prompt.prompt_text},
                    ],
                    "temperature": 0,
                    "stream": False,
                }, headers, timeout_seconds)
                if status != 200:
                    error = f"http_{status}"
                else:
                    response = json.loads(body)
                    response_id = str(response.get("id") or "")
                    raw = str(response["choices"][0]["message"]["content"] or "")
                    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
            except Exception as exc:  # noqa: BLE001 - transport failure is unavailable evidence.
                error = f"transport_error:{type(exc).__name__}"
            latency_ms = int((time.monotonic() - started) * 1000)
            if error:
                ref = self._write_evidence(
                    case, provider_id, model_id, base_url, method, "unavailable", raw,
                    usage, latency_ms, error, response_id,
                )
                results.append(CaseResult(
                    case_id=case.case_id,
                    dimension=case.dimension,
                    outcome=EvaluatorOutcome.UNAVAILABLE,
                    detail=error,
                    evidence_refs=[ref],
                ))
                continue
            parsed = adapter.parse_output(request, raw)
            verified = adapter.verify_contract(request, adapter.compile_patch(request, parsed))
            passed = verified.status == "passed" and verified.contract_valid
            outcome = EvaluatorOutcome.PASSED if passed else EvaluatorOutcome.FAILED
            detail = "method_contract_passed" if passed else ",".join([
                *verified.errors, *verified.blocked_reasons,
            ]) or "method_contract_failed"
            ref = self._write_evidence(
                case, provider_id, model_id, base_url, method, outcome.value, raw,
                usage, latency_ms, detail, response_id,
            )
            results.append(CaseResult(
                case_id=case.case_id,
                dimension=case.dimension,
                outcome=outcome,
                detail=detail,
                evidence_refs=[ref],
            ))
        return results

    @staticmethod
    def _case_goal(case: CapabilityCase, method: MethodVariant) -> str:
        concrete = {
            MethodVariant.STRUCTURED_PATCH_JSON: "Create eval_target.txt with content exactly ok using action_type create.",
            MethodVariant.PATCH_DSL_JSON: "Write eval_target.txt with content exactly ok using one patch DSL operation.",
            MethodVariant.EDIT_INTENT_LIST: "In eval_target.txt replace the exact anchor old with new.",
            MethodVariant.ANCHORED_EDIT_BLOCK: "In eval_target.txt replace the exact anchor old with new.",
            MethodVariant.REVIEW_ONLY: "Review eval_target.txt for risk and report findings with severity and evidence; do not produce a patch.",
            MethodVariant.REPAIR_COMPASS_STEPS: "Return a JSON object with a non-empty steps array describing how to repair the failing change in eval_target.txt.",
        }[method]
        return f"Evaluation case: {case.prompt}. {concrete}"

    def _write_evidence(
        self, case: CapabilityCase, provider_id: str, model_id: str, base_url: str,
        method: MethodVariant, outcome: str, raw: str, usage: dict, latency_ms: int,
        detail: str, response_id: str,
    ) -> str:
        evidence_id = "real_method_" + uuid4().hex[:12]
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        raw_path = self._evidence_dir / f"{evidence_id}.raw.txt"
        raw_path.write_text(raw, encoding="utf-8")
        path = self._evidence_dir / f"{evidence_id}.json"
        record = {
            "evidence_id": evidence_id,
            "case_id": case.case_id,
            "dimension": case.dimension,
            "provider_id": provider_id,
            "model_id": model_id,
            "base_url": base_url,
            "response_id": response_id,
            "method_variant": method.value,
            "outcome": outcome,
            "raw_output_ref": str(raw_path),
            "usage": {key: int(value) for key, value in usage.items() if isinstance(value, int)},
            "latency_ms": latency_ms,
            "detail": detail,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    @staticmethod
    def _unavailable(case: CapabilityCase, reason: str) -> CaseResult:
        return CaseResult(
            case_id=case.case_id,
            dimension=case.dimension,
            outcome=EvaluatorOutcome.UNAVAILABLE,
            detail=reason,
        )
