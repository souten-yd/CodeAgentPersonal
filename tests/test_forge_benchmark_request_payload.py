"""PFH-1 benchmark run payload contract."""
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
let arenaBody = null;
global.fetch = async (url, options) => {
  if (String(url).endsWith('/api/forge/arena/run')) {
    arenaBody = JSON.parse(options.body);
    return { ok: true, json: async () => ({ arena_run_id: 'arena_payload', candidates: [{ adoption_state: 'not_applied' }] }) };
  }
  if (String(url).indexOf('/api/forge/arena/runs/') >= 0) {
    return { ok: true, json: async () => ({ arena_run_id: 'arena_payload', candidates: [] }) };
  }
  throw new Error('unexpected fetch ' + url);
};
eval(fs.readFileSync(process.argv[2], 'utf8'));
const F = global.window.Forge;
const input = JSON.parse(process.argv[3]);
Object.assign(F._state.bench, input.bench || {});
F._runBenchmark(input.data).then(() => {
  process.stdout.write(JSON.stringify(arenaBody));
}).catch((err) => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
"""


def test_run_payload_includes_all_selected_real_preset_ids_and_depth(tmp_path: Path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = tmp_path / "bench_payload.js"
    script.write_text(_NODE_TEMPLATE, encoding="utf-8")
    payload = {
        "data": {"presets": preset_listing(), "providers": []},
        "bench": {
            "presets": ["quick_standard", "repair_standard"],
            "depth": "standard",
            "provider": "local_openai_compatible",
            "model": "m1",
        },
    }
    proc = subprocess.run(
        [node, str(script), str(FORGE_JS), json.dumps(payload)],
        capture_output=True,
        text=True,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    body = json.loads(proc.stdout)
    assert body["preset_id"] == "quick_standard"
    assert body["preset_ids"] == ["quick_standard", "repair_standard"]
    assert body["depth"] == "standard"
