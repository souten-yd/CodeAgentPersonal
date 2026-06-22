"""Source-render checks for the Benchmark injection-sweep curve UI (B)."""
from pathlib import Path


def _forge_js() -> str:
    return Path("web/js/forge.js").read_text(encoding="utf-8")


def test_injection_sweep_consolidated_into_benchmark():
    src = _forge_js()
    # The sweep runs as part of the single Benchmark action — no separate panel/button.
    assert "Run injection sweep" not in src
    assert "data-injection-sweep-run" not in src
    assert "injectionSweepCard" not in src
    # Result renders inline under Benchmark; objective control moved to the Benchmark area.
    assert "injectionSweepInlineHtml" in src
    assert "Twin injection sweep（今回の実行）" in src
    assert "injectionObjectiveControl" in src


def test_injection_sweep_calls_forge_api_with_dimensions():
    src = _forge_js()
    assert "api('/evaluation/injection-sweep'" in src
    assert "INJECTION_SWEEP_DIMENSIONS" in src
    assert "structured_output_fidelity" in src and "edit_intent_quality" in src


def test_injection_sweep_renders_curve_from_level_means():
    src = _forge_js()
    # The curve is an inline SVG polyline over level_means (no chart library).
    assert "injectionSweepChart" in src
    assert "level_means" in src
    assert "<polyline" in src
    assert "recommended_injection_level" in src
    assert "per_dimension_optimal" in src


def test_injection_sweep_surfaces_min_sufficient_level():
    src = _forge_js()
    # The headline for a weak LLM is how far injection can be lowered.
    assert "min sufficient injection level" in src
    assert "min_sufficient_injection_level" in src
    assert "per_dimension_min_sufficient_level" in src
    # Sufficiency threshold band on the chart (peak - tolerance).
    assert "forge-chart-threshold" in src
    assert "best_mean_score" in src


def test_injection_sweep_chart_css_present():
    css = Path("web/css/app.css").read_text(encoding="utf-8")
    assert ".forge-chart" in css
    assert ".forge-chart-line" in css
    assert ".is-recommended" in css


def test_injection_sweep_escapes_rendered_dimension_keys():
    src = _forge_js()
    assert "escapeHtml(dim)" in src


def test_injection_sweep_objective_switch_present():
    src = _forge_js()
    # Switchable strategy: min injection vs max score.
    assert "data-injection-objective" in src
    assert "INJECTION_OBJECTIVES" in src
    assert "Max score" in src and "Min injection" in src
    assert "objective: sel.injectionObjective" in src
    assert "selected injection level" in src
    assert "selected_injection_level" in src


def test_benchmark_button_runs_all_three_in_one_go():
    src = _forge_js()
    # The single Benchmark action orchestrates benchmark + injection sweep + Twin eval.
    assert "runArenaCore" in src
    assert "runInjectionSweepCore" in src
    assert "runTwinAssistCore" in src
    assert "api('/twin-assist/run'" in src
    assert "api('/arena/run'" in src
    # Twin result surfaced inline in the Benchmark tab.
    assert "twinAssistInlineHtml" in src
    assert "Twin assist 評価" in src


def test_reading_tips_and_direction_unification_present():
    src = _forge_js()
    # "How to read" tips so score/level direction is unambiguous.
    assert "forgeTipsHtml" in src
    assert "読み方" in src
    # Injection level direction is spelled out (lower = better) and restated as a higher-is-better
    # autonomy index so it reads the same way as capability scores.
    assert "低いほど" in src
    assert "autonomyIndex" in src
    assert "自律度" in src
    assert "best_mean_score" in src
    # Radar carries the "bigger area = more capable" note so the graph direction is unified.
    assert "面積が大きいほど能力が高い" in src


def test_method_fitness_panel_in_benchmark_capability():
    src = _forge_js()
    # Benchmark-derived method fitness surfaced in the capability view.
    assert "methodFitnessHtml" in src
    assert "method_fitness" in src
    assert "手法の向き不向き" in src
    assert "forge-fit-bar" in src


def test_method_fitness_radar_and_twin_rescue_in_arena():
    src = _forge_js()
    # Method-fitness radar shown in the Arena candidate drawer.
    assert "methodFitnessRadarHtml" in src
    assert "Method fitness radar" in src
    # Twin-offload rescue (the non-method weak-LLM rescue) surfaced alongside method substitution.
    assert "twin_rescues" in src
    assert "Twin肩代わり" in src


def test_method_substitution_surfaced_in_ui():
    src = _forge_js()
    # Injection-resistant weaknesses get an alternative-method suggestion in the sweep result.
    assert "methodSubstitutionHtml" in src
    assert "method_substitutions" in src
    assert "注入では直らない弱点" in src
    assert "代わりに使う手法" in src


def test_local_server_port_option_present():
    src = _forge_js()
    # An already-running local model addressed by port (default 8080), no Anvil registry needed.
    assert "ローカルサーバ（ポート指定）" in src
    assert "data-bench-port" in src
    assert "localPortBaseUrl" in src
    assert "loadLocalPortCatalog" in src
    assert "127.0.0.1:" in src
