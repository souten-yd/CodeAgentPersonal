"""Continuous multi-task end-to-end completion check against the live local model.

Runs several distinct small coding tasks through the REAL autonomous codegen orchestrator with
deterministic test planning (expand_test_plan) + integration verification on, and reports the
completion status of each so we can see the pipeline complete repeatedly (not a one-off).

Run:  python scripts/forge_e2e_multi.py
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

TASKS = [
    ("subtract", "Add subtract(a, b) returning a - b to calc.py.",
     "calc.py", "def add(a, b):\n    return a + b\n"),
    ("multiply", "Add multiply(a, b) returning a * b to mathops.py.",
     "mathops.py", "def add(a, b):\n    return a + b\n"),
    ("greet", "Add greet(name) returning 'Hello, ' + name to greet.py.",
     "greet.py", "GREETING = 'Hello, '\n"),
]


def _envelope():
    return {"envelope_id": "pre_authorized_bounded_dev_envelope", "status": "active",
            "bounds": {"allowed_paths": ["src/"], "blocked_paths": [".git/"],
                       "max_actions_per_loop": 8, "max_files_changed": 8,
                       "max_runtime_seconds": 600, "max_risk_level": "medium"}}


def run_task(client, storage, project, pool_id, goal, code_rel, seed):
    (project / "src").mkdir(parents=True, exist_ok=True)
    (project / "src" / code_rel).write_text(seed, encoding="utf-8")
    pool = AtlasPlanPool(
        pool_id=pool_id, root_goal=goal, project_path=str(project), status="ready",
        items=[AtlasPlanItem(item_id="item_1", pool_id=pool_id, title=goal, goal=goal,
                             item_type="implementation", status="ready", risk_level="low",
                             target_files=[f"src/{code_rel}"], metadata={"action_type": "update"})],
        metadata={})
    storage.save_pool(pool)
    payload = {
        "pool_id": pool_id, "user_requirement": goal, "workspace_id": "default",
        "project_path": str(project), "selected_profile": "autonomous_dev_agent",
        "policy_id": "full_auto_multi_item_v1", "envelope": _envelope(), "allowed_paths": ["src/"],
        "max_retries": 2, "max_runtime_seconds": 600, "generate_missing_patches": True,
        "expand_test_plan": True, "run_integration_verification": True,
        "metadata": {"model_id": MODEL, "provider_id": "local_openai_compatible",
                     "forge_model_id": MODEL, "forge_provider_id": "local_openai_compatible"},
    }
    body = client.post("/api/atlas/autonomous-codegen/run", json=payload).json()
    ar = (body.get("metadata") or {}).get("autopilot_result") or body.get("autopilot_result") or {}
    iv = (body.get("metadata") or {}).get("integration_verification") or {}
    return {"task": pool_id, "status": body.get("status"), "phase": body.get("phase"),
            "completed": ar.get("completed_count"), "failed": ar.get("failed_count"),
            "applied_no_verification": ar.get("applied_no_verification_count"),
            "integration": iv.get("status")}


def main():
    root = Path(tempfile.mkdtemp(prefix="forge_e2e_multi_"))
    storage = AtlasPlanPoolStorage(root)
    app = create_app()
    app.state.atlas_ca_data_root = str(root)
    app.state.atlas_llm_json_fn = AtlasLLMJsonAdapter(base_url=BASE_URL, model=MODEL)
    client = TestClient(app)
    results = []
    for name, goal, code_rel, seed in TASKS:
        proj = root / "workspace" / name
        results.append(run_task(client, storage, proj, f"pool_{name}", goal, code_rel, seed))
        print("DONE", json.dumps(results[-1], ensure_ascii=False)); sys.stdout.flush()
    done = sum(1 for r in results if r["status"] == "completed")
    print(f"\n=== {done}/{len(results)} tasks reached status=completed ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
