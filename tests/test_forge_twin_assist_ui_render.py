from pathlib import Path


def test_twin_assist_results_render_and_safety_copy():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    # The dedicated Twin-eval tab/button/run form was removed; the run is part of the Benchmark
    # action and results render inline under Benchmark.
    assert "Run Twin Assist Eval" not in source
    assert "forge-twin-run" not in source
    assert "function twinAssistHtml" not in source
    # Results still render (baseline vs assisted lift/harm) and the safety copy is preserved.
    assert "baseline" in source and "assisted" in source and "lift" in source and "harm" in source
    assert "twin_localized_slot" in source and "twin_deterministic_anchor" in source
    assert "ファイル適用や本番ルーティングは変更しません" in source


def test_twin_eval_runs_via_benchmark_action_and_escapes_values():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    # The combined Benchmark action fetches cases and runs the twin eval.
    assert "api('/twin-assist/cases?pack_id=quick')" in source
    assert "api('/twin-assist/run'" in source
    assert "runTwinAssistCore" in source
    assert "escapeHtml(item.case_id)" in source
    assert "textContent = JSON.stringify" in source


def test_twin_result_shown_in_benchmark_area_honestly():
    source = Path("web/js/forge.js").read_text(encoding="utf-8")
    # Twin result lives inline under Benchmark, and an unavailable run is shown honestly.
    assert "twinAssistInlineHtml" in source
    assert "Twin assist 評価（今回の実行）" in source
    assert "twinUnavailableReasons" in source
    assert "fixture_missing" in source
