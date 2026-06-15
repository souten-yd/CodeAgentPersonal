"""Real-LLM evaluation of Twin/Forge/Git usefulness (real_model-gated).

Drives the real autonomous codegen stack against the local LLM across a condition matrix
for two projects (a Python package, then a small web app), records a structured evidence
report, and asserts the DETERMINISTIC Twin mechanism effects (not model luck). Skips when
the model server is unreachable.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent.twin_control_plane.evaluation_harness import (
    build_report, default_conditions, run_condition, subprocess_validator,
)

BASE_URL = os.environ.get("FORGE_LOCAL_BASE_URL", "http://localhost:8080").rstrip("/")
MODEL_ID = os.environ.get("FORGE_LOCAL_MODEL", "Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf")

# Two evaluation projects (kept small so the local model can plausibly complete them).
PACKAGE_ITEMS = [
    {"item_id": "store", "title": "persistence", "target_files": ["store.py"],
     "goal": "Create store.py with save(path, value) writing value to the file and "
             "load(path) returning the file contents."},
]
WEBAPP_ITEMS = [
    {"item_id": "api", "title": "fastapi endpoint", "target_files": ["app_server.py"],
     "goal": "Create app_server.py using FastAPI: a create_app() factory returning a "
             "FastAPI app with a GET /health route returning JSON {'status': 'ok'}."},
]

# Content-validity checks: run the generated code and assert it actually works.
PACKAGE_VALIDATOR = subprocess_validator(
    "from store import save, load\n"
    "import os, tempfile\n"
    "p = os.path.join(tempfile.mkdtemp(), 'd.txt')\n"
    "save(p, 'hello')\n"
    "assert load(p) == 'hello'\n"
    "print('VALID')\n")
WEBAPP_VALIDATOR = subprocess_validator(
    "from app_server import create_app\n"
    "from fastapi.testclient import TestClient\n"
    "c = TestClient(create_app())\n"
    "r = c.get('/health')\n"
    "assert r.status_code == 200 and r.json() == {'status': 'ok'}\n"
    "print('VALID')\n")


def _adapter():
    from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
    return AtlasLLMJsonAdapter(base_url=BASE_URL, model=MODEL_ID)


def _model_up() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(f"{BASE_URL}/v1/models", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _evaluate_project(tmp_path: Path, name: str, items: list[dict], validator) -> dict:
    adapter = _adapter()
    records = []
    for idx, condition in enumerate(default_conditions(MODEL_ID)):
        root = tmp_path / f"{name}_{idx}_{condition.name}"
        root.mkdir(parents=True, exist_ok=True)
        rec = run_condition(
            adapter=adapter, root=root, condition=condition, validator=validator,
            pool_id=f"{name}_pool", project_path=str(root / "proj"), items=items)
        records.append(rec)
    report = build_report(name, records)
    out_dir = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "ca_data")) / "twin_control_plane" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _assert_twin_effects(report: dict):
    s = report["summary"]
    # The evaluation actually exercises patch generation, verification, Twin injection,
    # the post-apply gate, and the repair loop.
    cov = s["pipeline_coverage"]
    assert cov["generation_attempted"] is True
    assert cov["verification_recorded"] is True
    assert cov["twin_instruction_injected"] is True
    assert cov["post_apply_gate_ran"] is True
    assert cov["repair_guidance_produced"] is True
    # Generated content validity is checked (the run executes the produced code). We do not
    # require the local model to always succeed, but the validity check must have run and
    # the report must record per-condition validity counts.
    assert cov["content_validity_checked"] is True
    assert isinstance(s["content_validity"], dict) and s["content_validity"]
    inj = s["twin_injection_verified"]
    # Twin injection happens where needed in ACTIVE, and not in OFF (genuine, not vacuous).
    assert inj["active_gates_present"] is True
    assert inj["active_instruction_injected"] is True
    assert inj["active_post_apply_ran"] is True
    assert inj["off_no_instruction"] is True
    assert inj["off_not_engaged"] is True
    # ACTIVE adds required gates that OFF does not.
    assert s["active_vs_off"]["instruction_only_in_active"] is True
    assert s["active_vs_off"]["gate_count_delta"] >= 1
    # A weak capability profile raises at least as many gates as a strong one.
    weak = s["profile_effect"]["weak_gate_count"]
    strong = s["profile_effect"]["strong_gate_count"]
    if weak is not None and strong is not None:
        assert weak >= strong
    # The re-run with an in-run-built Twin makes impact evidence available on the 2nd run.
    rerun = s["rerun_twin_effect"]
    if rerun:
        assert rerun["impact_became_available_on_rerun"] is True


@pytest.mark.real_model
def test_real_evaluation_python_package(tmp_path):
    if not _model_up():
        pytest.skip(f"no local model server reachable at {BASE_URL}")
    report = _evaluate_project(tmp_path, "python_package", PACKAGE_ITEMS, PACKAGE_VALIDATOR)
    _assert_twin_effects(report)


@pytest.mark.real_model
def test_real_evaluation_web_app(tmp_path):
    if not _model_up():
        pytest.skip(f"no local model server reachable at {BASE_URL}")
    report = _evaluate_project(tmp_path, "web_app", WEBAPP_ITEMS, WEBAPP_VALIDATOR)
    _assert_twin_effects(report)
