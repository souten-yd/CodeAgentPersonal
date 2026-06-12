"""Forge service composition (PFG-19).

Read-mostly facade that composes the Forge components (provider registry, profile store,
stage/route matrices, arena runner, benchmark presets, loadouts) against a ca_data root
and returns plain serialisable dicts for the backend API.

Safety:

- Forge is OFF by default. ``status()`` reports ``forge_enabled`` from an explicit env
  flag (``FORGE_ENABLED``); legacy execution stays primary regardless.
- Secrets are never returned. Provider descriptors carry only the credential ENV NAME
  (never its value) and a base URL; no header or key value is ever serialised.
- Disabled/unavailable provider states are surfaced truthfully.
- Arena runs default to Local Only; external providers stay blocked unless explicitly
  enabled and policy-allowed.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from agent.model_forge.arena_runner import ArenaCandidateSpec, ArenaRunner
from agent.model_forge.benchmark_presets import get_preset, preset_listing
from agent.model_forge.candidate_evaluator import (
    CandidateEvaluation,
    CandidateEvaluationInput,
    CandidateEvaluator,
    VERDICT_ELIGIBLE,
)
from agent.model_forge.loadouts import LoadoutStore
from agent.model_forge.portal_evidence import PortalRunEvidence, ingest_portal_evidence
from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.provider_registry import ProviderRegistry
from agent.model_forge.providers.legacy_atlas import LegacyAtlasProvider
from agent.model_forge.providers.local_openai_compatible import (
    LOCAL_OPENAI_PROVIDER_ID,
    LocalOpenAICompatibleProvider,
)
from agent.model_forge.providers.openrouter_catalog import OpenRouterCatalog
from agent.model_forge.providers.openrouter_client import OpenRouterProvider
from agent.model_forge.providers.openrouter_config import (
    OpenRouterConfig,
    check_openrouter_allowed,
    openrouter_credentials_available,
)
from agent.model_forge.cutover import CutoverController
from agent.model_forge.route_matrix import ChangeClass, RouteMatrix, RouteSelector
from agent.model_forge.schema import (
    AdoptionState,
    CandidateProposalDraft,
    ForgeExecutionRequest,
    ForgeExecutionResult,
)
from agent.model_forge.shadow import ShadowStore
from agent.model_forge.source_policy import SourceMode
from agent.model_forge.stage_matrix import StageMatrix
from agent.model_forge.stage_taxonomy import ForgeStage


PromptResolver = Callable[[ForgeExecutionRequest], "tuple[str, str]"]


def _prompt_resolver(_request: ForgeExecutionRequest) -> tuple[str, str]:
    return "", ""


class ForgeService:
    def __init__(
        self,
        ca_data_root: str | Path,
        *,
        env: Mapping[str, str] | None = None,
        prompt_resolver: PromptResolver | None = None,
    ) -> None:
        self._env = dict(env if env is not None else os.environ)
        self._ca_data_root = Path(ca_data_root)
        self._root = Path(ca_data_root) / "model_forge"
        self._prompt_resolver = prompt_resolver or _prompt_resolver
        self.profiles = ProfileStore(self._root / "profiles")
        self.stage_matrix = StageMatrix(self._root / "stage_policy.json")
        self.route_matrix = RouteMatrix()
        self.loadouts = LoadoutStore(self._root / "loadouts.json")
        self._settings_path = self._root / "settings.json"
        self._catalog_path = self._root / "catalog" / "openrouter_models.json"
        self._provider_probe_path = self._root / "provider_probes.json"
        self._route_policy_path = self._root / "route_policy.json"
        self._active_loadout_path = self._root / "active_loadout.json"
        self.registry = self._build_registry()
        self.arena = ArenaRunner(self.registry, store_dir=self._root / "arena_runs")
        self.shadow = ShadowStore(self._root / "shadow")
        self.cutover_controller = CutoverController(
            self.stage_matrix, self.shadow, store_dir=self._root / "cutover")

    # ----- composition -----

    def _build_registry(self) -> ProviderRegistry:
        registry = ProviderRegistry()
        # Legacy Atlas executor: local, enabled, but unwired here (health UNAVAILABLE),
        # which is truthful — the live legacy path runs in the Atlas pipeline, not here.
        registry.register(LegacyAtlasProvider(backend_fn=None, prompt_resolver=self._prompt_resolver))

        settings = self._settings()
        probes = self._provider_probe_status()
        local_settings = settings.get("local_provider", {})
        local_base = self._env.get("FORGE_LOCAL_BASE_URL", "").strip() or str(local_settings.get("base_url") or "").strip()
        local_model = self._env.get("FORGE_LOCAL_MODEL", "").strip() or str(local_settings.get("model_id") or "").strip()
        local_probe = probes.get(LOCAL_OPENAI_PROVIDER_ID, {})
        registry.register(LocalOpenAICompatibleProvider(
            base_url=local_base, model_id=local_model, prompt_resolver=self._prompt_resolver,
            enabled=True,
            runtime_health=str(local_probe.get("runtime_health") or ""),
            last_probe_at=str(local_probe.get("last_probe_at") or ""),
            last_probe_error=str(local_probe.get("last_probe_error") or ""),
        ))

        openrouter_config = self._openrouter_config(settings)
        registry.register(OpenRouterProvider(
            config=openrouter_config,
            model_id=self._env.get("FORGE_OPENROUTER_MODEL", "").strip(),
            prompt_resolver=self._prompt_resolver,
        ))
        return registry

    def _settings(self) -> dict:
        if not self._settings_path.exists():
            return {}
        try:
            data = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    def _provider_probe_status(self) -> dict:
        if not self._provider_probe_path.exists():
            return {}
        try:
            data = json.loads(self._provider_probe_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    def _openrouter_config(self, settings: Mapping[str, object] | None = None) -> OpenRouterConfig:
        raw = dict((settings or self._settings()).get("openrouter", {}) or {})
        env_enabled = self._env.get("FORGE_OPENROUTER_ENABLED", "").strip()
        enabled = bool(raw.get("enabled", False))
        if env_enabled:
            enabled = env_enabled in ("1", "true", "True")
        return OpenRouterConfig(
            enabled=enabled,
            api_key_env=str(raw.get("api_key_env") or "OPENROUTER_API_KEY"),
            http_referer_env=str(raw.get("http_referer_env") or "OPENROUTER_HTTP_REFERER"),
            app_title=str(raw.get("app_title") or "KasaneCore Atlas Forge"),
            base_url=str(raw.get("base_url") or "https://openrouter.ai/api/v1"),
            catalog_cache_ttl_seconds=int(raw.get("catalog_cache_ttl_seconds") or 3600),
        )

    def forge_enabled(self) -> bool:
        return self._env.get("FORGE_ENABLED", "").strip() in ("1", "true", "True")

    def source_mode(self) -> SourceMode:
        raw = self._env.get("FORGE_SOURCE_MODE", "").strip()
        try:
            return SourceMode(raw) if raw else SourceMode.LOCAL_ONLY
        except ValueError:
            return SourceMode.LOCAL_ONLY

    def record_execution_bridge_event(self, payload: dict) -> str:
        request_id = str(payload.get("request_id") or "unknown").replace("/", "_").replace("\\", "_")
        stage = str(payload.get("stage") or "unknown").replace("/", "_").replace("\\", "_")
        path = self._root / "execution_bridge" / f"{stage}.{request_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    # ----- read endpoints -----

    def status(self) -> dict:
        health = {h.provider_id: h.state.value for h in self.registry.health_all()}
        active = self.active_loadout()
        return {
            "forge_enabled": self.forge_enabled(),
            "legacy_primary": True,
            "source_mode": self.source_mode().value,
            "provider_health": health,
            "provider_count": len(health),
            "ready_providers": self.registry.ready_providers(),
            "profile_count": len(self.profiles.list_profiles()),
            "active_loadout": active.get("loadout_id", "") if active else "",
        }

    def providers(self) -> list[dict]:
        # Descriptors carry only the credential ENV NAME, never a secret value.
        health = {h.provider_id: h for h in self.registry.health_all()}
        out: list[dict] = []
        for desc in self.registry.descriptors():
            d = desc.model_dump(mode="json")
            h = health.get(desc.provider_id)
            d["health"] = h.state.value if h else "error"
            d["health_detail"] = h.detail if h else "no_health"
            d["configured_state"] = h.configured_state.value if h else "missing_config"
            d["runtime_health"] = h.runtime_health.value if h else "error"
            d["last_probe_at"] = h.last_probe_at if h else ""
            d["last_probe_error"] = h.last_probe_error if h else "no_health"
            # Defensive: ensure no secret value is ever attached.
            d.pop("api_key", None)
            d.pop("authorization", None)
            out.append(d)
        return out

    def models(self) -> list[dict]:
        seen: set[tuple[str, str]] = set()
        out: list[dict] = []
        # Models with a recorded profile.
        for profile in self.profiles.list_profiles():
            key = (profile.provider_id, profile.model_id)
            if key not in seen:
                seen.add(key)
                out.append({"provider_id": profile.provider_id, "model_id": profile.model_id,
                            "source": "profile"})
        # Configured local model, if any.
        local_model = self._env.get("FORGE_LOCAL_MODEL", "").strip()
        if not local_model:
            local_model = str(self._settings().get("local_provider", {}).get("model_id") or "").strip()
        if local_model and (LOCAL_OPENAI_PROVIDER_ID, local_model) not in seen:
            out.append({"provider_id": LOCAL_OPENAI_PROVIDER_ID, "model_id": local_model,
                        "source": "configured"})
        for model in self._cached_openrouter_models():
            key = (model["provider_id"], model["model_id"])
            if key not in seen:
                seen.add(key)
                out.append(model)
        return out

    def profiles_list(self) -> list[dict]:
        return [p.model_dump(mode="json") for p in self.profiles.list_profiles()]

    def leaderboard(self) -> list[dict]:
        """Champion (highest-scoring) model per dimension across all profiles."""
        champions: dict[str, dict] = {}
        for profile in self.profiles.list_profiles():
            for dim, score in profile.dimension_scores.items():
                cur = champions.get(dim)
                if cur is None or score > cur["score"]:
                    champions[dim] = {"dimension": dim, "provider_id": profile.provider_id,
                                      "model_id": profile.model_id, "score": score}
        return [champions[d] for d in sorted(champions)]

    def presets(self) -> list[dict]:
        return preset_listing()

    def settings(self) -> dict:
        settings = self._settings()
        openrouter_config = self._openrouter_config(settings)
        local_settings = settings.get("local_provider", {}) if isinstance(settings.get("local_provider"), dict) else {}
        return {
            "local_provider": {
                "base_url": self._env.get("FORGE_LOCAL_BASE_URL", "").strip() or str(local_settings.get("base_url") or ""),
                "model_id": self._env.get("FORGE_LOCAL_MODEL", "").strip() or str(local_settings.get("model_id") or ""),
                "model_storage_dir": str(local_settings.get("model_storage_dir") or ""),
                "base_url_source": "env" if self._env.get("FORGE_LOCAL_BASE_URL", "").strip() else "settings",
                "model_id_source": "env" if self._env.get("FORGE_LOCAL_MODEL", "").strip() else "settings",
            },
            "openrouter": {
                "enabled": openrouter_config.enabled,
                "api_key_env": openrouter_config.api_key_env,
                "credential_configured": openrouter_credentials_available(openrouter_config),
                "http_referer_env": openrouter_config.http_referer_env,
                "app_title": openrouter_config.app_title,
                "base_url": openrouter_config.base_url,
                "catalog_cache_path": str(self._catalog_path),
            },
        }

    def save_settings(self, payload: dict) -> dict:
        forbidden = {"api_key", "access_token", "token", "openrouter_api_key", "authorization"}
        if self._contains_forbidden_secret_key(payload, forbidden):
            raise ValueError("secret_values_must_not_be_persisted")
        openrouter = dict(payload.get("openrouter") or {})
        local_provider = dict(payload.get("local_provider") or {})
        safe = {
            "openrouter": {
                "enabled": bool(openrouter.get("enabled", False)),
                "api_key_env": str(openrouter.get("api_key_env") or "OPENROUTER_API_KEY"),
                "http_referer_env": str(openrouter.get("http_referer_env") or "OPENROUTER_HTTP_REFERER"),
                "app_title": str(openrouter.get("app_title") or "KasaneCore Atlas Forge"),
                "base_url": str(openrouter.get("base_url") or "https://openrouter.ai/api/v1"),
                "catalog_cache_ttl_seconds": int(openrouter.get("catalog_cache_ttl_seconds") or 3600),
            },
            "local_provider": {
                "base_url": str(local_provider.get("base_url") or ""),
                "model_id": str(local_provider.get("model_id") or ""),
                "model_storage_dir": str(local_provider.get("model_storage_dir") or ""),
            },
        }
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.settings()

    def _contains_forbidden_secret_key(self, value, forbidden: set[str]) -> bool:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in forbidden:
                    return True
                if self._contains_forbidden_secret_key(child, forbidden):
                    return True
        if isinstance(value, list):
            return any(self._contains_forbidden_secret_key(child, forbidden) for child in value)
        return False

    def openrouter_catalog(self, *, force_refresh: bool = False) -> dict:
        config = self._openrouter_config()
        catalog = OpenRouterCatalog(config, cache_path=self._catalog_path)
        if self._catalog_path.exists() and not force_refresh:
            result = catalog.get_models(force_refresh=False)
            return self._catalog_payload("from_cache", result, config, reason=result.error)
        gate = check_openrouter_allowed(config, self.source_mode())
        if not gate.allowed:
            status = "disabled" if gate.reason in ("local_only_blocks_external", "openrouter_disabled") else "unavailable"
            return self._catalog_payload(status, None, config, reason=gate.reason)
        result = catalog.get_models(force_refresh=force_refresh)
        status = "live" if result.status == "fetched" else result.status
        return self._catalog_payload(status, result, config, reason=result.error)

    def _catalog_payload(self, status: str, result, config: OpenRouterConfig, *, reason: str = "") -> dict:
        models = [m.model_dump(mode="json") for m in (result.models if result else [])]
        return {
            "provider_id": "openrouter",
            "status": status,
            "enabled": config.enabled,
            "credential_configured": openrouter_credentials_available(config),
            "from_cache": status == "from_cache",
            "stale": bool(getattr(result, "stale", False)) if result else False,
            "reason": reason,
            "fetched_at": getattr(result, "fetched_at", "") if result else "",
            "models": models,
        }

    def _cached_openrouter_models(self) -> list[dict]:
        if not self._catalog_path.exists():
            return []
        result = OpenRouterCatalog(OpenRouterConfig(enabled=False), cache_path=self._catalog_path).get_models()
        return [
            {
                "provider_id": m.provider_id,
                "model_id": m.model_id,
                "display_name": m.display_name,
                "source": "openrouter_catalog_cache",
            }
            for m in result.models
        ]

    def probe_provider(self, provider_id: str) -> dict:
        provider = self.registry.get(provider_id)
        if provider is None:
            raise ValueError(f"unknown_provider:{provider_id}")
        health = provider.probe_runtime()
        probes = self._provider_probe_status()
        probes[provider_id] = {
            "runtime_health": health.runtime_health.value,
            "last_probe_at": health.last_probe_at or health.checked_at,
            "last_probe_error": health.last_probe_error,
            "state": health.state.value,
            "detail": health.detail,
        }
        self._provider_probe_path.parent.mkdir(parents=True, exist_ok=True)
        self._provider_probe_path.write_text(json.dumps(probes, ensure_ascii=False, indent=2), encoding="utf-8")
        return health.model_dump(mode="json")

    # ----- arena -----

    def run_arena(
        self, *, stage: str, specs: list[dict], source_mode: str | None = None,
        privacy_mode: str = "no_external_code", preset_id: str = "",
        preset_ids: list[str] | None = None, benchmark_depth: str = "standard",
        task_id: str = "",
    ) -> dict:
        selected_preset_ids = [p for p in (preset_ids or []) if p]
        if preset_id and preset_id not in selected_preset_ids:
            selected_preset_ids.insert(0, preset_id)
        if selected_preset_ids:
            for pid in selected_preset_ids:
                if get_preset(pid) is None:
                    raise ValueError(f"unknown_preset_id:{pid}")
            preset_id = selected_preset_ids[0]
        depth = (benchmark_depth or "standard").strip().lower()
        if depth != "standard":
            raise ValueError(f"benchmark_depth_unavailable_not_supported:{depth}")
        candidate_specs = [ArenaCandidateSpec(**s) for s in specs]
        record = self.arena.run(
            stage=ForgeStage(stage), specs=candidate_specs,
            source_mode=source_mode or self.source_mode().value,
            privacy_mode=privacy_mode, preset_id=preset_id,
            preset_ids=selected_preset_ids, benchmark_depth=depth,
            task_id=task_id,
        )
        return record.model_dump(mode="json")

    def get_arena_run(self, arena_run_id: str) -> dict | None:
        run_dir = self._root / "arena_runs" / arena_run_id
        path = run_dir / "arena.json"
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        # Enrich each candidate with its persisted execution-result metadata (latency,
        # contract validity, errors) so the Arena UI shows real per-candidate data. No
        # secrets are involved; results contain only metadata + output references.
        for cand in record.get("candidates", []):
            ref = cand.get("execution_result_ref", "")
            result_path = run_dir / ref if ref else None
            if result_path and result_path.exists():
                result = json.loads(result_path.read_text(encoding="utf-8"))
                cand["result"] = {
                    "contract_valid": result.get("contract_valid", False),
                    "latency_ms": result.get("latency_ms", 0),
                    "errors": result.get("errors", []),
                    "usage": result.get("usage", {}),
                }
            evaluation = self._evaluate_arena_candidate(record, cand, run_dir)
            cand["evaluation"] = evaluation.model_dump(mode="json")
            cand["evaluator_score"] = evaluation.score.model_dump(mode="json")
            cand["blocked_reasons"] = list(evaluation.score.blocked_reasons)
            cand["eligible_for_proposal"] = evaluation.score.verdict == VERDICT_ELIGIBLE
            cand["risk_level"] = self._candidate_risk_level(cand)
            cand["proposal_draft"] = self._candidate_proposal_draft_summary(
                str(cand.get("arena_run_id") or arena_run_id), str(cand.get("candidate_id") or "")
            )
        return record

    def create_candidate_proposal_draft(self, candidate_id: str) -> dict:
        found = self._find_arena_candidate(candidate_id)
        if found is None:
            raise ValueError(f"unknown_candidate:{candidate_id}")
        arena_run_id, run_dir, record, cand = found
        evaluation = self._evaluate_arena_candidate(record, cand, run_dir)
        self._persist_candidate_evaluation(run_dir, cand, evaluation)
        if evaluation.score.verdict != VERDICT_ELIGIBLE:
            cand["adoption_state"] = AdoptionState.REJECTED.value
            self._save_arena_record(run_dir, record)
            return {
                "status": "blocked",
                "candidate_id": candidate_id,
                "arena_run_id": arena_run_id,
                "blocked_reasons": list(evaluation.score.blocked_reasons),
                "evaluator_score": evaluation.score.model_dump(mode="json"),
                "proposal_draft": None,
            }

        existing = self._load_candidate_proposal_draft(arena_run_id, candidate_id)
        if existing is not None:
            cand["adoption_state"] = AdoptionState.PROPOSAL_CREATED.value
            self._save_arena_record(run_dir, record)
            return {
                "status": "created",
                "candidate_id": candidate_id,
                "arena_run_id": arena_run_id,
                "proposal_draft": existing,
                "idempotent": True,
            }

        draft = self._build_candidate_proposal_draft(record, cand, evaluation)
        draft_path = self._proposal_draft_path(arena_run_id, candidate_id)
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        payload = draft.model_copy(update={"artifact_ref": str(draft_path)}).model_dump(mode="json")
        draft_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_candidate_proposal_draft_markdown(record, cand, payload)
        cand["adoption_state"] = AdoptionState.PROPOSAL_CREATED.value
        cand["score_ref"] = f"{candidate_id}.score.json"
        self._save_arena_record(run_dir, record)
        return {
            "status": "created",
            "candidate_id": candidate_id,
            "arena_run_id": arena_run_id,
            "proposal_draft": payload,
            "idempotent": False,
        }

    def _find_arena_candidate(self, candidate_id: str) -> tuple[str, Path, dict, dict] | None:
        arena_root = self._root / "arena_runs"
        if not arena_root.exists():
            return None
        for path in sorted(arena_root.glob("*/arena.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for cand in record.get("candidates", []):
                if str(cand.get("candidate_id") or "") == candidate_id:
                    return str(record.get("arena_run_id") or path.parent.name), path.parent, record, cand
        return None

    @staticmethod
    def _save_arena_record(run_dir: Path, record: dict) -> None:
        (run_dir / "arena.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def _evaluate_arena_candidate(self, record: dict, cand: dict, run_dir: Path) -> CandidateEvaluation:
        result = self._candidate_execution_result(cand, run_dir)
        raw = self._candidate_raw_output(cand, run_dir)
        privacy_mode = str(record.get("privacy_mode") or "")
        privacy_penalty = 0.0 if privacy_mode == "no_external_code" else None
        return CandidateEvaluator().evaluate(CandidateEvaluationInput(
            candidate_id=str(cand.get("candidate_id") or ""),
            execution_result=result,
            output_contract="text",
            raw_output=raw,
            privacy_penalty=privacy_penalty,
        ))

    @staticmethod
    def _candidate_execution_result(cand: dict, run_dir: Path) -> ForgeExecutionResult:
        ref = str(cand.get("execution_result_ref") or "")
        path = run_dir / ref if ref else None
        if path and path.exists():
            return ForgeExecutionResult.model_validate(json.loads(path.read_text(encoding="utf-8")))
        return ForgeExecutionResult(
            request_id=str(cand.get("candidate_id") or "unknown"),
            provider_id=str(cand.get("provider_id") or "unknown"),
            model_id=str(cand.get("model_id") or "unknown"),
            route_id=cand.get("route_id") or "direct_patch",
            stage="patch_generation",
            contract_valid=False,
            errors=["execution_result_missing"],
        )

    @staticmethod
    def _candidate_raw_output(cand: dict, run_dir: Path) -> str:
        raw_path = run_dir / f"{cand.get('candidate_id')}.raw.txt"
        if raw_path.exists():
            return raw_path.read_text(encoding="utf-8", errors="replace")
        return ""

    @staticmethod
    def _persist_candidate_evaluation(run_dir: Path, cand: dict, evaluation: CandidateEvaluation) -> None:
        candidate_id = str(cand.get("candidate_id") or "")
        if not candidate_id:
            return
        ref = f"{candidate_id}.score.json"
        (run_dir / ref).write_text(
            json.dumps(evaluation.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        cand["score_ref"] = ref

    def _build_candidate_proposal_draft(
        self, record: dict, cand: dict, evaluation: CandidateEvaluation
    ) -> CandidateProposalDraft:
        preset_id = str(cand.get("preset_id") or record.get("preset_id") or "")
        risk_level = self._candidate_risk_level(cand)
        required_evaluators = list((get_preset(preset_id).required_evaluators if get_preset(preset_id) else []) or [])
        return CandidateProposalDraft(
            draft_id=f"proposal_draft_{cand.get('candidate_id')}",
            candidate_id=str(cand.get("candidate_id") or ""),
            arena_run_id=str(record.get("arena_run_id") or cand.get("arena_run_id") or ""),
            provider_id=str(cand.get("provider_id") or ""),
            model_id=str(cand.get("model_id") or ""),
            route_id=cand.get("route_id") or "direct_patch",
            preset_id=preset_id,
            task_id=str(cand.get("task_id") or record.get("task_id") or ""),
            stage=record.get("stage") or "patch_generation",
            source_mode=record.get("source_mode") or self.source_mode().value,
            privacy_mode=record.get("privacy_mode") or "no_external_code",
            risk_level=risk_level,
            evaluator_score=evaluation.score,
            blocked_reasons=list(evaluation.score.blocked_reasons),
            required_safe_apply_steps=[
                "Review and approve this Proposal draft before adoption.",
                "Create an Atlas PlanItem from the approved Proposal.",
                "Run changes only through Atlas Safe Apply.",
            ],
            required_verification_steps=required_evaluators + [
                "Run focused and affected Atlas Verification after Safe Apply.",
            ],
            metadata={
                "source": "forge_candidate_proposal_handoff",
                "approval_required": True,
                "safe_apply_run": False,
                "verification_run": False,
                "source_mutation": False,
                "execution_result_ref": str(cand.get("execution_result_ref") or ""),
                "raw_output_ref": f"{cand.get('candidate_id')}.raw.txt",
                "candidate_adoption_state_before": str(cand.get("adoption_state") or ""),
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _candidate_risk_level(self, cand: dict) -> str:
        preset = get_preset(str(cand.get("preset_id") or ""))
        return preset.risk_level if preset else "medium"

    def _proposal_draft_path(self, arena_run_id: str, candidate_id: str) -> Path:
        safe_arena = arena_run_id.replace("/", "_").replace("\\", "_")
        safe_candidate = candidate_id.replace("/", "_").replace("\\", "_")
        return self._root / "proposal_drafts" / safe_arena / f"{safe_candidate}.json"

    def _proposal_draft_markdown_path(self, arena_run_id: str, candidate_id: str) -> Path:
        safe_arena = arena_run_id.replace("/", "_").replace("\\", "_")
        safe_candidate = candidate_id.replace("/", "_").replace("\\", "_")
        return self._root / "proposal_drafts" / safe_arena / f"{safe_candidate}.md"

    def _load_candidate_proposal_draft(self, arena_run_id: str, candidate_id: str) -> dict | None:
        path = self._proposal_draft_path(arena_run_id, candidate_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _candidate_proposal_draft_summary(self, arena_run_id: str, candidate_id: str) -> dict:
        draft = self._load_candidate_proposal_draft(arena_run_id, candidate_id)
        if not draft:
            return {"status": "not_created"}
        return {
            "status": str(draft.get("status") or "proposal_draft"),
            "draft_id": str(draft.get("draft_id") or ""),
            "artifact_ref": str(draft.get("artifact_ref") or ""),
        }

    def _write_candidate_proposal_draft_markdown(self, record: dict, cand: dict, draft: dict) -> None:
        path = self._proposal_draft_markdown_path(
            str(record.get("arena_run_id") or cand.get("arena_run_id") or ""),
            str(cand.get("candidate_id") or ""),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        md = (
            "# Forge Candidate Proposal Draft\n\n"
            f"- Arena run ID: {draft.get('arena_run_id')}\n"
            f"- Candidate ID: {draft.get('candidate_id')}\n"
            f"- Provider/model: {draft.get('provider_id')} / {draft.get('model_id')}\n"
            f"- Route/preset: {draft.get('route_id')} / {draft.get('preset_id')}\n"
            f"- Risk level: {draft.get('risk_level')}\n"
            f"- Source/privacy: {draft.get('source_mode')} / {draft.get('privacy_mode')}\n"
            f"- Evaluator verdict: {(draft.get('evaluator_score') or {}).get('verdict')}\n"
            f"- Blocked reasons: {json.dumps(draft.get('blocked_reasons') or [], ensure_ascii=False)}\n"
            f"- Required Safe Apply steps: {json.dumps(draft.get('required_safe_apply_steps') or [], ensure_ascii=False)}\n"
            f"- Required Verification steps: {json.dumps(draft.get('required_verification_steps') or [], ensure_ascii=False)}\n\n"
            "- No source file was modified.\n"
            "- No Safe Apply was run.\n"
            "- No Verification was run.\n"
            "- Atlas Proposal approval is still required before adoption.\n"
        )
        path.write_text(md, encoding="utf-8")

    # ----- stage policy -----

    def get_stage_policy(self) -> list[dict]:
        return [e.model_dump(mode="json") for e in self.stage_matrix.matrix()]

    def set_stage_policy(
        self, *, stage: str, mode: str, allow_production_routing: bool = False, **kwargs
    ) -> dict:
        entry = self.stage_matrix.set_policy(
            stage, mode, allow_production_routing=allow_production_routing,
            fixed_provider_id=kwargs.get("fixed_provider_id", ""),
            fixed_model_id=kwargs.get("fixed_model_id", ""),
            fallback_provider_id=kwargs.get("fallback_provider_id", ""),
            fallback_model_id=kwargs.get("fallback_model_id", ""),
            reason=kwargs.get("reason", ""),
        )
        return entry.model_dump(mode="json")

    # ----- route policy -----

    def get_route_policy(self) -> list[dict]:
        overrides = self._load_route_overrides()
        out: list[dict] = []
        for cc in ChangeClass:
            entry = self.route_matrix.entry(cc).model_dump(mode="json")
            entry["preferred_route_override"] = overrides.get(cc.value, "")
            out.append(entry)
        return out

    def set_route_policy(self, *, change_class: str, preferred_route: str) -> dict:
        cc = ChangeClass(change_class)
        # Validate against the matrix: an unsafe/forbidden route is refused.
        selection = RouteSelector(self.route_matrix).select(cc, requested_route=preferred_route)
        if selection.overridden:
            raise ValueError(
                f"route {preferred_route} not allowed for {change_class}: {selection.reasons}"
            )
        overrides = self._load_route_overrides()
        overrides[cc.value] = preferred_route
        self._route_policy_path.parent.mkdir(parents=True, exist_ok=True)
        self._route_policy_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
        return {"change_class": cc.value, "preferred_route": preferred_route,
                "selected_route": selection.selected_route.value}

    def _load_route_overrides(self) -> dict[str, str]:
        if self._route_policy_path.exists():
            return json.loads(self._route_policy_path.read_text(encoding="utf-8"))
        return {}

    # ----- loadouts -----

    def get_loadouts(self) -> list[dict]:
        active = self.active_loadout()
        active_id = active.get("loadout_id", "") if active else ""
        out = []
        for lo in self.loadouts.list_loadouts():
            d = lo.model_dump(mode="json")
            d["active"] = (d["loadout_id"] == active_id)
            out.append(d)
        return out

    def save_loadout(self, payload: dict) -> dict:
        return self.loadouts.upsert(payload).model_dump(mode="json")

    def list_cutovers(self) -> list[dict]:
        return [c.model_dump(mode="json") for c in self.cutover_controller.list_cutovers()]

    def cutover_stage(self, stage: str, *, acknowledge: bool = False) -> dict:
        return self.cutover_controller.cutover(stage, acknowledge=acknowledge).model_dump(mode="json")

    def rollback_stage(self, stage: str) -> dict:
        return self.cutover_controller.rollback(stage).model_dump(mode="json")

    def attach_capsule_forge_meta(self, payload: dict) -> dict:
        # Imported lazily to keep the model_forge package free of app/ imports.
        from app.atlas.capsule.forge_meta import write_capsule_forge_meta
        return write_capsule_forge_meta(self._ca_data_root, payload).model_dump(mode="json")

    def get_capsule_forge_meta(self, package_id: str, version: str, content_hash: str) -> dict | None:
        from app.atlas.capsule.forge_meta import read_capsule_forge_meta
        meta = read_capsule_forge_meta(self._ca_data_root, package_id, version, content_hash)
        return meta.model_dump(mode="json") if meta else None

    def record_capsule_replay(self, payload: dict) -> dict:
        from app.atlas.capsule.forge_meta import record_capsule_replay_via_play_runtime
        evidence = record_capsule_replay_via_play_runtime(
            self._ca_data_root, self.profiles,
            package_id=payload["package_id"], version=payload["version"],
            content_hash=payload["content_hash"],
            user_decision=payload.get("user_decision", ""),
        )
        return evidence.model_dump(mode="json")

    def record_portal_evidence(self, payload: dict) -> dict:
        """Ingest a Portal run outcome into the model profile. Runtime pass/fail moves the
        score; a user decision alone is weak feedback (never moves the score)."""
        result = ingest_portal_evidence(self.profiles, PortalRunEvidence(**payload))
        return result.model_dump(mode="json")

    def active_loadout(self) -> dict | None:
        if self._active_loadout_path.exists():
            return json.loads(self._active_loadout_path.read_text(encoding="utf-8"))
        return None

    def apply_loadout(self, loadout_id: str, *, acknowledge_risky: bool = False) -> dict:
        """Switch the active loadout: apply its stage overrides to the stage matrix and
        record it as active. A risky loadout (one that would change production routing or
        use an external provider) requires acknowledge_risky=True."""
        loadout = self.loadouts.get(loadout_id)
        if loadout is None:
            raise ValueError(f"unknown_loadout:{loadout_id}")
        if loadout.risky and not acknowledge_risky:
            raise PermissionError(
                f"loadout {loadout_id} is risky (external/live routing); "
                "pass acknowledge_risky=True to confirm"
            )
        applied: list[dict] = []
        for stage, mode in (loadout.stage_overrides or {}).items():
            entry = self.stage_matrix.set_policy(
                stage, mode, allow_production_routing=acknowledge_risky,
                reason=f"loadout:{loadout_id}",
            )
            applied.append({"stage": entry.stage.value, "mode": entry.mode.value})
        marker = {
            "loadout_id": loadout.loadout_id,
            "source_mode": loadout.source_mode.value,
            "provider_preferences": loadout.provider_preferences,
            "applied_stages": applied,
        }
        self._active_loadout_path.parent.mkdir(parents=True, exist_ok=True)
        self._active_loadout_path.write_text(json.dumps(marker, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        return marker


__all__ = ["ForgeService"]
