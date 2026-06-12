"""Forge execution bridge for the Atlas LLM JSON boundary (PFH-4/PFH-5).

The bridge wraps the existing ``atlas_llm_json_fn`` callable. Legacy Atlas remains
authoritative unless an acknowledged cutover record is active for the selected stage.
Shadow mode records advisory evidence without changing production routing; cutover
mode returns Forge output only when it is valid, with legacy fallback kept available.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter, call_llm_json
from agent.atlas_llm_json_adapter_schema import AtlasLLMJsonRequest, AtlasLLMJsonResult
from agent.model_forge.provider_policy import select_eligible_provider_ids
from agent.model_forge.providers.legacy_atlas import LEGACY_ATLAS_PROVIDER_ID
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ForgeExecutionRequest, ForgeExecutionResult, ForgeUsage
from agent.model_forge.shadow import compare_stage
from agent.model_forge.source_policy import PrivacyMode, SourceMode
from agent.model_forge.stage_matrix import StageCandidate, StageSelector
from agent.model_forge.stage_taxonomy import ForgeStage, StageMode

LegacyJsonFn = Callable[[str, str], dict | None]
ForgeServiceFactory = Callable[[str, str], object]


class ForgeModelExecutionBridge:
    """Callable-compatible bridge around the central Atlas structured-output path."""

    def __init__(
        self,
        *,
        legacy_fn: LegacyJsonFn,
        service_factory: ForgeServiceFactory,
        stage: ForgeStage | str = ForgeStage.PLANNING,
        route_id: ForgeRoute | str = ForgeRoute.SLICED_IMPACT,
        task_category: str = "atlas_llm_json",
    ) -> None:
        self._legacy_fn = legacy_fn
        self._service_factory = service_factory
        self._stage = ForgeStage(stage)
        self._route_id = ForgeRoute(route_id)
        self._task_category = str(task_category or "atlas_llm_json")

    def with_progress(self, on_progress: Callable[[dict], None] | None) -> "ForgeModelExecutionBridge":
        legacy = self._legacy_fn
        if hasattr(legacy, "with_progress"):
            legacy = legacy.with_progress(on_progress)  # type: ignore[assignment, attr-defined]
        return ForgeModelExecutionBridge(
            legacy_fn=legacy,
            service_factory=self._service_factory,
            stage=self._stage,
            route_id=self._route_id,
            task_category=self._task_category,
        )

    def __call__(self, system_prompt: str, user_prompt: str) -> dict | None:
        start = time.monotonic()
        raw = self._legacy_fn(system_prompt, user_prompt)
        data = raw if isinstance(raw, dict) else None
        result = AtlasLLMJsonResult(
            ok=data is not None,
            data=data or {},
            raw_text="" if isinstance(raw, dict) else str(raw or ""),
            backend="legacy_callable",
            error="" if data is not None else "legacy_empty_or_unparseable",
        )
        metadata = self._observe(
            system_prompt,
            user_prompt,
            request=AtlasLLMJsonRequest(system_prompt=system_prompt, user_prompt=user_prompt),
            legacy_result=result,
            legacy_latency_ms=int((time.monotonic() - start) * 1000),
        )
        if "_routed_data" in metadata:
            routed = metadata.get("_routed_data")
            return routed if isinstance(routed, dict) else None
        return data

    def generate_json(self, request: AtlasLLMJsonRequest) -> AtlasLLMJsonResult:
        start = time.monotonic()
        legacy_result = self._call_legacy_generate_json(request)
        metadata = self._observe(
            request.system_prompt,
            request.user_prompt,
            request=request,
            legacy_result=legacy_result,
            legacy_latency_ms=int((time.monotonic() - start) * 1000),
        )
        if metadata:
            merged = dict(legacy_result.metadata or {})
            public_metadata = self._public_event(metadata)
            merged["forge_execution_bridge"] = public_metadata
            if "_routed_data" in metadata:
                routed = metadata.get("_routed_data")
                return AtlasLLMJsonResult(
                    ok=isinstance(routed, dict),
                    data=routed if isinstance(routed, dict) else {},
                    raw_text="",
                    model=str(metadata.get("routed_model_id") or ""),
                    backend="forge_execution_bridge",
                    structured=bool(request.json_schema or request.grammar),
                    metadata=merged,
                    error="" if isinstance(routed, dict) else "forge_routed_output_invalid",
                )
            return legacy_result.model_copy(update={"metadata": merged})
        return legacy_result

    def _call_legacy_generate_json(self, request: AtlasLLMJsonRequest) -> AtlasLLMJsonResult:
        if hasattr(self._legacy_fn, "generate_json"):
            return self._legacy_fn.generate_json(request)  # type: ignore[attr-defined]
        try:
            data = call_llm_json(
                self._legacy_fn,
                request.system_prompt,
                request.user_prompt,
                json_schema=request.json_schema,
            )
        except Exception as exc:  # noqa: BLE001
            return AtlasLLMJsonResult(
                ok=False,
                backend="legacy_callable",
                error=f"legacy_execution_error:{type(exc).__name__}",
                used_fallback=True,
            )
        return AtlasLLMJsonResult(
            ok=data is not None,
            data=data or {},
            raw_text=json.dumps(data, ensure_ascii=False) if data is not None else "",
            backend="legacy_callable",
            error="" if data is not None else "legacy_empty_or_unparseable",
        )

    def _observe(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        request: AtlasLLMJsonRequest,
        legacy_result: AtlasLLMJsonResult,
        legacy_latency_ms: int,
    ) -> dict:
        metadata = dict(request.metadata or {})
        stage = self._metadata_stage(metadata)
        route_id = self._metadata_route(metadata)
        task_category = str(metadata.get("forge_task_category") or self._task_category)
        request_id = str(metadata.get("forge_request_id") or uuid4().hex)
        source_mode = self._metadata_source_mode(metadata)
        privacy_mode = self._metadata_privacy_mode(metadata)
        event: dict = {
            "schema_version": "forge.execution_bridge.v1",
            "request_id": request_id,
            "stage": stage.value,
            "route_id": route_id.value,
            "task_category": task_category,
            "source_mode": source_mode.value,
            "privacy_mode": privacy_mode.value,
            "legacy_primary": True,
            "legacy_ok": bool(legacy_result.ok),
            "changes_production_routing": False,
            "decision": "legacy_primary",
            "reasons": [],
            "selection": {},
            "shadow": {},
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "prompt_bytes": {
                "system": len(system_prompt.encode("utf-8", "replace")),
                "user": len(user_prompt.encode("utf-8", "replace")),
            },
        }
        service = None
        try:
            service = self._service_factory(system_prompt, user_prompt)
            if "source_mode" not in metadata and hasattr(service, "source_mode"):
                source_mode = service.source_mode()
                event["source_mode"] = source_mode.value
            if not bool(service.forge_enabled()):
                event["decision"] = "forge_disabled_legacy_primary"
                event["reasons"] = ["forge_disabled", "legacy_primary"]
                return self._record_event(service, event)

            request_obj = ForgeExecutionRequest(
                request_id=request_id,
                stage=stage,
                route_id=route_id,
                task_category=task_category,
                risk_level=str(metadata.get("risk_level") or "medium"),
                source_mode=source_mode,
                privacy_mode=privacy_mode,
                candidate_models=list(metadata.get("candidate_models") or []),
                context_package_ref=f"atlas_llm_json:{task_category}",
                output_contract="json_schema" if request.json_schema else "json_object",
                verification_contract="shadow_advisory_only",
            )
            candidates = self._candidates(service, source_mode=source_mode, privacy_mode=privacy_mode)
            selection = StageSelector(service.stage_matrix, profile_store=service.profiles).select(
                stage,
                candidates=candidates,
            )
            event["selection"] = selection.model_dump(mode="json")
            cutover_record = self._cutover_record(service, stage)
            if cutover_record:
                event["cutover"] = cutover_record
            if selection.changes_production_routing:
                if not self._cutover_active(cutover_record):
                    event["decision"] = "active_policy_without_cutover_record_legacy_primary"
                    event["reasons"] = list(selection.reasons) + ["cutover_record_not_active", "legacy_primary"]
                    return self._record_event(service, event)
                if not selection.selected_provider_id:
                    event["decision"] = "forge_primary_unavailable_legacy_fallback"
                    event["reasons"] = list(selection.reasons) + ["no_forge_candidate", "legacy_fallback"]
                    event["fallback"] = {"used": True, "reason": "no_forge_candidate"}
                    return self._record_event(service, event)
                forge_result, forge_output = self._run_forge_shadow(
                    service,
                    provider_id=selection.selected_provider_id,
                    request=request_obj,
                )
                routed = self._parse_json_output(forge_output)
                event["forge_primary"] = {
                    "provider_id": forge_result.provider_id,
                    "model_id": forge_result.model_id,
                    "contract_valid": forge_result.contract_valid,
                    "errors": list(forge_result.errors),
                }
                if forge_result.contract_valid and routed is not None:
                    event["legacy_primary"] = False
                    event["changes_production_routing"] = True
                    event["decision"] = "forge_primary_returned"
                    event["reasons"] = list(selection.reasons) + ["cutover_active", "legacy_fallback_available"]
                    event["fallback"] = {"used": False}
                    event["routed_provider_id"] = forge_result.provider_id
                    event["routed_model_id"] = forge_result.model_id
                    event["_routed_data"] = routed
                    return self._record_event(service, event)
                event["decision"] = "forge_primary_failed_legacy_fallback"
                event["reasons"] = list(selection.reasons) + ["forge_primary_failed", "legacy_fallback"]
                event["fallback"] = {
                    "used": True,
                    "reason": "forge_output_invalid_or_failed",
                    "forge_errors": list(forge_result.errors),
                }
                return self._record_event(service, event)
            if selection.mode != StageMode.SHADOW_SELECT:
                event["decision"] = (
                    "production_routing_deferred_to_pfh5"
                    if selection.changes_production_routing
                    else "legacy_primary_no_shadow"
                )
                event["reasons"] = list(selection.reasons) + ["legacy_primary"]
                return self._record_event(service, event)
            if not selection.selected_provider_id:
                event["decision"] = "shadow_unavailable_legacy_primary"
                event["reasons"] = list(selection.reasons) + ["legacy_primary"]
                return self._record_event(service, event)
            forge_result, forge_output = self._run_forge_shadow(
                service,
                provider_id=selection.selected_provider_id,
                request=request_obj,
            )
            legacy_output = legacy_result.raw_text or json.dumps(legacy_result.data or {}, ensure_ascii=False)
            legacy_forge_result = self._legacy_forge_result(
                request_obj,
                legacy_result=legacy_result,
                legacy_latency_ms=legacy_latency_ms,
                legacy_output=legacy_output,
            )
            comparison = compare_stage(
                stage,
                legacy_result=legacy_forge_result,
                legacy_output=legacy_output,
                forge_result=forge_result,
                forge_output=forge_output,
            )
            shadow_ref = service.shadow.record(comparison)
            event["decision"] = "shadow_recorded_legacy_primary"
            event["reasons"] = list(selection.reasons) + ["legacy_primary", "shadow_advisory_only"]
            event["shadow"] = {
                "comparison_ref": shadow_ref,
                "winner": comparison.winner,
                "regression": comparison.regression,
                "promotable": comparison.promotable,
                "forge_errors": list(forge_result.errors),
            }
            return self._record_event(service, event)
        except Exception as exc:  # noqa: BLE001 - observation must not affect legacy output.
            event["decision"] = "bridge_observation_failed_legacy_primary"
            event["reasons"] = [f"bridge_observation_error:{type(exc).__name__}", "legacy_primary"]
            if service is not None:
                return self._record_event(service, event)
            return event

    def _metadata_stage(self, metadata: dict) -> ForgeStage:
        try:
            return ForgeStage(metadata.get("forge_stage") or self._stage)
        except ValueError:
            return self._stage

    def _metadata_route(self, metadata: dict) -> ForgeRoute:
        try:
            return ForgeRoute(metadata.get("forge_route_id") or self._route_id)
        except ValueError:
            return self._route_id

    def _metadata_source_mode(self, metadata: dict) -> SourceMode:
        try:
            return SourceMode(metadata.get("source_mode") or SourceMode.LOCAL_ONLY)
        except ValueError:
            return SourceMode.LOCAL_ONLY

    def _metadata_privacy_mode(self, metadata: dict) -> PrivacyMode:
        try:
            return PrivacyMode(metadata.get("privacy_mode") or PrivacyMode.NO_EXTERNAL_CODE)
        except ValueError:
            return PrivacyMode.NO_EXTERNAL_CODE

    def _candidates(self, service: object, *, source_mode: SourceMode, privacy_mode: PrivacyMode) -> list[StageCandidate]:
        eligible = set(select_eligible_provider_ids(
            service.registry,
            source_mode=source_mode,
            privacy_mode=privacy_mode,
        ))
        eligible.discard(LEGACY_ATLAS_PROVIDER_ID)
        by_provider: dict[str, list[str]] = {provider_id: [] for provider_id in eligible}
        for model in service.models():
            provider_id = str(model.get("provider_id") or "")
            model_id = str(model.get("model_id") or "")
            if provider_id in eligible and model_id:
                by_provider.setdefault(provider_id, []).append(model_id)
        candidates: list[StageCandidate] = []
        for provider_id in sorted(eligible):
            model_ids = by_provider.get(provider_id) or [provider_id]
            for model_id in model_ids:
                candidates.append(StageCandidate(provider_id=provider_id, model_id=model_id))
        return candidates

    def _run_forge_shadow(
        self,
        service: object,
        *,
        provider_id: str,
        request: ForgeExecutionRequest,
    ) -> tuple[ForgeExecutionResult, str]:
        provider = service.registry.get(provider_id)
        if provider is not None and hasattr(provider, "run_and_capture"):
            return provider.run_and_capture(request)  # type: ignore[attr-defined]
        return service.registry.execute(provider_id, request), ""

    def _parse_json_output(self, output: str) -> dict | None:
        return AtlasLLMJsonAdapter().parse_json_response(output)

    def _cutover_record(self, service: object, stage: ForgeStage) -> dict:
        controller = getattr(service, "cutover_controller", None)
        if controller is None or not hasattr(controller, "load"):
            return {}
        record = controller.load(stage)
        if record is None:
            return {}
        if hasattr(record, "model_dump"):
            return record.model_dump(mode="json")  # type: ignore[call-arg]
        return dict(record) if isinstance(record, dict) else {}

    def _cutover_active(self, record: dict) -> bool:
        return bool(record and record.get("status") == "active" and record.get("forge_primary") is True)

    def _legacy_forge_result(
        self,
        request: ForgeExecutionRequest,
        *,
        legacy_result: AtlasLLMJsonResult,
        legacy_latency_ms: int,
        legacy_output: str,
    ) -> ForgeExecutionResult:
        model_id = str(getattr(self._legacy_fn, "model", "") or LEGACY_ATLAS_PROVIDER_ID)
        return ForgeExecutionResult(
            request_id=request.request_id,
            provider_id=LEGACY_ATLAS_PROVIDER_ID,
            model_id=model_id,
            route_id=request.route_id,
            stage=request.stage,
            contract_valid=bool(legacy_result.ok),
            latency_ms=legacy_latency_ms,
            usage=ForgeUsage(output_tokens=len(legacy_output.split())),
            errors=[] if legacy_result.ok else [legacy_result.error or "legacy_unavailable"],
        )

    def _record_event(self, service: object, event: dict) -> dict:
        if hasattr(service, "record_execution_bridge_event"):
            event = dict(event)
            event["evidence_ref"] = service.record_execution_bridge_event(self._public_event(event))  # type: ignore[attr-defined]
        return event

    def _public_event(self, event: dict) -> dict:
        return {key: value for key, value in event.items() if not str(key).startswith("_")}


__all__ = ["ForgeModelExecutionBridge"]
