"""Anvil real-evaluation acceptance.

Drives registered Forge Methods through a live (Anvil-served) model and captures
**natural** fallback evidence: a primary method that genuinely fails the contract on
real model output, after which :class:`MethodPipeline` falls back without forcing.

No file is applied and no proposal is granted readiness; the Safe Apply boundary is
preserved. Readiness is confirmed against the OpenAI-compatible ``/v1/models`` surface
that Anvil exposes once a model is loaded (``/model/switch`` -> ``/model/status`` ready).
When the model is not served the run is recorded as ``anvil_real_eval_pending`` and is
never upgraded to ``passed``.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.model_forge.method_artifacts import InMemoryMethodArtifactStore
from agent.model_forge.method_contracts import (
    CompiledPrompt,
    FallbackStep,
    MethodChain,
    MethodRequest,
)
from agent.model_forge.method_pipeline import MethodPipeline, MethodUnavailableError
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.remaining_adapters import build_method_registry
from agent.model_forge.route_taxonomy import ForgeRoute

HttpGet = Callable[[str, float], tuple[int, str]]
HttpPost = Callable[[str, dict, dict[str, str], float], tuple[int, str]]

# The real failure vocabulary emitted by the structured / edit-intent / anchored
# adapters. The original MethodRouter chains only triggered on a subset
# (``schema_invalid`` / ``missing_edit_anchor`` / ``anchor_not_found``); a weak model
# in practice also fails with ``content_missing`` / ``file_changes_missing``. Natural
# fallback must trigger on what real models actually produce.
NATURAL_FALLBACK_TRIGGERS: list[str] = [
    "schema_invalid",
    "content_missing",
    "file_changes_missing",
    "missing_edit_anchor",
    "invalid_edit_intent",
    "anchor_not_found",
    "empty_output",
    "unsafe_target_path",
    "forbidden_action_type",
    "failed",
    "blocked",
]

_PROOF_PASSED = "anvil_real_eval_passed"
_PROOF_PENDING = "anvil_real_eval_pending"


def _default_get(url: str, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-selected URL.
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")


def _default_post(url: str, payload: dict, headers: dict[str, str], timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-selected URL.
            return int(response.status), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", "replace")


@dataclass
class AnvilReadiness:
    """Result of confirming the model is loaded and served by Anvil."""

    ready: bool
    model_id: str
    base_url: str
    served_models: list[str] = field(default_factory=list)
    detail: str = ""


def check_anvil_ready(
    base_url: str,
    model_id: str,
    *,
    http_get: HttpGet | None = None,
    timeout: float = 30.0,
) -> AnvilReadiness:
    """Confirm ``model_id`` is served at ``{base_url}/v1/models`` (Anvil ready state)."""
    getter = http_get or _default_get
    url = base_url.rstrip("/") + "/v1/models"
    try:
        status, body = getter(url, timeout)
    except Exception as exc:  # noqa: BLE001 - transport failure is pending evidence, not passed.
        return AnvilReadiness(False, model_id, base_url, [], f"transport_error:{type(exc).__name__}")
    if status != 200:
        return AnvilReadiness(False, model_id, base_url, [], f"http_{status}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return AnvilReadiness(False, model_id, base_url, [], "invalid_models_response")
    served = [str(entry.get("id")) for entry in payload.get("data", []) if isinstance(entry, dict) and entry.get("id")]
    ready = model_id in served
    return AnvilReadiness(
        ready=ready,
        model_id=model_id,
        base_url=base_url,
        served_models=served,
        detail="model_served" if ready else "model_not_served",
    )


def make_live_invoker(
    base_url: str,
    model_id: str,
    *,
    http_post: HttpPost | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 120.0,
    transcript: list[dict] | None = None,
) -> Callable[[MethodRequest, CompiledPrompt], str]:
    """Build a :class:`MethodPipeline` invoker backed by an OpenAI-compatible endpoint."""
    poster = http_post or _default_post
    endpoint = base_url.rstrip("/") + "/v1/chat/completions"
    request_headers = dict(headers or {})

    def invoke(request: MethodRequest, prompt: CompiledPrompt) -> str:
        body_payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": prompt.system_text},
                {"role": "user", "content": prompt.prompt_text},
            ],
            "temperature": 0,
            "stream": False,
        }
        try:
            status, body = poster(endpoint, body_payload, request_headers, timeout)
        except Exception as exc:  # noqa: BLE001 - transport failure -> unavailable, not passed.
            raise MethodUnavailableError(f"transport_error:{type(exc).__name__}") from exc
        if status != 200:
            raise MethodUnavailableError(f"http_{status}")
        try:
            response = json.loads(body)
            content = str(response["choices"][0]["message"]["content"] or "")
            response_id = str(response.get("id") or "")
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise MethodUnavailableError(f"malformed_response:{type(exc).__name__}") from exc
        if transcript is not None:
            transcript.append({
                "method_variant": request.method_variant.value,
                "response_id": response_id,
                "raw_output": content,
            })
        return content

    return invoke


@dataclass
class AcceptanceScenario:
    """A single acceptance flow: a goal plus the Method fallback chain to exercise."""

    scenario_id: str
    goal: str
    chain: MethodChain
    allowed_refs: list[str] = field(default_factory=lambda: ["eval_target.txt"])


def natural_fallback_chain(
    chain_id: str,
    primary: MethodVariant,
    fallbacks: list[MethodVariant],
) -> MethodChain:
    """Build a chain whose fallback triggers match the real adapter failure vocabulary."""
    return MethodChain(
        chain_id=chain_id,
        primary=primary,
        fallbacks=[
            FallbackStep(
                method_variant=variant,
                reason=f"natural_fallback->{variant.value}",
                trigger_on=list(NATURAL_FALLBACK_TRIGGERS),
            )
            for variant in fallbacks
        ],
        stop_on=["passed"],
        hard_fail_on=["proposal_bypass", "safe_apply_bypass", "verification_bypass"],
    )


def default_scenarios() -> list[AcceptanceScenario]:
    """Acceptance scenarios that drive real models toward a natural fallback.

    Each starts from a strict structured/edit method that a weak local model tends to
    fail, then degrades through edit-intent and anchored editing before a review-only
    terminal that recovers without applying any file.
    """
    return [
        AcceptanceScenario(
            scenario_id="structured_to_review",
            goal="Create eval_target.txt with content exactly ok.",
            chain=natural_fallback_chain(
                "anvil-structured-to-review",
                MethodVariant.STRUCTURED_PATCH_JSON,
                [
                    MethodVariant.EDIT_INTENT_LIST,
                    MethodVariant.ANCHORED_EDIT_BLOCK,
                    MethodVariant.REVIEW_ONLY,
                ],
            ),
        ),
        AcceptanceScenario(
            scenario_id="edit_intent_to_review",
            goal="In eval_target.txt replace the exact anchor old with new.",
            chain=natural_fallback_chain(
                "anvil-edit-intent-to-review",
                MethodVariant.EDIT_INTENT_LIST,
                [MethodVariant.ANCHORED_EDIT_BLOCK, MethodVariant.REVIEW_ONLY],
            ),
        ),
    ]


_BENCHMARK_PRIMARY = {
    "structured_output_fidelity": MethodVariant.STRUCTURED_PATCH_JSON,
    "patch_protocol_fidelity": MethodVariant.PATCH_DSL_JSON,
    "edit_intent_quality": MethodVariant.EDIT_INTENT_LIST,
    "anchor_selection_quality": MethodVariant.ANCHORED_EDIT_BLOCK,
}
_BENCHMARK_GOAL_SUFFIX = {
    MethodVariant.STRUCTURED_PATCH_JSON: "Create eval_target.txt with content exactly ok using action_type create.",
    MethodVariant.PATCH_DSL_JSON: "Write eval_target.txt with content exactly ok using one patch DSL operation.",
    MethodVariant.EDIT_INTENT_LIST: "In eval_target.txt replace the exact anchor old with new.",
    MethodVariant.ANCHORED_EDIT_BLOCK: "In eval_target.txt replace the exact anchor old with new.",
}
_BENCHMARK_FALLBACK_ORDER = [
    MethodVariant.EDIT_INTENT_LIST,
    MethodVariant.ANCHORED_EDIT_BLOCK,
    MethodVariant.REVIEW_ONLY,
]


def benchmark_scenarios(dimensions: list[str] | None = None) -> list[AcceptanceScenario]:
    """Build acceptance scenarios from the real Forge benchmark cases.

    Using the actual evaluation prompts means any failure (and therefore any fallback)
    is genuine benchmark behaviour rather than a forced trigger. Each scenario degrades
    toward a review-only terminal that recovers without applying a file.
    """
    from agent.model_forge.eval_packs import load_eval_packs

    selected = set(dimensions or _BENCHMARK_PRIMARY)
    scenarios: list[AcceptanceScenario] = []
    for pack in load_eval_packs():
        if pack.dimension not in selected or pack.dimension not in _BENCHMARK_PRIMARY:
            continue
        primary = _BENCHMARK_PRIMARY[pack.dimension]
        fallbacks = [variant for variant in _BENCHMARK_FALLBACK_ORDER if variant != primary]
        for case in pack.cases:
            scenarios.append(AcceptanceScenario(
                scenario_id=f"{pack.dimension}:{case.case_id}",
                goal=f"Evaluation case: {case.prompt}. {_BENCHMARK_GOAL_SUFFIX[primary]}",
                chain=natural_fallback_chain(f"anvil-{case.case_id}", primary, fallbacks),
            ))
    return scenarios


class AnvilAcceptanceRunner:
    """Run acceptance scenarios against a live model and persist truthful evidence."""

    def __init__(
        self,
        evidence_dir: str | Path,
        *,
        http_get: HttpGet | None = None,
        http_post: HttpPost | None = None,
    ) -> None:
        self._evidence_dir = Path(evidence_dir)
        self._http_get = http_get
        self._http_post = http_post

    def run(
        self,
        *,
        provider_id: str,
        model_id: str,
        base_url: str,
        scenarios: list[AcceptanceScenario] | None = None,
        timeout_seconds: float = 120.0,
    ) -> dict:
        run_id = "anvil_eval_" + uuid4().hex[:12]
        readiness = check_anvil_ready(base_url, model_id, http_get=self._http_get)
        if not readiness.ready:
            return self._write_report({
                "run_id": run_id,
                "provider_id": provider_id,
                "model_id": model_id,
                "base_url": base_url,
                "proof_level": _PROOF_PENDING,
                "anvil_ready": False,
                "readiness_detail": readiness.detail,
                "served_models": readiness.served_models,
                "natural_fallback_observed": False,
                "natural_fallback_recovered": False,
                "scenarios": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        scenarios = scenarios or default_scenarios()
        store = InMemoryMethodArtifactStore()
        registry = build_method_registry(store)
        scenario_reports: list[dict] = []
        for scenario in scenarios:
            transcript: list[dict] = []
            invoke = make_live_invoker(
                base_url,
                model_id,
                http_post=self._http_post,
                timeout=timeout_seconds,
                transcript=transcript,
            )
            pipeline = MethodPipeline(registry, invoke)
            request = MethodRequest(
                request_id=f"{run_id}-{scenario.scenario_id}-{uuid4().hex[:6]}",
                route=ForgeRoute.PATCH_DSL,
                method_variant=scenario.chain.primary,
                model_id=model_id,
                provider_id=provider_id,
                goal=scenario.goal,
                allowed_refs=scenario.allowed_refs,
                output_contract="Follow the selected method contract exactly.",
                verification_contract="No file is applied; output is contract-evaluated only.",
            )
            result = pipeline.run(request, scenario.chain)
            attempts = [
                {
                    "method_variant": attempt.method_variant.value,
                    "status": attempt.status,
                    "errors": attempt.errors,
                    "blocked_reasons": attempt.blocked_reasons,
                    "unavailable_reasons": attempt.unavailable_reasons,
                }
                for attempt in result.attempts
            ]
            natural_fallback = len(result.attempts) > 1 and bool(result.fallback_reasons)
            recovered = natural_fallback and result.final_status == "passed"
            scenario_reports.append({
                "scenario_id": scenario.scenario_id,
                "chain_id": scenario.chain.chain_id,
                "primary": scenario.chain.primary.value,
                "selected_method": result.selected_method.value,
                "final_status": result.final_status,
                "attempts": attempts,
                "fallback_reasons": result.fallback_reasons,
                "blocked_reasons": result.blocked_reasons,
                "natural_fallback": natural_fallback,
                "natural_fallback_recovered": recovered,
                "raw_output_ref": self._write_transcript(run_id, scenario.scenario_id, transcript),
            })

        any_fallback = any(item["natural_fallback"] for item in scenario_reports)
        any_recovered = any(item["natural_fallback_recovered"] for item in scenario_reports)
        proof_level = _PROOF_PASSED if (readiness.ready and any_recovered) else _PROOF_PENDING
        return self._write_report({
            "run_id": run_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "base_url": base_url,
            "proof_level": proof_level,
            "anvil_ready": True,
            "readiness_detail": readiness.detail,
            "served_models": readiness.served_models,
            "natural_fallback_observed": any_fallback,
            "natural_fallback_recovered": any_recovered,
            "scenarios": scenario_reports,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    def _write_transcript(self, run_id: str, scenario_id: str, transcript: list[dict]) -> str:
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        path = self._evidence_dir / f"{run_id}.{scenario_id}.transcript.json"
        path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def _write_report(self, report: dict) -> dict:
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        path = self._evidence_dir / f"{report['run_id']}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_ref"] = str(path)
        return report
