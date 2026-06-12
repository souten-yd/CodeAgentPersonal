"""PFG-21 — Forge Overview and Provider cards render tests.

Drives the real web/js/forge.js render path under a minimal DOM stub via node, proving:
the Overview works with no configured external provider, and a missing OpenRouter key /
disabled provider renders as a disabled/unavailable status with a plain note rather than
error spam.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FORGE_JS = ROOT / "web" / "js" / "forge.js"

_NODE_SCRIPT = r"""
const fs = require('fs');
const store = {};
global.document = {
  getElementById: (id) => store[id] || (store[id] = {
    _html: '', set innerHTML(v){this._html=v;}, get innerHTML(){return this._html;},
    textContent: '', classList: { toggle(){}, add(){}, remove(){} }, addEventListener(){},
  }),
  addEventListener(){},
};
global.window = {};
global.fetch = () => Promise.reject(new Error('no-net'));
eval(fs.readFileSync(process.argv[2], 'utf8'));
const Forge = global.window.Forge;
Forge._renderOverview(
  { forge_enabled: false, source_mode: 'local_only', profile_count: 0 },
  [
    { provider_id: 'legacy_atlas', source_class: 'local', health: 'unavailable', health_detail: 'legacy_backend_unwired' },
    { provider_id: 'local_openai_compatible', source_class: 'self_hosted', health: 'unavailable', health_detail: 'missing_base_url' },
    { provider_id: 'openrouter', source_class: 'external_cloud', health: 'disabled', health_detail: 'provider_disabled' },
  ],
  [{ loadout_id: 'local_safe', display_name: 'Local Safe', builtin: true }]
);
process.stdout.write(store['forge-body'].innerHTML);
"""


@pytest.fixture(scope="module")
def rendered_html(tmp_path_factory) -> str:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path_factory.mktemp("forge") / "render.js"
    script.write_text(_NODE_SCRIPT, encoding="utf-8")
    proc = subprocess.run([node, str(script), str(FORGE_JS)],
                          capture_output=True, text=True, timeout=30,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_overview_renders_with_no_external_provider(rendered_html):
    assert "Overview" in rendered_html
    assert "Local Safe" in rendered_html          # active loadout
    assert "local_only" in rendered_html          # source mode


def test_all_three_providers_are_labelled(rendered_html):
    assert "Legacy Atlas" in rendered_html
    assert "Local model" in rendered_html
    assert "OpenRouter" in rendered_html


def test_missing_openrouter_key_is_disabled_not_error_spam(rendered_html):
    # Disabled badge, plain explanatory note — not an error badge.
    assert "forge-badge-disabled" in rendered_html
    assert "Disabled by default" in rendered_html
    assert "forge-badge-error" not in rendered_html


def test_local_without_server_shows_config_hint(rendered_html):
    assert "No local server configured" in rendered_html
