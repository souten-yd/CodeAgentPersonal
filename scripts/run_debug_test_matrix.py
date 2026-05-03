#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
CA_DATA_DIR = Path(os.environ.get("CODEAGENT_CA_DATA_DIR", "/workspace/ca_data" if Path('/workspace').exists() else str(REPO_ROOT / "ca_data"))).resolve()
DEBUG_RUN_ROOT = CA_DATA_DIR / "debug_test_runs"


@dataclass(frozen=True)
class TestPreset:
    id: str
    title: str
    description: str
    command: list[str]
    env: dict[str, str]
    timeout_sec: int = 300


SMOKE_ENV_KEYS = [
    "PLAYWRIGHT_SMOKE_BASE_URL",
    "RUN_ATLAS_BACKEND_PREFLIGHT",
    "RUN_ATLAS_BACKEND_E2E",
    "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN",
    "RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION",
    "RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL",
    "RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL_ACTIONABLE",
    "PLAYWRIGHT_SMOKE_ARTIFACT_DIR",
]

TEST_PRESETS: list[TestPreset] = [
    TestPreset("static_contracts", "Static contract tests", "Representative phase contract tests", [sys.executable, "-m", "unittest", "tests.test_phase29_0_plan_approval_gate_readiness_contract", "tests.test_phase29_0c_plan_approval_invalid_selector_guard_contract", "tests.test_phase29_1_plan_approval_actionability_contract"], {}, 300),
    TestPreset("ui_9of9_mock", "UI smoke 9/9 (mock)", "Run non-destructive UI smoke with mocked backend", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "", "RUN_ATLAS_BACKEND_PREFLIGHT": "0", "RUN_ATLAS_BACKEND_E2E": "0"}, 600),
    TestPreset("backend_preflight", "Backend preflight only", "Smoke with backend preflight only", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1"}, 600),
    TestPreset("backend_e2e_dry_run", "Backend E2E dry run", "E2E flow without destructive actions", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1"}, 900),
    TestPreset("wait_plan", "Wait plan", "Wait-plan gate path", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1", "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN": "1"}, 900),
    TestPreset("clarification_resolution", "Clarification resolution", "Resolve clarification path", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1", "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN": "1", "RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION": "1"}, 900),
    TestPreset("plan_approval_gate", "Plan approval gate", "Validate gate visibility path", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1", "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN": "1", "RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL": "1"}, 900),
    TestPreset("plan_approval_actionability", "Plan approval actionability", "Validate actionable plan approval path (may fail)", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1", "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN": "1", "RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL": "1", "RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL_ACTIONABLE": "1"}, 900),
]


def _write_summary(run_dir: Path, payload: dict[str, Any]) -> None:
    lines = [f"# Debug Test Matrix {payload['run_id']}", "", f"- status: **{payload.get('status', 'unknown')}**", f"- total: {payload.get('total', 0)} pass: {payload.get('passed', 0)} fail: {payload.get('failed', 0)} skip: {payload.get('skipped', 0)} timeout: {payload.get('timeout', 0)}", ""]
    if payload.get("current_test"):
        lines.extend([f"- current_test: {payload['current_test']}", ""])
    lines.extend(["| id | status | exit | duration |", "|---|---:|---:|---:|"])
    for row in payload.get("results", []):
        lines.append(f"| {row['id']} | {row['status']} | {row['exit_code']} | {row['duration_sec']}s |")
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_progress(run_dir: Path, payload: dict[str, Any]) -> None:
    (run_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary(run_dir, payload)


def run_all_presets(run_id: str) -> dict[str, Any]:
    run_dir = DEBUG_RUN_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    payload: dict[str, Any] = {"run_id": run_id, "status": "running", "current_test": None, "started_at": datetime.now(timezone.utc).isoformat(), "results": [], "total": 0, "passed": 0, "failed": 0, "skipped": 0, "timeout": 0}
    _write_progress(run_dir, payload)
    for preset in TEST_PRESETS:
        payload["current_test"] = preset.id
        _write_progress(run_dir, payload)
        test_dir = run_dir / preset.id
        test_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir = test_dir / "artifacts" / "playwright"
        env = os.environ.copy()
        for key in SMOKE_ENV_KEYS:
            env.pop(key, None)
        env.update(preset.env)
        env["PLAYWRIGHT_SMOKE_ARTIFACT_DIR"] = str(artifact_dir)
        t0 = time.time()
        status = "passed"
        code = 0
        out = ""
        err = ""
        try:
            proc = subprocess.run(preset.command, cwd=str(REPO_ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=preset.timeout_sec)
            code = int(proc.returncode)
            out = proc.stdout or ""
            err = proc.stderr or ""
            combined = f"{out}\n{err}"
            if "SKIP: playwright is not installed" in combined or "SKIP:" in combined:
                status = "skipped"
            elif code != 0:
                status = "failed"
        except subprocess.TimeoutExpired as exc:
            status = "timeout"
            code = -1
            out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            err = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        (test_dir / "stdout.log").write_text(out, encoding="utf-8", errors="replace")
        (test_dir / "stderr.log").write_text(err, encoding="utf-8", errors="replace")
        payload["results"].append({"id": preset.id, "title": preset.title, "status": status, "exit_code": code, "duration_sec": round(time.time() - t0, 3), "stdout_tail": "\n".join(out.splitlines()[-20:]), "stderr_tail": "\n".join(err.splitlines()[-20:]), "artifact_path": str(artifact_dir)})
        failed = sum(1 for r in payload["results"] if r["status"] == "failed")
        skipped = sum(1 for r in payload["results"] if r["status"] == "skipped")
        timeout = sum(1 for r in payload["results"] if r["status"] == "timeout")
        payload["total"] = len(payload["results"])
        payload["passed"] = sum(1 for r in payload["results"] if r["status"] == "passed")
        payload["failed"] = failed
        payload["skipped"] = skipped
        payload["timeout"] = timeout
        _write_progress(run_dir, payload)

    failed = sum(1 for r in payload["results"] if r["status"] == "failed")
    skipped = sum(1 for r in payload["results"] if r["status"] == "skipped")
    timeout = sum(1 for r in payload["results"] if r["status"] == "timeout")
    payload["total"] = len(payload["results"])
    payload["passed"] = sum(1 for r in payload["results"] if r["status"] == "passed")
    payload["failed"] = failed
    payload["skipped"] = skipped
    payload["timeout"] = timeout
    if failed > 0:
        payload["status"] = "finished_with_failures"
    elif skipped > 0:
        payload["status"] = "finished_with_skips"
    else:
        payload["status"] = "passed"
    payload["current_test"] = None
    payload["finished_at"] = datetime.now(timezone.utc).isoformat()
    payload["duration_sec"] = round(time.time() - started, 3)
    _write_progress(run_dir, payload)
    return payload
