"""Mechanical Forge capability evaluation runs and profile previews."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agent.model_forge.capability_scoring import CapabilityScorer, build_capability_profile
from agent.model_forge.eval_packs import CaseResult, load_eval_packs, score_pack
from agent.model_forge.live_capability_eval import LIVE_CAPABILITY_DIMENSIONS, LiveCapabilityEvaluator
from agent.model_forge.method_router import MethodRouter
from agent.model_forge.method_taxonomy import MethodVariant
from agent.model_forge.profile_store import ProfileStore
from agent.model_forge.real_method_runner import RealMethodRunner
from agent.model_forge.optimizer import ForgeOptimizer
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
        results = self._run_capability_cases(
            provider_id=provider_id, model_id=model_id, base_url=base_url, selected=selected,
            source_mode=source_mode, credential_env=credential_env, timeout_seconds=timeout_seconds,
        )
        return self.run(
            provider_id=provider_id,
            model_id=model_id,
            results=results,
            dimensions=dimensions,
        )

    def _run_capability_cases(
        self, *, provider_id: str, model_id: str, base_url: str, selected: set[str],
        source_mode: str, credential_env: str, timeout_seconds: float, system_directive: str = "",
    ) -> list[CaseResult]:
        """Run the live benchmark for the selected dimensions, optionally with a Twin assist
        directive injected into the prompts. Method-backed dimensions go through the adapter
        runner; non-method capability dimensions go through the live capability evaluator."""
        packs = [pack for pack in load_eval_packs() if pack.dimension in selected]
        method_cases = [
            case for pack in packs for case in pack.cases
            if pack.dimension not in LIVE_CAPABILITY_DIMENSIONS
        ]
        results: list[CaseResult] = []
        if method_cases:
            results.extend(RealMethodRunner(self._root / "real_evidence").run_cases(
                provider_id=provider_id, model_id=model_id, base_url=base_url, cases=method_cases,
                source_mode=source_mode, credential_env=credential_env,
                timeout_seconds=timeout_seconds, system_directive=system_directive,
            ))
        live_dims = [d for d in selected if d in LIVE_CAPABILITY_DIMENSIONS]
        if live_dims:
            results.extend(LiveCapabilityEvaluator(self._root / "real_evidence").evaluate(
                provider_id=provider_id, model_id=model_id, base_url=base_url, dimensions=live_dims,
                source_mode=source_mode, timeout_seconds=timeout_seconds, system_directive=system_directive,
            ))
        return results

    # Twin assist directive injected for the "with assist" pass. Real, meaningful guidance
    # (not the full Twin pipeline) so the measured lift reflects guidance at eval time.
    ASSIST_DIRECTIVE = (
        "Twin assist guidance: follow the requested output contract exactly; copy exact, unique "
        "anchors from the provided content; keep unavailable distinct from passed; never treat mock "
        "output as live evidence; stay strictly within allowed paths; make minimal, targeted changes."
    )

    def assist_capability_profile(
        self,
        *,
        provider_id: str,
        model_id: str,
        base_url: str,
        dimensions: list[str],
        source_mode: str = "local_only",
        credential_env: str = "",
        timeout_seconds: float = 120.0,
        assist_directive: str | None = None,
    ) -> dict:
        """Measure capability WITHOUT and WITH a Twin assist directive, per dimension, so the
        Arena radar can overlay with-vs-without-assist (補助有無) from real data. Persists the
        comparison. Scores are None when a dimension had only unavailable evidence (never faked)."""
        selected = set(dimensions)
        packs = [pack for pack in load_eval_packs() if pack.dimension in selected]
        if not packs or selected.difference(pack.dimension for pack in packs):
            raise ValueError("unknown_evaluation_dimension")
        directive = self.ASSIST_DIRECTIVE if assist_directive is None else assist_directive

        baseline_results = self._run_capability_cases(
            provider_id=provider_id, model_id=model_id, base_url=base_url, selected=selected,
            source_mode=source_mode, credential_env=credential_env, timeout_seconds=timeout_seconds,
            system_directive="",
        )
        assisted_results = self._run_capability_cases(
            provider_id=provider_id, model_id=model_id, base_url=base_url, selected=selected,
            source_mode=source_mode, credential_env=credential_env, timeout_seconds=timeout_seconds,
            system_directive=directive,
        )
        baseline_scores = {p.dimension: score_pack(p, baseline_results).score for p in packs}
        assisted_scores = {p.dimension: score_pack(p, assisted_results).score for p in packs}
        lift = {
            dim: round(assisted_scores[dim] - baseline_scores[dim], 4)
            for dim in baseline_scores
            if isinstance(baseline_scores[dim], (int, float)) and isinstance(assisted_scores[dim], (int, float))
        }
        record = {
            "provider_id": provider_id,
            "model_id": model_id,
            "dimensions": sorted(selected),
            "baseline_scores": baseline_scores,
            "assisted_scores": assisted_scores,
            "lift": lift,
            "assist_directive": directive,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_assist_capability(provider_id, model_id, record)
        return record

    # Cumulative Twin guidance per injection level (0..4), mirroring TwinInjectionLevel:
    # NONE / SUMMARY / CONTRACTS_AND_IMPACT / CONSTRAINED_WITH_TESTS / STRICT_INTERFACE_AND_REPAIR.
    INJECTION_DIRECTIVES = {
        0: "",
        1: "Twin (summary): follow the requested output contract exactly.",
        2: ("Twin (contracts+impact): follow the output contract exactly; preserve interface/schema "
            "contracts and account for dependency impact."),
        3: ("Twin (constrained+tests): follow the output contract exactly; preserve contracts and impact; "
            "keep impacted tests green; keep unavailable distinct from passed; never weaken tests."),
        4: ("Twin (strict interface+repair): follow the output contract exactly; preserve contracts and "
            "impact; keep tests green and unavailable distinct from passed; use exact unique anchors; stay "
            "strictly within allowed paths; make minimal targeted repairs and no broad rewrites."),
    }

    def injection_sweep_profile(
        self,
        *,
        provider_id: str,
        model_id: str,
        base_url: str,
        dimensions: list[str],
        levels: list[int] | None = None,
        source_mode: str = "local_only",
        credential_env: str = "",
        timeout_seconds: float = 120.0,
        tolerance: float = 0.05,
        objective: str = "min_sufficient",
    ) -> dict:
        """Benchmark capability across VARYING Twin injection levels (0..4). Real measurement (one
        pass per level); scores are None when a dimension had only unavailable evidence (never faked).

        Two readings are always computed:
        - ``recommended_injection_level`` / ``per_dimension_optimal``: the PEAK level (max score;
          tie -> least injection).
        - ``min_sufficient_injection_level`` / ``per_dimension_min_sufficient_level``: the LOWEST
          level whose score stays within ``tolerance`` of that peak — the cheapest guidance that
          still works.

        ``objective`` switches WHICH reading drives ExecutionPolicy via ``selected_injection_level``:
        - ``"min_sufficient"`` (default): minimise injection — the weak-LLM cost-efficient strategy
          (ExecutionPolicy treats it as a CEILING).
        - ``"max_score"``: maximise capability — start at the peak-scoring level (ExecutionPolicy
          treats it as a FLOOR)."""
        if objective not in ("min_sufficient", "max_score"):
            raise ValueError("invalid_objective")
        selected = set(dimensions)
        packs = [pack for pack in load_eval_packs() if pack.dimension in selected]
        if not packs or selected.difference(pack.dimension for pack in packs):
            raise ValueError("unknown_evaluation_dimension")
        levels = sorted({int(lvl) for lvl in (levels or [0, 1, 2, 3, 4])})
        if any(lvl not in self.INJECTION_DIRECTIVES for lvl in levels):
            raise ValueError("invalid_injection_level")
        if not 0.0 <= float(tolerance) <= 1.0:
            raise ValueError("invalid_tolerance")
        tolerance = float(tolerance)

        scores_by_level: dict[str, dict[str, float | None]] = {}
        for lvl in levels:
            results = self._run_capability_cases(
                provider_id=provider_id, model_id=model_id, base_url=base_url, selected=selected,
                source_mode=source_mode, credential_env=credential_env,
                timeout_seconds=timeout_seconds, system_directive=self.INJECTION_DIRECTIVES[lvl],
            )
            scores_by_level[str(lvl)] = {p.dimension: score_pack(p, results).score for p in packs}

        def _min_sufficient(score_at, best: float | None) -> int | None:
            """Lowest level (levels are ascending) whose score stays within ``tolerance`` of
            ``best`` — i.e. how far injection can be lowered before capability drops too far."""
            if best is None:
                return None
            threshold = best - tolerance
            for lvl in levels:
                s = score_at(lvl)
                if isinstance(s, (int, float)) and s >= threshold - 1e-9:
                    return lvl
            return None

        # Per-dimension PEAK level: highest score; ties resolve to the LOWEST level.
        per_dimension_optimal: dict[str, int | None] = {}
        # Per-dimension MIN-SUFFICIENT level: lowest level within tolerance of that peak.
        per_dimension_min_sufficient: dict[str, int | None] = {}
        for pack in packs:
            dim = pack.dimension
            best: tuple[int, float] | None = None
            for lvl in levels:
                score = scores_by_level[str(lvl)][dim]
                if not isinstance(score, (int, float)):
                    continue
                if best is None or score > best[1] + 1e-9:
                    best = (lvl, float(score))
            per_dimension_optimal[dim] = best[0] if best else None
            per_dimension_min_sufficient[dim] = _min_sufficient(
                lambda lvl, d=dim: scores_by_level[str(lvl)][d], best[1] if best else None)

        # Overall: peak mean (tie -> lowest) AND the lowest level within tolerance of that peak.
        level_means: dict[str, float | None] = {}
        recommended: tuple[int, float] | None = None
        for lvl in levels:
            vals = [v for v in scores_by_level[str(lvl)].values() if isinstance(v, (int, float))]
            mean = round(sum(vals) / len(vals), 4) if vals else None
            level_means[str(lvl)] = mean
            if mean is not None and (recommended is None or mean > recommended[1] + 1e-9):
                recommended = (lvl, mean)
        recommended_injection_level = recommended[0] if recommended else None
        best_mean_score = recommended[1] if recommended else None
        min_sufficient_injection_level = _min_sufficient(
            lambda lvl: level_means[str(lvl)], best_mean_score)

        # The objective selects which level ExecutionPolicy acts on.
        selected_injection_level = (
            recommended_injection_level if objective == "max_score"
            else min_sufficient_injection_level)

        # Injection-resistant weaknesses: dimensions whose BEST score across all levels is still
        # weak — more injection will not fix them, so propose a different generation METHOD instead.
        from agent.model_forge.method_substitution import (
            WEAKNESS_THRESHOLD, recommend_method_substitutions,
        )
        injection_resistant = []
        for pack in packs:
            dim = pack.dimension
            vals = [scores_by_level[str(lvl)][dim] for lvl in levels]
            numeric = [v for v in vals if isinstance(v, (int, float))]
            if numeric and max(numeric) < WEAKNESS_THRESHOLD:
                injection_resistant.append(dim)
        method_substitutions = [s.as_dict() for s in recommend_method_substitutions(injection_resistant)]

        record = {
            "provider_id": provider_id,
            "model_id": model_id,
            "dimensions": sorted(selected),
            "levels": levels,
            "tolerance": tolerance,
            "objective": objective,
            "scores_by_level": scores_by_level,
            "level_means": level_means,
            "best_mean_score": best_mean_score,
            "per_dimension_optimal": per_dimension_optimal,
            "per_dimension_min_sufficient_level": per_dimension_min_sufficient,
            "recommended_injection_level": recommended_injection_level,
            "min_sufficient_injection_level": min_sufficient_injection_level,
            "selected_injection_level": selected_injection_level,
            "injection_resistant_dimensions": injection_resistant,
            "method_substitutions": method_substitutions,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_injection_sweep(provider_id, model_id, record)
        # Auto-reflect into the model profile so the measured optimum reaches ExecutionPolicy.
        self._profiles.record_injection_sweep_report(record)
        return record

    def _injection_sweep_path(self, provider_id: str, model_id: str) -> Path:
        safe = f"{provider_id}_{model_id}".replace("/", "_").replace(":", "_").replace("\\", "_")
        return self._root / "injection_sweep" / f"{safe}.json"

    def _write_injection_sweep(self, provider_id: str, model_id: str, record: dict) -> None:
        path = self._injection_sweep_path(provider_id, model_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_injection_sweep(self, provider_id: str, model_id: str) -> dict | None:
        path = self._injection_sweep_path(provider_id, model_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def _assist_capability_path(self, provider_id: str, model_id: str) -> Path:
        safe = f"{provider_id}_{model_id}".replace("/", "_").replace(":", "_").replace("\\", "_")
        return self._root / "assist_capability" / f"{safe}.json"

    def _write_assist_capability(self, provider_id: str, model_id: str, record: dict) -> None:
        path = self._assist_capability_path(provider_id, model_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_assist_capability(self, provider_id: str, model_id: str) -> dict | None:
        path = self._assist_capability_path(provider_id, model_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def model_profile(self, provider_id: str, model_id: str) -> dict:
        profile = self._profiles.load_profile(provider_id, model_id)
        capability = build_capability_profile(profile, provider_id=provider_id, model_id=model_id)
        # Benchmark-derived method fitness: turn the capability scores into which generation methods
        # this model should be driven with, and which weak methods to substitute. Measurement-driven
        # (ranked from real scores); a future per-method live measurement can slot in here.
        from agent.model_forge.method_substitution import (
            WEAKNESS_THRESHOLD, rank_methods_by_fitness, recommend_method_substitutions,
            recommend_twin_rescue,
        )
        # method_fitness is derived from the LIVE-measured capability scores. The method-backed
        # dimensions (structured/patch/edit/large_file, see real_method_runner._METHOD_BY_DIMENSION)
        # are measured by running that very method's adapter, so this is already measurement-based.
        scores = capability.capability_scores
        weak = [d for d, v in scores.items() if v < WEAKNESS_THRESHOLD]
        method_fitness_view = {
            "ranking": [{"method": m, "fitness": f} for m, f in rank_methods_by_fitness(scores)],
            "substitutions": [s.as_dict() for s in
                              recommend_method_substitutions(weak, capability_scores=scores)],
            "twin_rescues": [r.as_dict() for r in recommend_twin_rescue(weak)],
            "measured": bool(scores),
        }
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
            "method_fitness": method_fitness_view,
        }

    def optimize_preview(self, provider_id: str, model_id: str) -> dict:
        profile = self._profiles.load_profile(provider_id, model_id)
        return ForgeOptimizer().optimize(
            profile, provider_id=provider_id, model_id=model_id,
        ).model_dump(mode="json")

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
