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
from pathlib import Path
from typing import Mapping

from agent.model_forge.arena_runner import ArenaCandidateSpec, ArenaRunner
from agent.model_forge.benchmark_presets import preset_listing
from agent.model_forge.loadouts import LoadoutStore
from agent.model_forge.portal_evidence import PortalRunEvidence, ingest_portal_evidence
from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.provider_registry import ProviderRegistry
from agent.model_forge.providers.legacy_atlas import LegacyAtlasProvider
from agent.model_forge.providers.local_openai_compatible import (
    LOCAL_OPENAI_PROVIDER_ID,
    LocalOpenAICompatibleProvider,
)
from agent.model_forge.providers.openrouter_client import OpenRouterProvider
from agent.model_forge.providers.openrouter_config import OpenRouterConfig
from agent.model_forge.route_matrix import ChangeClass, RouteMatrix, RouteSelector
from agent.model_forge.source_policy import SourceMode
from agent.model_forge.stage_matrix import StageMatrix
from agent.model_forge.stage_taxonomy import ForgeStage


def _prompt_resolver(system: str, user: str) -> tuple[str, str]:
    return system, user


class ForgeService:
    def __init__(self, ca_data_root: str | Path, *, env: Mapping[str, str] | None = None) -> None:
        self._env = dict(env if env is not None else os.environ)
        self._ca_data_root = Path(ca_data_root)
        self._root = Path(ca_data_root) / "model_forge"
        self.profiles = ProfileStore(self._root / "profiles")
        self.stage_matrix = StageMatrix(self._root / "stage_policy.json")
        self.route_matrix = RouteMatrix()
        self.loadouts = LoadoutStore(self._root / "loadouts.json")
        self._route_policy_path = self._root / "route_policy.json"
        self._active_loadout_path = self._root / "active_loadout.json"
        self.registry = self._build_registry()
        self.arena = ArenaRunner(self.registry, store_dir=self._root / "arena_runs")

    # ----- composition -----

    def _build_registry(self) -> ProviderRegistry:
        registry = ProviderRegistry()
        # Legacy Atlas executor: local, enabled, but unwired here (health UNAVAILABLE),
        # which is truthful — the live legacy path runs in the Atlas pipeline, not here.
        registry.register(LegacyAtlasProvider(backend_fn=None, prompt_resolver=_prompt_resolver))

        local_base = self._env.get("FORGE_LOCAL_BASE_URL", "").strip()
        local_model = self._env.get("FORGE_LOCAL_MODEL", "").strip()
        registry.register(LocalOpenAICompatibleProvider(
            base_url=local_base, model_id=local_model, prompt_resolver=_prompt_resolver,
            enabled=bool(local_base),
        ))

        registry.register(OpenRouterProvider(
            config=OpenRouterConfig(enabled=self._forge_external_enabled()),
            model_id=self._env.get("FORGE_OPENROUTER_MODEL", "").strip(),
            prompt_resolver=_prompt_resolver,
        ))
        return registry

    def _forge_external_enabled(self) -> bool:
        return self._env.get("FORGE_OPENROUTER_ENABLED", "").strip() in ("1", "true", "True")

    def forge_enabled(self) -> bool:
        return self._env.get("FORGE_ENABLED", "").strip() in ("1", "true", "True")

    def source_mode(self) -> SourceMode:
        raw = self._env.get("FORGE_SOURCE_MODE", "").strip()
        try:
            return SourceMode(raw) if raw else SourceMode.LOCAL_ONLY
        except ValueError:
            return SourceMode.LOCAL_ONLY

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
        if local_model and (LOCAL_OPENAI_PROVIDER_ID, local_model) not in seen:
            out.append({"provider_id": LOCAL_OPENAI_PROVIDER_ID, "model_id": local_model,
                        "source": "configured"})
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

    # ----- arena -----

    def run_arena(
        self, *, stage: str, specs: list[dict], source_mode: str | None = None,
        privacy_mode: str = "no_external_code", preset_id: str = "", task_id: str = "",
    ) -> dict:
        candidate_specs = [ArenaCandidateSpec(**s) for s in specs]
        record = self.arena.run(
            stage=ForgeStage(stage), specs=candidate_specs,
            source_mode=source_mode or self.source_mode().value,
            privacy_mode=privacy_mode, preset_id=preset_id, task_id=task_id,
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
        return record

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

    def attach_capsule_forge_meta(self, payload: dict) -> dict:
        # Imported lazily to keep the model_forge package free of app/ imports.
        from app.atlas.capsule.forge_meta import write_capsule_forge_meta
        return write_capsule_forge_meta(self._ca_data_root, payload).model_dump(mode="json")

    def get_capsule_forge_meta(self, package_id: str, version: str, content_hash: str) -> dict | None:
        from app.atlas.capsule.forge_meta import read_capsule_forge_meta
        meta = read_capsule_forge_meta(self._ca_data_root, package_id, version, content_hash)
        return meta.model_dump(mode="json") if meta else None

    def record_capsule_replay(self, payload: dict) -> dict:
        from app.atlas.capsule.forge_meta import record_capsule_replay
        evidence = record_capsule_replay(
            self._ca_data_root, self.profiles,
            package_id=payload["package_id"], version=payload["version"],
            content_hash=payload["content_hash"],
            runtime_passed=payload.get("runtime_passed"),
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
