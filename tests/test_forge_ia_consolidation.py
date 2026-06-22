"""Forge IA consolidation: no Overview tab; Twin Assist runs inside Benchmark."""
from pathlib import Path

SRC = Path("web/js/forge.js").read_text(encoding="utf-8")


def test_overview_and_twin_assist_removed_from_tabs():
    # The TABS list no longer exposes Overview or a standalone Twin Assist tab.
    tabs = SRC[SRC.index("const TABS = ["): SRC.index("];", SRC.index("const TABS = ["))]
    assert "id: 'overview'" not in tabs
    assert "id: 'twin-assist'" not in tabs
    for keep in ("'skills'", "'benchmark'", "'arena'", "'loadouts'", "'settings'", "'advanced'"):
        assert keep in tabs


def test_default_tab_is_benchmark():
    assert "tab: 'benchmark'," in SRC


def test_benchmark_is_single_evaluation_hub_no_subnav():
    # The Twin Assist sub-tab was removed: the Benchmark body and the capability/runtime-policy
    # views render together as one hub.
    assert 'data-bench-subtab="twin-assist"' not in SRC
    assert "_benchmarkBody(data) + capabilityPolicyHtml()" in SRC


def test_providers_and_status_moved_into_settings():
    assert "Providers & status" in SRC
    # probe wiring is present in settings now.
    settings_wire = SRC[SRC.index("function wireSettings"):]
    settings_wire = settings_wire[: settings_wire.index("\n  function ")]
    assert "data-provider-probe" in settings_wire
