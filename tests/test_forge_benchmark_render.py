"""PFG-23 — Benchmark Preset selector UI render tests.

Drives the real web/js/forge.js benchmark builder under a node DOM stub: the four primary
presets render as checkboxes, depth defaults to standard (deep not forced), and selecting
an external provider raises a policy warning.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agent.model_forge.benchmark_presets import preset_listing

ROOT = Path(__file__).resolve().parent.parent
FORGE_JS = ROOT / "web" / "js" / "forge.js"

_NODE_TEMPLATE = r"""
const fs = require('fs');
const store = {};
function mkEl(){ return { _html:'', set innerHTML(v){this._html=v;}, get innerHTML(){return this._html;},
  textContent:'', classList:{toggle(){},add(){},remove(){}}, addEventListener(){},
  querySelectorAll(){return [];}, querySelector(){return null;}, appendChild(){}, getAttribute(){return '';} }; }
global.document = { getElementById:(id)=>store[id]||(store[id]=mkEl()),
  createElement:()=>mkEl(), body:{appendChild(){}}, addEventListener(){} };
global.window = {};
global.fetch = () => Promise.reject(new Error('no-net'));
eval(fs.readFileSync(process.argv[2], 'utf8'));
const F = global.window.Forge;
const input = JSON.parse(process.argv[3]);
Object.assign(F._state.bench, input.bench || {});
process.stdout.write(F._benchmarkHtml(input.data));
"""


def _render(tmp_path, payload: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "bench.js"
    script.write_text(_NODE_TEMPLATE, encoding="utf-8")
    proc = subprocess.run([node, str(script), str(FORGE_JS), json.dumps(payload)],
                          capture_output=True, text=True, timeout=30,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


_PRESETS = preset_listing()


def test_primary_presets_render_as_checkboxes(tmp_path):
    html = _render(tmp_path, {"data": {"presets": _PRESETS, "providers": []}, "bench": {}})
    for pid in ("quick_standard", "web_app_standard", "repair_standard", "greenfield_standard"):
        assert 'data-bench-preset="' + pid + '"' in html
    # Non-primary preset is tucked under a "More presets" disclosure, not a top checkbox grid.
    assert "More presets" in html


def test_depth_defaults_to_standard_not_deep(tmp_path):
    html = _render(tmp_path, {"data": {"presets": _PRESETS, "providers": []}, "bench": {}})
    # 'standard' is the active segment; 'deep' is present but not active by default.
    assert 'data-bench-depth="standard"' in html
    assert 'forge-seg active" data-bench-depth="standard"' in html
    assert 'forge-seg active" data-bench-depth="deep"' not in html


def test_external_provider_shows_policy_warning(tmp_path):
    data = {
        "presets": _PRESETS,
        "providers": [{"provider_id": "openrouter", "source_class": "external_cloud", "health": "disabled"}],
    }
    html = _render(tmp_path, {"data": data, "bench": {"provider": "openrouter"}})
    assert "forge-warn" in html
    assert "External provider selected" in html


def test_provider_card_shows_configured_and_runtime_state(tmp_path):
    html = _render(tmp_path, {
        "data": {
            "presets": _PRESETS,
            "providers": [{
                "provider_id": "local_openai_compatible",
                "source_class": "self_hosted",
                "health": "unavailable",
                "health_detail": "runtime_not_probed",
                "configured_state": "configured",
                "runtime_health": "not_probed",
            }],
        },
        "bench": {},
    })
    # Sanity-check benchmark renderer still ignores provider cards.
    assert "Configured: configured" not in html


def test_openrouter_catalog_models_render_as_model_selector(tmp_path):
    data = {
        "presets": _PRESETS,
        "providers": [{"provider_id": "openrouter", "source_class": "external_cloud", "health": "ready"}],
        "openrouterCatalog": {
            "status": "from_cache",
            "models": [{"model_id": "anthropic/claude", "display_name": "Claude"}],
        },
    }
    html = _render(tmp_path, {"data": data, "bench": {"provider": "openrouter"}})
    assert "data-bench-model-select" in html
    assert "anthropic/claude" in html


def test_anvil_runtime_lists_registry_models_with_per_model_config_button(tmp_path):
    # The "LLM management tool" (Anvil) offers registered models (Models DB) in a benchmark dropdown
    # with their context length, plus a per-model 詳細設定 button that opens the parameter drawer.
    data = {
        "presets": _PRESETS,
        "providers": [],
        "localModels": [
            {"id": "row1", "model_key": "mistral-small", "name": "Mistral Small", "ctx_size": 16384},
            {"id": "row2", "model_key": "qwen-coder", "name": "Qwen Coder", "ctx_size": 32768},
        ],
    }
    # Anvil appears as a selectable provider/tool.
    opts = _render(tmp_path, {"data": data, "bench": {}})
    assert 'value="anvil"' in opts and "Anvil" in opts
    # With Anvil selected, the benchmark dropdown plus a 詳細設定 button per registered model render.
    html = _render(tmp_path, {"data": data, "bench": {"provider": "anvil", "model": "mistral-small"}})
    assert "data-bench-model-select" in html
    assert "mistral-small" in html and "Mistral Small" in html
    assert "ctx 16384" in html
    assert "詳細設定" in html
    assert 'data-anvil-config data-model-id="row1"' in html
    assert 'data-anvil-config data-model-id="row2"' in html


_NODE_CONFIG_FORM_TEMPLATE = r"""
const fs = require('fs');
const store = {};
function mkEl(){ return { _html:'', set innerHTML(v){this._html=v;}, get innerHTML(){return this._html;},
  textContent:'', classList:{toggle(){},add(){},remove(){}}, addEventListener(){},
  querySelectorAll(){return [];}, querySelector(){return null;}, appendChild(){}, getAttribute(){return '';} }; }
