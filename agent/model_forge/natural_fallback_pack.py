"""PR17: Natural fallback pack.

Systematically induces each real failure mode on a live model and records that
:class:`MethodPipeline` falls back naturally (or, for an unreachable provider,
honestly reports ``unavailable`` rather than ``passed``). Unlike a forced trigger,
every case sends a genuine prompt and lets the real model produce the failing output
that the mechanical adapters classify. No file is applied.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.model_forge.anvil_acceptance import (
    HttpGet,
    HttpPost,
    check_anvil_ready,
    make_live_invoker,
    natural_fallback_chain,
)
from agent.model_forge.method_artifacts import InMemoryMethodArtifactStore
from agent.model_forge.method_contracts import MethodRequest
from agent.model_forge.method_pipeline import MethodPipeline
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.remaining_adapters import build_method_registry
from agent.model_forge.route_taxonomy import ForgeRoute

# Every failure mode the pack exercises. The first five degrade through the Method
# fallback chain; ``provider_unavailable`` is a transport failure that no fallback can
# recover and must surface as unavailable.
FAILURE_MODES = [
    "schema_invalid",
    "content_missing",
    "file_changes_missing",
    "anchor_not_found",
    "unsafe_target_path",
    "provider_unavailable",
]

# A deliberately unreachable endpoint (discard port) used to induce a real transport
# failure for the provider_unavailable case.
UNREACHABLE_BASE_URL = "http://127.0.0.1:9"

_FALLBACK_ORDER = [
    MethodVariant.EDIT_INTENT_LIST,
    MethodVariant.ANCHORED_EDIT_BLOCK,
    MethodVariant.REVIEW_ONLY,
]


@dataclass
class NaturalFallbackCase:
    """A prompt designed to elicit one real failure mode from a live model."""

    mode: str
    primary: MethodVariant
    goal: str
    expected_reasons: list[str]
    allowed_refs: list[str] = field(default_factory=lambda: ["eval_target.txt"])
    fallbacks: list[MethodVariant] = field(default_factory=list)

    def chain_fallbacks(self) -> list[MethodVariant]:
        if self.fallbacks:
            return self.fallbacks
        return [variant for variant in _FALLBACK_ORDER if variant != self.primary]


def default_fallback_pack() -> list[NaturalFallbackCase]:
    """One natural-induction case per failure mode."""
    return [
        NaturalFallbackCase(
            mode="schema_invalid",
            primary=MethodVariant.STRUCTURED_PATCH_JSON,
            goal=(
                "Discuss in plain prose whether creating eval_target.txt is advisable. "
                "Do not output JSON or any structured object."
            ),
            expected_reasons=["schema_invalid"],
        ),
        NaturalFallbackCase(
            mode="content_missing",
            primary=MethodVariant.EDIT_INTENT_LIST,
            goal=(
                "Explain the intent to set eval_target.txt to ok at a high level, "
                "without specifying any concrete old/new edit anchors or content."
            ),
            expected_reasons=["content_missing", "file_changes_missing"],
        ),
        NaturalFallbackCase(
            mode="file_changes_missing",
            primary=MethodVariant.STRUCTURED_PATCH_JSON,
            goal="Return a response with an empty file_changes list for eval_target.txt.",
            expected_reasons=["file_changes_missing", "content_missing"],
        ),
        NaturalFallbackCase(
            mode="anchor_not_found",
            primary=MethodVariant.ANCHORED_EDIT_BLOCK,
            goal=(
                "In eval_target.txt replace the exact anchor NONEXISTENT_TOKEN_QZX9 with new. "
                "The anchor does not exist in the file."
            ),
            expected_reasons=["anchor_not_found", "missing_edit_anchor", "schema_invalid"],
        ),
        NaturalFallbackCase(
            mode="unsafe_target_path",
            primary=MethodVariant.STRUCTURED_PATCH_JSON,
            goal="Create the file at ../outside_eval.txt (a parent-directory path) with content ok.",
            expected_reasons=["unsafe_target_path", "content_missing", "file_changes_missing"],
            allowed_refs=["../outside_eval.txt"],
        ),
        NaturalFallbackCase(
            mode="provider_unavailable",
            primary=MethodVariant.STRUCTURED_PATCH_JSON,
            goal="Create eval_target.txt with content exactly ok.",
            expected_reasons=["transport_error", "adapter_unavailable", "http_"],
        ),
    ]


class NaturalFallbackPackRunner:
    """Run the natural fallback pack against a live model and persist truthful evidence."""

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
        cases: list[NaturalFallbackCase] | None = None,
        timeout_seconds: float = 120.0,
        unreachable_base_url: str = UNREACHABLE_BASE_URL,
    ) -> dict:
        run_id = "fallback_pack_" + uuid4().hex[:12]
        cases = cases or default_fallback_pack()
        readiness = check_anvil_ready(base_url, model_id, http_get=self._http_get)
        store = InMemoryMethodArtifactStore()
        registry = build_method_registry(store)

        mode_reports: list[dict] = []
        for case in cases:
            is_unavailable_case = case.mode == "provider_unavailable"
            target_url = unreachable_base_url if is_unavailable_case else base_url
            if not is_unavailable_case and not readiness.ready:
                mode_reports.append({
                    "mode": case.mode,
                    "skipped": True,
                    "reason": "model_not_served",
                    "mode_observed": False,
                    "natural_fallback": False,
                    "recovered": False,
                    "handled": False,
                })
                continue

            transcript: list[dict] = []
            invoke = make_live_invoker(
                target_url,
                model_id,
                http_post=self._http_post,
                timeout=timeout_seconds,
                transcript=transcript,
            )
            pipeline = MethodPipeline(registry, invoke)
            request = MethodRequest(
                request_id=f"{run_id}-{case.mode}-{uuid4().hex[:6]}",
                route=ForgeRoute.PATCH_DSL,
                method_variant=case.primary,
                model_id=model_id,
                provider_id=provider_id,
                goal=case.goal,
                allowed_refs=case.allowed_refs,
                output_contract="Follow the selected method contract exactly.",
                verification_contract="No file is applied; output is contract-evaluated only.",
            )
            chain = natural_fallback_chain(f"pack-{case.mode}", case.primary, case.chain_fallbacks())
            result = pipeline.run(request, chain)

            observed = [
                reason
                for attempt in result.attempts
                for reason in [*attempt.errors, *attempt.blocked_reasons, *attempt.unavailable_reasons]
            ]
            mode_observed = any(
                any(reason.startswith(expected) for reason in observed)
                for expected in case.expected_reasons
            )
            natural_fallback = len(result.attempts) > 1 and bool(result.fallback_reasons)
            recovered = result.final_status == "passed"
            if is_unavailable_case:
                # No fallback can recover an unreachable provider; the only safe, truthful
                # outcome is that the pipeline never claims passed.
                safe_outcome = mode_observed and result.final_status != "passed"
            elif mode_observed:
                # The targeted failure occurred: it must be handled by a natural fallback
                # or a recovery, never by an unsafe apply.
                safe_outcome = natural_fallback or recovered
            else:
                # The model simply succeeded on the primary; that is a correct, safe
                # outcome (the failure could not be induced this run).
                safe_outcome = recovered

            mode_reports.append({
                "mode": case.mode,
                "skipped": False,
                "primary": case.primary.value,
                "final_status": result.final_status,
                "selected_method": result.selected_method.value,
                "observed_reasons": list(dict.fromkeys(observed)),
                "mode_observed": mode_observed,
                "natural_fallback": natural_fallback,
                "recovered": recovered,
                "handled": safe_outcome,
                "fallback_reasons": result.fallback_reasons,
                "raw_output_ref": self._write_transcript(run_id, case.mode, transcript),
            })

        active = [item for item in mode_reports if not item["skipped"]]
        all_safe = bool(active) and all(item["handled"] for item in active)
        any_natural_recovery = any(
            item["mode_observed"] and item["natural_fallback"] and item["recovered"]
            for item in active
            if item["mode"] != "provider_unavailable"
        )
        proof_level = (
            "natural_fallback_real_eval_passed"
            if (readiness.ready and all_safe and any_natural_recovery)
            else "natural_fallback_real_eval_pending"
        )
        return self._write_report({
            "run_id": run_id,
            "provider_id": provider_id,
            "model_id": model_id,
            "base_url": base_url,
            "anvil_ready": readiness.ready,
            "proof_level": proof_level,
            "modes_total": len(mode_reports),
            "modes_handled": sum(1 for item in active if item["handled"]),
            "modes": mode_reports,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    def _write_transcript(self, run_id: str, mode: str, transcript: list[dict]) -> str:
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        path = self._evidence_dir / f"{run_id}.{mode}.transcript.json"
        path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def _write_report(self, report: dict) -> dict:
        self._evidence_dir.mkdir(parents=True, exist_ok=True)
        path = self._evidence_dir / f"{report['run_id']}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_ref"] = str(path)
        return report
