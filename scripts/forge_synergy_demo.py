"""Synergy demo: does a (weak) LLM get its weaknesses covered and strengths amplified by the
platform — measure -> Twin injection -> assist -> failure escalation?

The honest problem: a capable model (e.g. a 35B) already saturates the baseline, so per-feature
lift is ~0 and the platform's value (don't over-inject) is real but undramatic. To SHOW the
synergy you need a model whose weaknesses actually appear. This harness runs the platform's own
injection sweep against a *controlled weak model* — a guidance-sensitive stub that can only honour
the output contract once enough Twin guidance is injected (exactly how a weak local LLM behaves) —
and reports raw (no platform) vs platform (capability-aware injection) capability.

Swap `weak_model_post` for a real provider to run the same comparison against a real weak GGUF.

Usage:  python scripts/forge_synergy_demo.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root on path

from agent.model_forge.evaluation_service import ForgeEvaluationService
from agent.model_forge.profile_store import ProfileStore

# Dimensions that respond differently to guidance, so the report shows a mix:
#  - structured_output_fidelity: the weak model only emits valid JSON WITH guidance (a weakness).
#  - edit_intent_quality: the weak model handles this even without guidance (a strength).
SWEEP_DIMS = ["structured_output_fidelity", "edit_intent_quality"]


def weak_model_post(strong_dims):
    """A controlled weak model. For dims in ``strong_dims`` it always produces valid output; for
    the rest it only produces valid output once the system directive carries level>=2 guidance."""
    def post(_url, payload, _headers, _timeout):
        system = payload["messages"][0]["content"]
        user = payload["messages"][1]["content"] if len(payload["messages"]) > 1 else ""
        guided = any(m in system for m in ("contracts+impact", "constrained+tests", "strict interface"))
        # The eval target path is embedded in the prompt; strength dims always succeed.
        strong = any(d in (system + user) for d in strong_dims)
        if strong or guided:
            content = ('{"file_changes": [{"path": "eval_target.txt", "action_type": "create", '
                       '"proposed_content": "ok"}]}')
        else:
            content = "Sure, here is the change! (prose, not the required JSON)"
        return 200, json.dumps({"id": "stub", "choices": [{"message": {"content": content}}]})
    return post


def run(strong_dims=("edit_intent_quality",)):
    import agent.model_forge.real_method_runner as rmr
    rmr._default_post = weak_model_post(set(strong_dims))  # controlled weak model

    root = Path(tempfile.mkdtemp())
    svc = ForgeEvaluationService(root, ProfileStore(root / "profiles"))
    rec = svc.injection_sweep_profile(
        provider_id="local", model_id="weak-sim", base_url="http://x",
        dimensions=SWEEP_DIMS, levels=[0, 1, 2, 3, 4],
    )
    by_level = rec["scores_by_level"]
    raw = by_level["0"]                       # no platform: injection level 0, no guidance
    chosen = str(rec["min_sufficient_injection_level"])
    platform = by_level[chosen]               # platform: capability-aware minimal-sufficient level

    print("=== Synergy: weak model, raw (no platform) vs platform ===")
    print(f"platform-chosen injection level (min_sufficient): {rec['min_sufficient_injection_level']}")
    print(f"{'dimension':32} {'raw(lvl0)':>10} {'platform':>10} {'delta':>8}")
    covered, amplified = 0, 0
    for d in SWEEP_DIMS:
        r, p = raw[d], platform[d]
        delta = round(p - r, 3)
        if r < 0.55 <= p:
            covered += 1
        if p > r:
            amplified += 1
        tag = "  <- weakness covered" if (r < 0.55 <= p) else ("  <- strength kept" if p >= 0.55 and delta == 0 else "")
        print(f"{d:32} {r:>10.2f} {p:>10.2f} {delta:>8.2f}{tag}")
    raw_mean = round(sum(raw.values()) / len(raw), 3)
    plat_mean = round(sum(platform.values()) / len(platform), 3)
    print(f"{'MEAN':32} {raw_mean:>10.2f} {plat_mean:>10.2f} {round(plat_mean-raw_mean,3):>8.2f}")
    print(f"weaknesses covered: {covered}/{len(SWEEP_DIMS)}   dims improved: {amplified}/{len(SWEEP_DIMS)}")
    return {"raw_mean": raw_mean, "platform_mean": plat_mean, "covered": covered,
            "chosen_level": rec["min_sufficient_injection_level"], "scores_by_level": by_level}


def show_substitutions(strong_dims=("structured_output_fidelity",)):
    """Second view: when injection can't fix a weakness (edit_intent), the platform proposes a
    DIFFERENT method instead. Here edit_intent stays weak at every level -> substitution kicks in."""
    import agent.model_forge.real_method_runner as rmr
    rmr._default_post = weak_model_post(set(strong_dims))
    root = Path(tempfile.mkdtemp())
    svc = ForgeEvaluationService(root, ProfileStore(root / "profiles"))
    rec = svc.injection_sweep_profile(provider_id="local", model_id="weak-sim", base_url="http://x",
                                      dimensions=SWEEP_DIMS, levels=[0, 1, 2, 3, 4])
    print("\n=== Injection-resistant weaknesses -> method substitution ===")
    print("injection_resistant_dimensions:", rec["injection_resistant_dimensions"])
    for s in rec["method_substitutions"]:
        print(f"  {s['dimension']}: avoid={s['avoid']} -> prefer={s['prefer']}")
        print(f"     why: {s['why']}")


if __name__ == "__main__":
    out = run()
    show_substitutions()
    print("\nJSON:", json.dumps(out, ensure_ascii=False))
