#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
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
    "PLAYWRIGHT_SMOKE_ONLY",
]

TEST_PRESETS: list[TestPreset] = [
    TestPreset("static_contracts", "Static contract tests", "Representative phase contract tests", [sys.executable, "-m", "unittest", "tests.test_phase30_0_debug_test_harness_contract", "tests.test_phase29_0_plan_approval_gate_readiness_contract", "tests.test_phase29_0c_plan_approval_invalid_selector_guard_contract", "tests.test_phase29_1_plan_approval_actionability_contract", "tests.test_phase31_2_atlas_mobile_ui_cleanup_contract", "tests.test_phase31_3_atlas_workflow_lifecycle_contract"], {}, 300),
    TestPreset("atlas_current_ui_smoke", "Atlas current UI smoke", "Current mobile-first Atlas UI smoke with mocked backend", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "", "RUN_ATLAS_BACKEND_PREFLIGHT": "0", "RUN_ATLAS_BACKEND_E2E": "0", "PLAYWRIGHT_SMOKE_ONLY": "atlas_current_ui_smoke"}, 600),
    TestPreset("nexus_current_ui_smoke", "Nexus current UI smoke", "Current Nexus UI smoke with dashboard exclusivity checks", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "", "RUN_ATLAS_BACKEND_PREFLIGHT": "0", "RUN_ATLAS_BACKEND_E2E": "0", "PLAYWRIGHT_SMOKE_ONLY": "nexus_current_ui_smoke"}, 600),
    TestPreset("backend_preflight", "Backend preflight only", "Smoke with backend preflight only", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1"}, 600),
    TestPreset("backend_e2e_dry_run", "Backend E2E dry run", "E2E flow without destructive actions", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1"}, 900),
    TestPreset("atlas_plan_api_contract", "Atlas plan API contract", "Direct API contract checks for /api/task/plan", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "PLAYWRIGHT_SMOKE_ONLY": "atlas_plan_api_contract"}, 600),
    TestPreset("wait_plan", "Wait plan", "Wait-plan gate path", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1", "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN": "1"}, 900),
    TestPreset("clarification_resolution", "Clarification resolution", "Resolve clarification path", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1", "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN": "1", "RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION": "1"}, 900),
    TestPreset("plan_approval_gate", "Plan approval gate", "Validate gate visibility path", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1", "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN": "1", "RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL": "1"}, 900),
    TestPreset("plan_approval_actionability", "Plan approval actionability", "Validate actionable plan approval path (may fail)", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1", "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN": "1", "RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL": "1", "RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL_ACTIONABLE": "1"}, 900),
]

LEGACY_TEST_PRESETS: list[TestPreset] = [
    TestPreset("legacy_ui_9of9_mock", "Legacy UI smoke 9/9 (mock, informational)", "Legacy compatibility UI smoke; not default acceptance for current Atlas UI", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "", "RUN_ATLAS_BACKEND_PREFLIGHT": "0", "RUN_ATLAS_BACKEND_E2E": "0"}, 600),
    TestPreset("wait_plan_live_llm", "Wait plan (live LLM diagnostic)", "Diagnostic scenario that may return clarification", [sys.executable, "scripts/smoke_ui_modes_playwright.py"], {"PLAYWRIGHT_SMOKE_BASE_URL": "http://127.0.0.1:8000", "RUN_ATLAS_BACKEND_PREFLIGHT": "1", "RUN_ATLAS_BACKEND_E2E": "1", "RUN_ATLAS_BACKEND_E2E_WAIT_PLAN": "1", "PLAYWRIGHT_SMOKE_ONLY": "atlas_backend_e2e_wait_plan_live_llm"}, 900),
]


_SMOKE_MODULE_CACHE = None


def _load_smoke_module() -> Any:
    global _SMOKE_MODULE_CACHE
    if _SMOKE_MODULE_CACHE is not None:
        return _SMOKE_MODULE_CACHE

    scripts_dir = (REPO_ROOT / "scripts").resolve()
    smoke_path = scripts_dir / "smoke_ui_modes_playwright.py"

    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    spec = importlib.util.spec_from_file_location(
        "codeagent_smoke_ui_modes_playwright",
        smoke_path,
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"matrix_preflight_failed: cannot load smoke module from {smoke_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _SMOKE_MODULE_CACHE = module
    return module


def _markdown_cell(value: Any, *, limit: int = 220) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    text = text.replace("|", "\\|")
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _compact_tail(output: str, *, max_lines: int = 8, max_chars: int = 1600) -> str:
    lines = output.splitlines()[-max_lines:]
    tail = "\n".join(lines)
    if len(tail) > max_chars:
        tail = "…" + tail[-max_chars:]
    return tail


def _error_summary(stdout: str, stderr: str, status: str) -> str:
    raw_lines = f"{stderr}\n{stdout}".splitlines()
    combined_lines = [line.rstrip() for line in raw_lines if line.strip()]
    for idx, line in enumerate(raw_lines):
        stripped = line.strip()
        if stripped.startswith("FAIL: ") or stripped.startswith("ERROR: "):
            snippet = raw_lines[idx:idx + 8]
            return _markdown_cell("\n".join(snippet), limit=800)
    for idx, line in enumerate(raw_lines):
        if "AssertionError" in line:
            lo = max(0, idx - 2)
            hi = min(len(raw_lines), idx + 3)
            return _markdown_cell("\n".join(raw_lines[lo:hi]), limit=800)
    for idx, line in enumerate(raw_lines):
        if line.strip().startswith("Traceback"):
            hi = min(len(raw_lines), idx + 10)
            return _markdown_cell("\n".join(raw_lines[idx:hi]), limit=800)
    priority_markers = ("TimeoutError", "Error:", "FAIL", "Traceback", "SMOKE_STATUS")
    for line in reversed(combined_lines):
        if any(marker in line for marker in priority_markers):
            return _markdown_cell(line, limit=300)
    if status == "passed":
        return ""
    return _markdown_cell(combined_lines[-1] if combined_lines else status, limit=300)


def _write_summary(run_dir: Path, payload: dict[str, Any]) -> None:
    lines = [f"# Debug Test Matrix {payload['run_id']}", "", f"- status: **{payload.get('status', 'unknown')}**", f"- total: {payload.get('total', 0)} pass: {payload.get('passed', 0)} fail: {payload.get('failed', 0)} skip: {payload.get('skipped', 0)} timeout: {payload.get('timeout', 0)}", ""]
    if payload.get("current_test"):
        lines.extend([f"- current_test: {payload['current_test']}", ""])
    lines.extend(["| id | status | exit | duration | error summary | artifact path | logs |", "|---|---:|---:|---:|---|---|---|"])
    for row in payload.get("results", []):
        log_paths = f"stdout: {row.get('stdout_log_path', '')}<br>stderr: {row.get('stderr_log_path', '')}"
        lines.append(f"| {row['id']} | {row['status']} | {row['exit_code']} | {row['duration_sec']}s | {_markdown_cell(row.get('error_summary'))} | {_markdown_cell(row.get('artifact_path'), limit=260)} | {_markdown_cell(log_paths, limit=360)} |")
    (run_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_progress(run_dir: Path, payload: dict[str, Any]) -> None:
    (run_dir / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_summary(run_dir, payload)

def _looks_like_full_skip(output: str) -> bool:
    skip_markers = (
        "SMOKE_STATUS: SKIPPED",
        "SKIP: playwright is not installed",
        "SKIP: browser dependency missing",
        "SKIP: no scenarios selected",
    )
    return any(marker in output for marker in skip_markers)


def _refresh_counts_and_status(payload: dict[str, Any], *, final: bool = False) -> None:
    results = payload.get("results", [])
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    timeout = sum(1 for r in results if r["status"] == "timeout")
    payload["total"] = len(results)
    payload["passed"] = sum(1 for r in results if r["status"] == "passed")
    payload["failed"] = failed
    payload["skipped"] = skipped
    payload["timeout"] = timeout

    if not final:
        return

    if failed > 0 or timeout > 0:
        payload["status"] = "finished_with_failures"
    elif skipped > 0:
        payload["status"] = "finished_with_skips"
    else:
        payload["status"] = "passed"




def _run_preflight_checks(run_dir: Path) -> dict[str, Any]:
    preflight_cmd = [sys.executable, "-c", "import main; print('main import ok')"]
    proc = subprocess.run(
        preflight_cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout_log_path = run_dir / "preflight_stdout.log"
    stderr_log_path = run_dir / "preflight_stderr.log"
    stdout_log_path.write_text(proc.stdout or "", encoding="utf-8", errors="replace")
    stderr_log_path.write_text(proc.stderr or "", encoding="utf-8", errors="replace")
    return {
        "command": " ".join(preflight_cmd),
        "exit_code": int(proc.returncode),
        "stdout_log_path": str(stdout_log_path),
        "stderr_log_path": str(stderr_log_path),
    }



def _load_smoke_registry() -> set[str]:
    proc = subprocess.run(
        [sys.executable, "scripts/smoke_ui_modes_playwright.py", "--list-scenarios"],
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"matrix_preflight_failed: smoke --list-scenarios failed: {proc.stderr.strip() or proc.stdout.strip()}")
    payload = json.loads(proc.stdout)
    return {item.get("id", "") for item in payload.get("scenarios", []) if isinstance(item, dict)}


def _validate_smoke_only_presets(registry: set[str]) -> None:
    missing: dict[str, str] = {}
    for preset in TEST_PRESETS:
        scenario = preset.env.get("PLAYWRIGHT_SMOKE_ONLY", "").strip()
        if scenario and scenario not in registry:
            missing[preset.id] = scenario
    if missing:
        raise AssertionError(f"matrix_preflight_failed: PLAYWRIGHT_SMOKE_ONLY not in smoke registry: {missing}")


def _validate_resolved_smoke_scenarios(registry: set[str]) -> None:
    smoke = _load_smoke_module()

    scenario_runners = {name: spec.fn for name, spec in smoke.SMOKE_SCENARIOS.items()}
    required_presets = {"atlas_plan_api_contract", "backend_preflight", "plan_approval_actionability"}
    for preset in TEST_PRESETS:
        if preset.id not in required_presets:
            continue
        only = [item.strip() for item in preset.env.get("PLAYWRIGHT_SMOKE_ONLY", "").split(",") if item.strip()]
        run_backend_preflight_opt_in = preset.env.get("RUN_ATLAS_BACKEND_PREFLIGHT", "").strip() == "1"
        run_backend_e2e_opt_in = preset.env.get("RUN_ATLAS_BACKEND_E2E", "").strip() == "1"
        preflight_only_mode = run_backend_preflight_opt_in and not run_backend_e2e_opt_in
        selected = smoke.resolve_smoke_scenarios(
            only=only,
            preflight_only_mode=preflight_only_mode,
            run_backend_e2e=run_backend_e2e_opt_in,
            run_wait_plan=preset.env.get("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN", "").strip() == "1",
            run_resolve_clarification=preset.env.get("RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION", "").strip() == "1",
            run_check_plan_approval=preset.env.get("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL", "").strip() == "1",
            run_check_plan_approval_actionable=preset.env.get("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL_ACTIONABLE", "").strip() == "1",
        )
        missing_registry = [item for item in selected if item not in registry]
        missing_runners = [item for item in selected if item not in scenario_runners]
        if missing_registry or missing_runners:
            raise AssertionError(
                f"matrix_preflight_failed: preset={preset.id} resolved non-executable scenarios: "
                f"missing_registry={missing_registry} missing_runners={missing_runners}"
            )

def run_all_presets(run_id: str) -> dict[str, Any]:
    run_dir = DEBUG_RUN_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    payload: dict[str, Any] = {"run_id": run_id, "status": "running", "current_test": None, "started_at": datetime.now(timezone.utc).isoformat(), "results": [], "total": 0, "passed": 0, "failed": 0, "skipped": 0, "timeout": 0}
    preflight = _run_preflight_checks(run_dir)
    payload["preflight"] = preflight
    if preflight["exit_code"] != 0:
        payload["status"] = "preflight_failed"
        payload["current_test"] = None
        payload["finished_at"] = datetime.now(timezone.utc).isoformat()
        payload["duration_sec"] = round(time.time() - started, 3)
        _write_progress(run_dir, payload)
        return payload
    _write_progress(run_dir, payload)
    try:
        smoke_registry = _load_smoke_registry()
        _validate_smoke_only_presets(smoke_registry)
        _validate_resolved_smoke_scenarios(smoke_registry)
    except Exception as exc:
        import traceback

        payload["status"] = "matrix_preflight_failed"
        payload["current_test"] = None
        payload["finished_at"] = datetime.now(timezone.utc).isoformat()
        payload["duration_sec"] = round(time.time() - started, 3)
        payload["preflight_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        _write_progress(run_dir, payload)
        return payload
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
            if code != 0:
                status = "failed"
            elif _looks_like_full_skip(combined):
                status = "skipped"
        except subprocess.TimeoutExpired as exc:
            status = "timeout"
            code = -1
            out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            err = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        stdout_log_path = test_dir / "stdout.log"
        stderr_log_path = test_dir / "stderr.log"
        stdout_log_path.write_text(out, encoding="utf-8", errors="replace")
        stderr_log_path.write_text(err, encoding="utf-8", errors="replace")
        payload["results"].append({"id": preset.id, "title": preset.title, "status": status, "exit_code": code, "duration_sec": round(time.time() - t0, 3), "error_summary": _error_summary(out, err, status), "stdout_tail": _compact_tail(out), "stderr_tail": _compact_tail(err), "stdout_log_path": str(stdout_log_path), "stderr_log_path": str(stderr_log_path), "artifact_path": str(artifact_dir)})
        _refresh_counts_and_status(payload)
        _write_progress(run_dir, payload)

    _refresh_counts_and_status(payload, final=True)
    payload["current_test"] = None
    payload["finished_at"] = datetime.now(timezone.utc).isoformat()
    payload["duration_sec"] = round(time.time() - started, 3)
    _write_progress(run_dir, payload)
    return payload
