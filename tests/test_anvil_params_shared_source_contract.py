"""Anvil per-model parameters: single source of truth shared by both editor UIs.

The Forge "⚙ 詳細設定" drawer (web/js/forge.js) and the Models tab Anvil modal (inline in
ui.html) edit the same Models DB columns. Their field definitions + value conversions must come
from the one shared module web/js/anvil_params.js, so adding/changing a field (e.g. the output
token cap) updates both at once instead of needing parallel edits.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ANVIL_JS = ROOT / "web" / "js" / "anvil_params.js"
FORGE_JS = (ROOT / "web" / "js" / "forge.js").read_text(encoding="utf-8")
UI_HTML = (ROOT / "ui.html").read_text(encoding="utf-8")


def test_forge_drawer_reads_from_shared_module_not_local_list() -> None:
    # forge.js must source the field list/conversions from the shared module, not re-declare them.
    assert "root.AnvilParams.FLAT" in FORGE_JS
    assert "root.AnvilParams.GROUPS" in FORGE_JS
    assert "root.AnvilParams.storedToInput" in FORGE_JS
    assert "root.AnvilParams.toPayloadValue" in FORGE_JS
    # The old hardcoded definitions are gone (would otherwise drift from the modal).
    assert "const ANVIL_PARAM_FIELDS = [" not in FORGE_JS


def test_models_tab_modal_reads_from_shared_module_not_local_list() -> None:
    assert "window.AnvilParams.GROUPS" in UI_HTML
    assert "window.AnvilParams.FLAT" in UI_HTML
    assert "window.AnvilParams.storedToInput" in UI_HTML
    assert "window.AnvilParams.toPayloadValue" in UI_HTML
    # The old inline definitions are gone.
    assert "const ANVIL_LLAMA_PARAMS = [" not in UI_HTML
    assert "ANVIL_PARAM_FLAT" not in UI_HTML


def test_shared_module_loads_before_forge_in_ui() -> None:
    anvil_idx = UI_HTML.index("anvil_params.js")
    forge_idx = UI_HTML.index("forge.js?v=")
    assert anvil_idx < forge_idx, "anvil_params.js must load before forge.js"


def test_shared_module_defines_groups_flat_and_output_token_cap() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")
    script = (
        "global.window={};"
        "eval(require('fs').readFileSync(process.argv[1],'utf8'));"
        "const A=window.AnvilParams;"
        "process.stdout.write(JSON.stringify({"
        "groups:A.GROUPS.map(g=>g.group),"
        "keys:A.FLAT.map(f=>f.key),"
        "in_zero:A.storedToInput({type:'num'},-1),"
        "pay_empty:A.toPayloadValue({type:'num'},''),"
        "pay_num:A.toPayloadValue({type:'num'},'16384'),"
        "pay_text:A.toPayloadValue({type:'text'},'  q8_0 '),"
        "ctx_opts:A.FLAT.find(f=>f.key==='ctx_size').opts,"
        "max_tokens_opts:A.FLAT.find(f=>f.key==='max_output_tokens').opts,"
        "}));"
    )
    proc = subprocess.run([node, "-e", script, str(ANVIL_JS)],
                          capture_output=True, text=True, timeout=30,
                          encoding="utf-8", errors="replace")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["groups"] == ["基本", "思考 / 投機デコード", "サンプリング", "生成"]
    assert "max_output_tokens" in data["keys"]
    # Conversions: sentinel round-trips, blank -> -1, numeric kept, text trimmed.
    assert data["in_zero"] == ""
    assert data["pay_empty"] == -1
    assert data["pay_num"] == 16384
    assert data["pay_text"] == "q8_0"
    # Ceiling raised to 256K per explicit user request (mirrors main.py's _MAX_LLM_CTX_SIZE); the
    # output-token cap presets were raised alongside it so a 256K-context model isn't stuck
    # picking from options capped at 32768.
    assert 262144 in data["ctx_opts"]
    assert max(data["max_tokens_opts"]) >= 131072
