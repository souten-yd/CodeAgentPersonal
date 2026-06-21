"""Model Profile Store and profile updater (PFG-16).

Persists versioned per-model quality profiles under ``ca_data/model_forge/profiles``
and an append-only observation log so that:

- profile updates are append-only AND versioned (every update writes a new
  ``profile.vN.json`` and never rewrites an earlier version);
- raw evidence is preserved (observations carry evidence_refs and the observation log
  is append-only — it is never rewritten);
- dimension scores can be recomputed at any time purely from the observation log.

Weak feedback (user save/discard/Capsule decisions) is recorded with
``weak_feedback=True`` and is EXCLUDED from dimension scoring by default, so a user
decision alone never moves a model's score. It is still preserved as evidence.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from uuid import uuid4

from pydantic import Field

from agent.model_forge.candidate_evaluator import VERDICT_REJECTED
from agent.model_forge.schema import (
    FORGE_SCHEMA_VERSION,
    CandidateScore,
    ForgeModel,
    ModelProfile,
)

_KEY_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def profile_key(provider_id: str, model_id: str) -> str:
    p = _KEY_SAFE.sub("_", provider_id.strip()) or "unknown_provider"
    m = _KEY_SAFE.sub("_", model_id.strip()) or "unknown_model"
    return f"{p}__{m}"


class ProfileObservation(ForgeModel):
    schema_version: str = FORGE_SCHEMA_VERSION
    observation_id: str
    model_id: str
    provider_id: str
    # Per-dimension scores in 0.0..1.0 contributed by this observation.
    dimensions: dict[str, float] = Field(default_factory=dict)
    sample_weight: float = 1.0
    # User save/discard/Capsule decisions: recorded but excluded from scoring by default.
    weak_feedback: bool = False
    # candidate_score | portal_run | capsule_replay | user_decision | benchmark_preset ...
    source: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    recorded_at: str = ""
    twin_assist: dict = Field(default_factory=dict)
    assist_matrix: dict = Field(default_factory=dict)
    injection_sweep: dict = Field(default_factory=dict)


class ProfileStore:
    """Append-only, versioned model profile persistence."""

    def __init__(
        self,
        store_dir: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        id_factory: Callable[[], str] | None = None,
        weak_weight: float = 0.0,
    ) -> None:
        self._dir = Path(store_dir)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._id_factory = id_factory or (lambda: uuid4().hex[:12])
        # Weight applied to weak-feedback observations when (optionally) included.
        # Default 0.0: weak feedback never moves the score on its own.
        self._weak_weight = weak_weight

    # ----- paths -----

    def _key_dir(self, provider_id: str, model_id: str) -> Path:
        d = self._dir / profile_key(provider_id, model_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _obs_path(self, provider_id: str, model_id: str) -> Path:
        return self._key_dir(provider_id, model_id) / "observations.jsonl"

    # ----- recording -----

    def record_observation(
        self,
        *,
        model_id: str,
        provider_id: str,
        dimensions: dict[str, float],
        sample_weight: float = 1.0,
        weak_feedback: bool = False,
        source: str = "",
        evidence_refs: Iterable[str] | None = None,
        twin_assist: dict | None = None,
        assist_matrix: dict | None = None,
        injection_sweep: dict | None = None,
    ) -> ModelProfile:
        obs = ProfileObservation(
            observation_id=self._id_factory(),
            model_id=model_id,
            provider_id=provider_id,
            dimensions={k: float(v) for k, v in dimensions.items()},
            sample_weight=float(sample_weight),
            weak_feedback=weak_feedback,
            source=source,
            evidence_refs=list(evidence_refs or []),
            recorded_at=self._clock().isoformat(),
            twin_assist=dict(twin_assist or {}),
            assist_matrix=dict(assist_matrix or {}),
            injection_sweep=dict(injection_sweep or {}),
        )
        # Append-only: never rewrite earlier lines.
        with self._obs_path(provider_id, model_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obs.model_dump(mode="json"), ensure_ascii=False) + "\n")
        return self._write_new_version(provider_id, model_id)

    def record_twin_assist_report(self, report) -> ModelProfile:
        scores = dict(report.aggregate_scores)
        lifts = {item.case_id: item.lift for item in report.comparisons if item.lift is not None}
        mode = report.recommended_assist_modes[0].value if report.recommended_assist_modes else ""
        return self.record_observation(
            model_id=report.model_id,
            provider_id=report.provider_id,
            dimensions={f"twin_assist:{key}": value for key, value in scores.items() if key != "scored_case_count"},
            source="twin_assist_evaluation",
            evidence_refs=report.evidence_refs,
            twin_assist={"scores": scores, "lift": lifts, "mode": mode, "injection_level": report.recommended_twin_injection_level},
        )

    def record_injection_sweep_report(self, record: dict) -> ModelProfile:
        """Persist an injection-sweep result so the MEASURED optimal injection level flows into
        the model profile (and thence ``ExecutionPolicySelector``). The sweep carries no
        per-dimension capability scores of its own (those live in the standard benchmark), so it
        records an empty ``dimensions`` map and only the injection optimum + provenance."""
        return self.record_observation(
            model_id=record["model_id"],
            provider_id=record["provider_id"],
            dimensions={},
            source="injection_sweep",
            evidence_refs=[],
            injection_sweep={
                "objective": record.get("objective"),
                "selected_injection_level": record.get("selected_injection_level"),
                "recommended_injection_level": record.get("recommended_injection_level"),
                "min_sufficient_injection_level": record.get("min_sufficient_injection_level"),
                "tolerance": record.get("tolerance"),
                "per_dimension_optimal": dict(record.get("per_dimension_optimal") or {}),
                "per_dimension_min_sufficient_level": dict(record.get("per_dimension_min_sufficient_level") or {}),
                "levels": list(record.get("levels") or []),
            },
        )

    def record_assist_matrix_report(self, report) -> ModelProfile:
        key = f"{report.task_category}:{report.change_class}"
        return self.record_observation(model_id=report.model_id, provider_id=report.provider_id, dimensions={}, source="assist_matrix", evidence_refs=report.evidence_refs, assist_matrix={key: report.recommended_policy_patch})

    def update_from_candidate_score(
        self,
        score: CandidateScore,
        *,
        model_id: str,
        provider_id: str,
        dimensions: Iterable[str],
        evidence_refs: Iterable[str] | None = None,
        source: str = "candidate_score",
    ) -> ModelProfile:
        """Map a mechanical CandidateScore onto profile dimensions. A rejected
        candidate scores 0.0 on every named dimension; an eligible one uses its
        aggregate final_score."""
        value = 0.0 if score.verdict == VERDICT_REJECTED else max(0.0, min(1.0, score.final_score))
        dims = {d: value for d in dimensions}
        refs = list(evidence_refs or [])
        if score.candidate_id:
            refs.append(f"candidate:{score.candidate_id}")
        return self.record_observation(
            model_id=model_id, provider_id=provider_id, dimensions=dims,
            source=source, evidence_refs=refs,
        )

    def record_user_feedback(
        self,
        *,
        model_id: str,
        provider_id: str,
        decision: str,
        dimensions: dict[str, float] | None = None,
        evidence_refs: Iterable[str] | None = None,
    ) -> ModelProfile:
        """Record a user save/discard/Capsule decision as WEAK feedback. It is stored
        as evidence but does not move dimension scores by default."""
        return self.record_observation(
            model_id=model_id, provider_id=provider_id,
            dimensions=dimensions or {}, weak_feedback=True,
            source=f"user_decision:{decision}", evidence_refs=evidence_refs,
        )

    # ----- reading / recomputation -----

    def load_observations(self, provider_id: str, model_id: str) -> list[ProfileObservation]:
        path = self._obs_path(provider_id, model_id)
        if not path.exists():
            return []
        out: list[ProfileObservation] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(ProfileObservation.model_validate_json(line))
        return out

    def recompute_profile(
        self, provider_id: str, model_id: str, *, include_weak: bool = False, version: int = 1
    ) -> ModelProfile:
        observations = self.load_observations(provider_id, model_id)
        sums: dict[str, float] = {}
        weights: dict[str, float] = {}
        evidence: list[str] = []
        primary_samples = 0
        latest_twin: dict = {}
        latest_sweep: dict = {}
        matrix_recommendations: dict[str, dict] = {}
        for obs in observations:
            if obs.weak_feedback and not include_weak:
                # Preserve the evidence ref but do not let it move the score.
                evidence.extend(obs.evidence_refs)
                continue
            if obs.twin_assist:
                latest_twin = dict(obs.twin_assist)
            if obs.injection_sweep:
                latest_sweep = dict(obs.injection_sweep)
            if obs.assist_matrix:
                matrix_recommendations.update(obs.assist_matrix)
            w = obs.sample_weight * (self._weak_weight if obs.weak_feedback else 1.0)
            if not obs.weak_feedback:
                primary_samples += 1
            evidence.extend(obs.evidence_refs)
            for dim, val in obs.dimensions.items():
                sums[dim] = sums.get(dim, 0.0) + val * w
                weights[dim] = weights.get(dim, 0.0) + w
        dimension_scores = {
            dim: round(sums[dim] / weights[dim], 4)
            for dim in sums
            if weights.get(dim, 0.0) > 0
        }
        # De-duplicate evidence refs while preserving order.
        seen: set[str] = set()
        ev_refs = [e for e in evidence if not (e in seen or seen.add(e))]
        return ModelProfile(
            model_id=model_id, provider_id=provider_id, version=version,
            dimension_scores=dimension_scores, sample_count=primary_samples,
            updated_at=self._clock().isoformat(), evidence_refs=ev_refs,
            twin_assist_scores=dict(latest_twin.get("scores") or {}),
            twin_assist_lift=dict(latest_twin.get("lift") or {}),
            recommended_twin_assist_mode=str(latest_twin.get("mode") or ""),
            recommended_twin_injection_level=latest_twin.get("injection_level"),
            # The level ExecutionPolicy acts on, chosen by the sweep objective (min_sufficient ->
            # ceiling; max_score -> floor). Falls back across the available readings.
            measured_optimal_injection_level=(
                latest_sweep.get("selected_injection_level")
                if latest_sweep.get("selected_injection_level") is not None
                else latest_sweep.get("min_sufficient_injection_level")
                if latest_sweep.get("min_sufficient_injection_level") is not None
                else latest_sweep.get("recommended_injection_level")),
            injection_objective=str(latest_sweep.get("objective") or ""),
            twin_assist_evidence_refs=ev_refs if latest_twin else [],
            assist_matrix_recommendations=matrix_recommendations,
        )

    def _next_version(self, provider_id: str, model_id: str) -> int:
        d = self._key_dir(provider_id, model_id)
        versions = [
            int(m.group(1))
            for p in d.glob("profile.v*.json")
            if (m := re.match(r"profile\.v(\d+)\.json$", p.name))
        ]
        return (max(versions) + 1) if versions else 1

    def _write_new_version(self, provider_id: str, model_id: str) -> ModelProfile:
        version = self._next_version(provider_id, model_id)
        profile = self.recompute_profile(provider_id, model_id, version=version)
        d = self._key_dir(provider_id, model_id)
        # Versioned write: a new file every time; earlier versions are never rewritten.
        (d / f"profile.v{version}.json").write_text(
            json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (d / "latest.json").write_text(
            json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return profile

    def load_profile(self, provider_id: str, model_id: str) -> ModelProfile | None:
        latest = self._key_dir(provider_id, model_id) / "latest.json"
        if not latest.exists():
            return None
        return ModelProfile.model_validate_json(latest.read_text(encoding="utf-8"))

    def load_profile_version(self, provider_id: str, model_id: str, version: int) -> ModelProfile | None:
        path = self._key_dir(provider_id, model_id) / f"profile.v{version}.json"
        if not path.exists():
            return None
        return ModelProfile.model_validate_json(path.read_text(encoding="utf-8"))

    def list_versions(self, provider_id: str, model_id: str) -> list[int]:
        d = self._key_dir(provider_id, model_id)
        return sorted(
            int(m.group(1))
            for p in d.glob("profile.v*.json")
            if (m := re.match(r"profile\.v(\d+)\.json$", p.name))
        )

    def list_profiles(self) -> list[ModelProfile]:
        if not self._dir.exists():
            return []
        out: list[ModelProfile] = []
        for latest in self._dir.glob("*/latest.json"):
            out.append(ModelProfile.model_validate_json(latest.read_text(encoding="utf-8")))
        return out


__all__ = ["ProfileStore", "ProfileObservation", "profile_key"]
