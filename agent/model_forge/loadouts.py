"""Forge loadouts (PFG-19 storage; PFG-26 UI/apply).

A Loadout is a named, simple preset that bundles a source mode, stage-mode overrides,
and provider preferences for normal use. This module owns the schema, the seven default
loadouts, and a JSON-backed store. Applying a loadout to live stage/provider policy is
wired in PFG-26 — these are definitions and persistence only and change nothing on their
own. ``risky`` flags loadouts whose application would change production routing so the UI
can require explicit confirmation.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from agent.model_forge.schema import FORGE_SCHEMA_VERSION, ForgeModel
from agent.model_forge.source_policy import SourceMode


class Loadout(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    loadout_id: str = Field(min_length=1)
    display_name: str = ""
    description: str = ""
    source_mode: SourceMode = SourceMode.LOCAL_ONLY
    # stage value -> stage mode value (applied in PFG-26).
    stage_overrides: dict[str, str] = Field(default_factory=dict)
    provider_preferences: list[str] = Field(default_factory=list)
    # True when applying this loadout would change production routing (needs confirmation).
    risky: bool = False
    builtin: bool = False


def default_loadouts() -> list[Loadout]:
    return [
        Loadout(loadout_id="local_safe", display_name="Local Safe", builtin=True,
                description="Local models only, shadow everywhere; never routes live.",
                source_mode=SourceMode.LOCAL_ONLY, provider_preferences=["local_openai_compatible"]),
        Loadout(loadout_id="local_fast", display_name="Local Fast", builtin=True,
                description="Local models, lightweight routes for quick tasks.",
                source_mode=SourceMode.LOCAL_ONLY, provider_preferences=["local_openai_compatible"]),
        Loadout(loadout_id="local_deep", display_name="Local Deep", builtin=True,
                description="Local models, deeper multi-step routes for harder tasks.",
                source_mode=SourceMode.LOCAL_ONLY, provider_preferences=["local_openai_compatible"]),
        Loadout(loadout_id="hybrid_balanced", display_name="Hybrid Balanced", builtin=True,
                description="Local preferred with optional external review.",
                source_mode=SourceMode.HYBRID, provider_preferences=["local_openai_compatible", "openrouter"]),
        Loadout(loadout_id="openrouter_review", display_name="OpenRouter Review", builtin=True,
                description="External model used for review only; gated by privacy policy.",
                source_mode=SourceMode.FRONTIER_PREFERRED, provider_preferences=["openrouter"], risky=True),
        Loadout(loadout_id="greenfield_builder", display_name="Greenfield Builder", builtin=True,
                description="Skeleton-first routes for new projects.",
                source_mode=SourceMode.LOCAL_PREFERRED, provider_preferences=["local_openai_compatible"]),
        Loadout(loadout_id="repair_specialist", display_name="Repair Specialist", builtin=True,
                description="Repair-loop and Portal replay repair routes.",
                source_mode=SourceMode.LOCAL_PREFERRED, provider_preferences=["local_openai_compatible"]),
    ]


class LoadoutStore:
    def __init__(self, store_path: str | Path) -> None:
        self._path = Path(store_path)
        self._custom: dict[str, Loadout] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for raw in data.get("loadouts", []):
                lo = Loadout.model_validate(raw)
                self._custom[lo.loadout_id] = lo

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": FORGE_SCHEMA_VERSION,
                   "loadouts": [lo.model_dump(mode="json") for lo in self._custom.values()]}
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_loadouts(self) -> list[Loadout]:
        # Builtins first, then custom (custom overrides a builtin id).
        merged: dict[str, Loadout] = {lo.loadout_id: lo for lo in default_loadouts()}
        merged.update(self._custom)
        return list(merged.values())

    def get(self, loadout_id: str) -> Loadout | None:
        for lo in self.list_loadouts():
            if lo.loadout_id == loadout_id:
                return lo
        return None

    def upsert(self, payload: dict) -> Loadout:
        lo = Loadout.model_validate(payload)
        # User-saved loadouts are never marked builtin.
        lo = lo.model_copy(update={"builtin": False})
        self._custom[lo.loadout_id] = lo
        self._save()
        return lo


__all__ = ["Loadout", "LoadoutStore", "default_loadouts"]
