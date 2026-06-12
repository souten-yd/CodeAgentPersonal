"""Arena runner foundation (PFG-14).

Runs model x route candidates through the provider interface in a NON-applying mode:
it only executes model calls and persists raw outputs + metadata under
ca_data/model_forge/arena_runs/. It never mutates workspace source and never applies a
candidate — every candidate starts and stays adoption_state=not_applied. Adoption
later must go through Proposal/Safe Apply (Arena never bypasses it).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from agent.model_forge.provider_policy import resolve_provider_policy
from agent.model_forge.provider_registry import ProviderRegistry
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import (
    FORGE_SCHEMA_VERSION,
    AdoptionState,
    ArenaCandidate,
    ForgeExecutionRequest,
    ForgeExecutionResult,
    ForgeModel,
    ForgeStage,
)
from agent.model_forge.source_policy import PrivacyMode, SourceMode


class ArenaCandidateSpec(ForgeModel):
    provider_id: str
    model_id: str
    route_id: ForgeRoute


class ArenaRunRecord(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    arena_run_id: str
    stage: ForgeStage
    preset_id: str = ""
    task_id: str = ""
    source_mode: SourceMode
    privacy_mode: PrivacyMode
    created_at: str = ""
    candidates: list[ArenaCandidate] = []


class ArenaRunner:
    def __init__(
        self,
        registry: ProviderRegistry,
        *,
        store_dir: str | Path | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.registry = registry
        self._store_dir = Path(store_dir) if store_dir else None
        self._id_factory = id_factory or (lambda: uuid4().hex[:10])

    def run(
        self,
        *,
        stage: ForgeStage,
        specs: list[ArenaCandidateSpec],
        source_mode: SourceMode | str,
        privacy_mode: PrivacyMode | str,
        preset_id: str = "",
        task_id: str = "",
        arena_run_id: str | None = None,
    ) -> ArenaRunRecord:
        run_id = arena_run_id or f"arena_{self._id_factory()}"
        run_dir = (self._store_dir / run_id) if self._store_dir else None
        if run_dir is not None:
            run_dir.mkdir(parents=True, exist_ok=True)

        candidates: list[ArenaCandidate] = []
        for idx, spec in enumerate(specs):
            candidate_id = f"cand_{run_id}_{idx}"
            request = ForgeExecutionRequest(
                request_id=f"{run_id}_c{idx}",
                stage=stage,
                route_id=spec.route_id,
                source_mode=SourceMode(source_mode),
                privacy_mode=PrivacyMode(privacy_mode),
                candidate_models=[spec.model_id],
            )
            decision = resolve_provider_policy(self.registry, spec.provider_id, source_mode=source_mode, privacy_mode=privacy_mode)
            if not decision.selectable:
                result = ForgeExecutionResult(
                    request_id=request.request_id, provider_id=spec.provider_id,
                    model_id=spec.model_id or spec.provider_id, route_id=spec.route_id, stage=stage,
                    contract_valid=False, errors=[f"policy_blocked:{';'.join(decision.reasons)}"],
                )
                raw = ""
            else:
                result, raw = self._execute_capture(spec.provider_id, request)
            result_ref = self._persist_candidate(run_dir, candidate_id, result, raw)
            candidates.append(ArenaCandidate(
                candidate_id=candidate_id,
                arena_run_id=run_id,
                model_id=spec.model_id or spec.provider_id,
                provider_id=spec.provider_id,
                route_id=spec.route_id,
                preset_id=preset_id,
                task_id=task_id,
                execution_result_ref=result_ref,
                adoption_state=AdoptionState.NOT_APPLIED,  # never auto-applied
            ))

        record = ArenaRunRecord(
            arena_run_id=run_id, stage=stage, preset_id=preset_id, task_id=task_id,
            source_mode=SourceMode(source_mode), privacy_mode=PrivacyMode(privacy_mode),
            created_at=datetime.now(timezone.utc).isoformat(), candidates=candidates,
        )
        if run_dir is not None:
            (run_dir / "arena.json").write_text(
                json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return record

    def _execute_capture(self, provider_id: str, request: ForgeExecutionRequest) -> "tuple[ForgeExecutionResult, str]":
        provider = self.registry.get(provider_id)
        capture = getattr(provider, "run_and_capture", None)
        if callable(capture):
            try:
                return capture(request)
            except Exception as exc:  # noqa: BLE001
                return self._error(request, provider_id, f"arena_execution_error:{type(exc).__name__}"), ""
        try:
            return self.registry.execute(provider_id, request), ""
        except Exception as exc:  # noqa: BLE001
            return self._error(request, provider_id, f"arena_execution_error:{type(exc).__name__}"), ""

    @staticmethod
    def _error(request: ForgeExecutionRequest, provider_id: str, error: str) -> ForgeExecutionResult:
        return ForgeExecutionResult(
            request_id=request.request_id, provider_id=provider_id, model_id=provider_id,
            route_id=request.route_id, stage=request.stage, contract_valid=False, errors=[error],
        )

    def _persist_candidate(self, run_dir: Path | None, candidate_id: str, result: ForgeExecutionResult, raw: str) -> str:
        if run_dir is None:
            return ""
        (run_dir / f"{candidate_id}.result.json").write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if raw:
            (run_dir / f"{candidate_id}.raw.txt").write_text(raw, encoding="utf-8")
        return f"{candidate_id}.result.json"