global.document = { getElementById:(id)=>store[id]||(store[id]=mkEl()),
  createElement:()=>mkEl(), body:{appendChild(){}}, addEventListener(){} };
global.window = {};
global.fetch = () => Promise.reject(new Error('no-net'));
eval(fs.readFileSync(process.argv[2], 'utf8'));
const F = global.window.Forge;
const model = JSON.parse(process.argv[3]);
process.stdout.write(F._anvilConfigFormHtml(model));
"""


def _render_config_form(tmp_path, model: dict) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "configform.js"
    script.write_text(_NODE_CONFIG_FORM_TEMPLATE, encoding="utf-8")
    proc = subprocess.run([node, str(script), str(FORGE_JS), json.dumps(model)],
                          capture_output=True, text=True, timeout=30,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_anvil_config_form_exposes_all_params_as_pulldowns(tmp_path):
    # The 詳細設定 drawer form surfaces every llama-server launch param as a <select> pulldown,
    # prefilled from the model's registry row, so a model can be configured like the pasted command.
    model = {
        "id": "row1", "model_key": "qwen36", "name": "Qwen3.6",
        "ctx_size": 16384, "n_cpu_moe": 14, "spec_type": "draft-mtp",
        "spec_draft_n_max": 2, "spec_draft_p_min": 0.75, "temp": 0.7,
        "top_p": 0.8, "top_k": 20, "min_p": 0.0, "presence_penalty": 1.5,
        "repeat_penalty": 1.0, "flash_attn": 1, "jinja": 1, "no_mmap": 1,
        "cache_type_k": "q8_0", "cache_type_v": "q8_0", "batch_size": 2048,
        "ubatch_size": 256, "threads": 16, "parallel": 1, "gpu_layers": 999,
    }
    html = _render_config_form(tmp_path, model)
    for key in ("ctx_size", "gpu_layers", "n_cpu_moe", "threads", "parallel", "batch_size",
                "ubatch_size", "cache_type_k", "cache_type_v", "flash_attn", "no_mmap", "jinja",
                "reasoning", "spec_type", "spec_draft_n_max", "spec_draft_p_min", "temp",
                "top_p", "top_k", "min_p", "presence_penalty", "repeat_penalty"):
        assert '<select class="forge-select" data-anvil-param="' + key + '">' in html
    # Stored values preselect their option (pulldown), and a カスタム… escape hatch is present.
    assert '<option value="14" selected>14</option>' in html
    assert '<option value="draft-mtp" selected>draft-mtp</option>' in html
    assert '<option value="1" selected>ON</option>' in html  # flash_attn / jinja / no_mmap
    assert "カスタム…" in html


def test_anvil_config_form_custom_value_selects_custom_option(tmp_path):
    # A stored value that is not among the curated choices preselects カスタム… and fills the input.
    model = {"id": "row9", "name": "Custom", "ctx_size": 20000}
    html = _render_config_form(tmp_path, model)
    assert '<option value="__custom__" selected>カスタム…</option>' in html
    assert 'data-anvil-custom="ctx_size"' in html
    assert 'value="20000"' in html


def test_lm_studio_runtime_is_offered_with_model_dropdown_and_ctx(tmp_path):
    data = {
        "presets": _PRESETS,
        "providers": [],
        "lmStudioCatalog": {"status": "ready", "models": [{"model_id": "lmstudio-model-a"}]},
    }
    opts = _render(tmp_path, {"data": data, "bench": {}})
    assert 'value="lm_studio"' in opts and "LM Studio" in opts
    html = _render(tmp_path, {"data": data, "bench": {"provider": "lm_studio", "model": "lmstudio-model-a"}})
    assert "lmstudio-model-a" in html
    assert "data-bench-ctx" in html


def test_runtime_management_enabled_shows_load_action_for_anvil(tmp_path):
    # With runtime management ON, the Anvil model card offers a Load action and shows load status;
    # with it OFF there is no Load button (benchmark uses the already-loaded model).
    base = {
        "presets": _PRESETS,
        "providers": [],
        "localModels": [{"id": "row1", "model_key": "mistral-small", "name": "Mistral Small", "ctx_size": 16384}],
    }
    on = dict(base, settings={"runtime_management": {"enabled": True}}, runtimeStatus={"status": "loading", "current_key": "mistral-small"})
    html_on = _render(tmp_path, {"data": on, "bench": {"provider": "anvil", "model": "mistral-small"}})
    assert "data-bench-load" in html_on
    assert "Load status" in html_on and "loading" in html_on

    off = dict(base, settings={"runtime_management": {"enabled": False}})
    html_off = _render(tmp_path, {"data": off, "bench": {"provider": "anvil", "model": "mistral-small"}})
    assert "data-bench-load" not in html_off


def test_runtime_management_lm_studio_load_is_marked_deferred(tmp_path):
    data = {
        "presets": _PRESETS,
        "providers": [],
        "settings": {"runtime_management": {"enabled": True}},
        "lmStudioCatalog": {"status": "ready", "models": [{"model_id": "lm-a"}]},
    }
    html = _render(tmp_path, {"data": data, "bench": {"provider": "lm_studio", "model": "lm-a"}})
    # LM Studio auto-load is deferred — no real load button, an explicit message instead.
    assert "data-bench-load" not in html
    assert "後日対応" in html


def test_run_disabled_until_preset_provider_model_chosen(tmp_path):
    data = {"presets": _PRESETS, "providers": [{"provider_id": "local_openai_compatible", "source_class": "self_hosted", "health": "ready"}]}
    # Nothing selected -> Run disabled.
    html0 = _render(tmp_path, {"data": data, "bench": {}})
    assert "data-bench-run disabled" in html0
    # Preset + provider + model -> Run enabled.
    html1 = _render(tmp_path, {"data": data, "bench": {"presets": ["quick_standard"], "provider": "local_openai_compatible", "model": "m1"}})
    assert "data-bench-run disabled" not in html1
    assert "data-bench-run" in html1
