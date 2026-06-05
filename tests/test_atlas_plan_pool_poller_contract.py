from pathlib import Path


API_JS = Path("web/js/atlas_pipeline_api.js")


def test_plan_pool_poller_uses_stall_signal_instead_of_fixed_eight_minute_cap() -> None:
    js = API_JS.read_text(encoding="utf-8")

    assert "maxWaitMs = 480000" not in js
    assert "PLAN_POOL_ABSOLUTE_MAX_MS = 2700000" in js
    assert "is_stalled === true" in js
    assert "plan_pool_stalled" in js
    assert "plan_pool_absolute_timeout" in js
    assert "モデルが混雑しています" not in js[js.index("async pollPlanPoolUntilReady"):]

