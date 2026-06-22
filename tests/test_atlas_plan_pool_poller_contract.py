from pathlib import Path


API_JS = Path("web/js/atlas_pipeline_api.js")


def test_plan_pool_poller_uses_stall_signal_instead_of_fixed_eight_minute_cap() -> None:
    js = API_JS.read_text(encoding="utf-8")

    assert "maxWaitMs = 480000" not in js
    assert "is_stalled === true" in js
    assert "plan_pool_stalled" in js
    assert "モデルが混雑しています" not in js[js.index("async pollPlanPoolUntilReady"):]


def test_plan_pool_poller_is_server_authoritative_with_no_client_deadline() -> None:
    # The browser must not police generation time: stall/timeout/completion is judged server-side
    # (status + is_stalled). The plan poller loops until a server terminal/stall verdict or an
    # unreachable status endpoint — it has NO client-side absolute deadline.
    js = API_JS.read_text(encoding="utf-8")
    poller = js[js.index("async pollPlanPoolUntilReady"):js.index("listPlanPools()")]
    assert "while (true)" in poller
    assert "absoluteMaxMs" not in poller
    assert "Date.now() - startTime" not in poller
    assert "plan_pool_absolute_timeout" not in poller
    # Server verdicts remain the only stop conditions.
    assert "is_stalled === true" in poller
    assert "status === 'ready'" in poller
    assert "status === 'failed'" in poller

