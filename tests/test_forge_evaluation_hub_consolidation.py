"""Request #1: benchmark + Twin injection/route/method evaluation shown together."""
from pathlib import Path


def test_runtime_policy_shows_benchmark_capability_together():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    # The Runtime Policy sub-tab now also shows the benchmark capability it derives from.
    assert "Benchmark capability" in source
    assert "modelProfile.capability_profile.capability_scores" in source
    assert "derived from" in source
    # route/method/injection remain in the same view.
    assert "method variant" in source
    assert "twin injection level" in source


def test_preview_fetches_model_profile_for_consolidation():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    assert "/evaluation/model-profile?provider_id=" in source
    assert "state.twinAssist.modelProfile" in source
