"""Mechanical Forge capability evaluation runs and profile previews."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.model_forge.capability_scoring import CapabilityScorer, build_capability_profile
from agent.model_forge.eval_packs import CaseResult, load_eval_packs
from agent.model_forge.method_router import MethodRouter
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.real_method_runner import RealMethodRunner
from agent.model_forge.route_matrix import ChangeClass
from agent.model_forge.route_taxonomy import ForgeRoute
from agent.model_forge.schema import ModelOptimizationProfile


class ForgeEvaluationService:
    def __init__(self, root: str | Path, profiles: ProfileStore) -> None:
        self._root = Path(root)
        self._runs = self._root / "evaluation_runs"
        self._profiles = profiles

    def cases(self, dimension: str = "") -> dict:
        packs = [pack for pack in load_eval_packs() if not dimension or pack.dimension == dimension]
        return {
            "dimensions": [pack.dimension for pack in packs],
            "packs": [pack.model_dump(mode="json") for pack in packs],
        }

    def run(
        self,
        *,
        provider_id: str,
        model_id: str,
        results: list[CaseResult],
        dimensions: list[str] | None = None,
        rerun_of: str = "",
    ) -> dict:
        selected = set(dimensions or [])
        packs = [pack for pack in load_eval_packs() if not selected or pack.dimension in selected]
        if selected.difference(pack.dimension for pack in packs):
            raise ValueError("unknown_evaluation_dimension")
        run_id = "forge_eval_" + uuid4().hex[:12]
        scores = CapabilityScorer(self._profiles).record_eval_run(
            model_id=model_id,
            provider_id=provider_id,
            packs=packs,
            results=results,
            source=f"forge_evaluation:{run_id}",
        )
        record = {
            "run_id": run_id,
            "rerun_of": rerun_of,
            "provider_id": provider_id,
            "model_id": model_id,
            "status": "completed",
            "scores": {key: value.model_dump(mode="json") for key, value in scores.items()},
            "results": [result.model_dump(mode="json") for result in results],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_run(record)
        return record

    def rerun(self, run_id: str, results: list[CaseResult], dimensions: list[str] | None = None) -> dict:
        previous = self.get_run(run_id)
        if previous is None:
            raise FileNotFoundError("evaluation_run_not_found")
        return self.run(
            provider_id=previous["provider_id"],
            model_id=previous["model_id"],
            results=results,
            dimensions=dimensions,
            rerun_of=run_id,
        )

    def run_live(
        self,
        *,
        provider_id: str,
        model_id: str,
        base_url: str,
        dimensions: list[str],
        source_mode: str = "local_only",
        credential_env: str = "",
        timeout_seconds: float = 120.0,
    ) -> dict:
        selected = set(dimensions)
        packs = [pack for pack in load_eval_packs() if pack.dimension in selected]
        if not packs or selected.difference(pack.dimension for pack in packs):
            raise ValueError("unknown_evaluation_dimension")
        cases = [case for pack in packs for case in pack.cases]
        results = RealMethodRunner(self._root / "real_evidence").run_cases(
            provider_id=provider_id,
            model_id=model_id,
            base_url=base_url,
            cases=cases,
            source_mode=source_mode,
            credential_env=credential_env,
            timeout_seconds=timeout_seconds,
        )
        return self.run(
            provider_id=provider_id,
            model_id=model_id,
            results=results,
            dimensions=dimensions,
        )

    def model_profile(self, provider_id: str, model_id: str) -> dict:
        profile = self._profiles.load_profile(provider_id, model_id)
        capability = build_capability_profile(profile, provider_id=provider_id, model_id=model_id)
        return {
            "available": profile is not None,
            "profile": profile.model_dump(mode="json") if profile else None,
            "capability_profile": {
                "model_id": capability.model_id,
                "provider_id": capability.provider_id,
                "capability_scores": capability.capability_scores,
                "known_weaknesses": capability.known_weaknesses,
                "mode": capability.mode.value,
            },
        }

    def optimize_preview(self, provider_id: str, model_id: str) -> dict:
        profile = self._profiles.load_profile(provider_id, model_id)
        capability = build_capability_profile(profile, provider_id=provider_id, model_id=model_id)
        decision = MethodRouter().select(
            route=ForgeRoute.PATCH_DSL,
            change_class=ChangeClass.MEDIUM,
            profile=capability,
        )
        scores = capability.capability_scores
        fitness = {
            MethodVariant.STRUCTURED_PATCH_JSON: scores.get("structured_output_fidelity", 0.5),
            MethodVariant.PATCH_DSL_JSON: scores.get("patch_protocol_fidelity", 0.5),
            MethodVariant.EDIT_INTENT_LIST: scores.get("edit_intent_quality", 0.5),
            MethodVariant.ANCHORED_EDIT_BLOCK: scores.get("anchor_selection_quality", 0.5),
        }
        preview = ModelOptimizationProfile(
            profile_id=f"optimization-preview:{provider_id}:{model_id}",
            provider_id=provider_id,
            model_id=model_id,
            method_fitness=fitness,
            preferred_methods=[decision.chain.primary],
            fallback_methods=[step.method_variant for step in decision.chain.fallbacks],
            instruction_abstraction_level=decision.instruction_abstraction_level,
            task_decomposition_policy=decision.task_decomposition_policy,
            context_package_mode=decision.context_package_mode,
            verification_mode=decision.verification_mode,
            evidence_refs=list(profile.evidence_refs) if profile else [],
        )
        return {"status": "preview_not_applied", "optimization_profile": preview.model_dump(mode="json")}

    def get_run(self, run_id: str) -> dict | None:
        path = self._runs / f"{self._safe_id(run_id)}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _write_run(self, record: dict) -> None:
        self._runs.mkdir(parents=True, exist_ok=True)
        path = self._runs / f"{self._safe_id(record['run_id'])}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _safe_id(value: str) -> str:
        if not value or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in value):
            raise ValueError("invalid_evaluation_run_id")
        return value
