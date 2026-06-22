"""Drive the REAL autonomous codegen orchestrator end-to-end against the live local model.

Plan pool -> generate -> apply (Safe Apply) -> verify -> complete, through the production app wiring
(create_app + the real AtlasLLMJsonAdapter pointed at the local server). Prints the phase/status/
stop_reason and key metadata so we can see exactly where it stops and fix generically.

Run:  python scripts/forge_e2e_live_run.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from app.server import create_app

BASE_URL = "http://127.0.0.1:8080"
MODEL = "Qwen3.6-35B-A3B-UD-IQ4_XS.gguf"


def _active_envelope(allowed):
    return {
        "envelope_id": "pre_authorized_bounded_dev_envelope",
        "status": "active",
        "bounds": {
            "allowed_paths": allowed,
            "blocked_paths": [".git/"],
            "max_actions_per_loop": 8,
            "max_files_changed": 8,
            "max_runtime_seconds": 600,
            "max_risk_level": "medium",
        },
    }


def main():
    root = Path(tempfile.mkdtemp(prefix="forge_e2e_"))
    project = root / "workspace" / "proj"
    (project / "src").mkdir(parents=True, exist_ok=True)
    # A tiny real project under src/ (allowed_paths are project-relative prefixes).
    (project / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (project / "src" / "test_calc.py").write_text(
        "from calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n", encoding="utf-8")

    storage = AtlasPlanPoolStorage(root)
    pool = AtlasPlanPool(
        pool_id="pool_e2e", root_goal="Add a subtract function to calc.py with a test",
        project_path=str(project), status="ready",
        items=[AtlasPlanItem(
            item_id="item_sub", pool_id="pool_e2e",
            title="Add subtract() to calc.py",
            goal="Add a subtract(a, b) function returning a - b to calc.py, and a test in test_calc.py.",
            item_type="implementation", status="ready", risk_level="low",
            target_files=["src/calc.py"],  # test is added deterministically by expand_test_plan
            metadata={"action_type": "update"})],
        metadata={})
    storage.save_pool(pool)

    app = create_app()
    app.state.atlas_ca_data_root = str(root)
    app.state.atlas_llm_json_fn = AtlasLLMJsonAdapter(base_url=BASE_URL, model=MODEL)
    client = TestClient(app)

    payload = {
        "pool_id": "pool_e2e",
        "user_requirement": "Add a subtract function to calc.py with a test",
        "workspace_id": "default",
        "project_path": str(project),
        "selected_profile": "autonomous_dev_agent",
        "policy_id": "full_auto_multi_item_v1",
        "envelope": _active_envelope(["src/"]),
        "allowed_paths": ["src/"],
        "max_retries": 2,
        "max_runtime_seconds": 600,
        "generate_missing_patches": True,
        "expand_test_plan": True,
        "run_integration_verification": True,
        "metadata": {"model_id": MODEL, "provider_id": "local_openai_compatible",
                     "forge_model_id": MODEL, "forge_provider_id": "local_openai_compatible"},
    }
    resp = client.post("/api/atlas/autonomous-codegen/run", json=payload)
    print("HTTP", resp.status_code)
    try:
        body = resp.json()
    except Exception:
        print(resp.text[:2000]); return
    keys = ("phase", "status", "generated_count", "skipped_generation_count", "stop_reason",
            "warnings", "errors")
    print(json.dumps({k: body.get(k) for k in keys}, ensure_ascii=False, indent=2))
    md = body.get("metadata", {})
    print("metadata keys:", sorted(md.keys())[:30])
    # surface twin/policy + apply summary if present
    for k in ("twin_control_plane", "twin_repair_attempts", "autopilot_result"):
        if k in md or k in body:
            v = md.get(k, body.get(k))
            print(f"--- {k} ---", json.dumps(v, ensure_ascii=False)[:1200])
    print("ROOT", root)


if __name__ == "__main__":
    main()
