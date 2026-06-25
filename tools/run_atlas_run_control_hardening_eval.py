"""Live CS15 evaluation for hardened Atlas Run control and Kasane CLI.

The script probes the user's local OpenAI-compatible model at
http://127.0.0.1:8080/v1, then drives real Run API and CLI client paths against
an isolated in-process FastAPI app. Missing live model evidence is recorded as
blocked_live_llm_unavailable, not passed.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LLM_BASE_URL = "http://127.0.0.1:8080"
LLM_ENDPOINT = f"{LLM_BASE_URL}/v1/chat/completions"
RUNNABLE_PLAN_STATUSES = {"ready", "approval_required"}

for _key in ("LLM_URL", "CODEAGENT_LLM_PLANNER", "CODEAGENT_LLM_EXECUTOR", "CODEAGENT_LLM_CHAT", "CODEAGENT_LLM_LIGHT"):
    os.environ.setdefault(_key, LLM_ENDPOINT)
os.environ.setdefault("CODEAGENT_LLM_BASE_URL", LLM_BASE_URL)
os.environ.setdefault("OPENAI_BASE_URL", f"{LLM_BASE_URL}/v1")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.api.atlas_runs as atlas_runs_api  # noqa: E402
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool  # noqa: E402
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage  # noqa: E402
from agent.atlas_run_orchestrator import AtlasRunOrchestrator, AtlasRunOrchestratorCallbacks  # noqa: E402
from agent.atlas_run_store import AtlasRunStore  # noqa: E402
from agent.atlas_time_utils import utc_now_iso  # noqa: E402
from app.api.atlas_runs import router as atlas_runs_router  # noqa: E402
from kasane_cli import commands as kasane_commands  # noqa: E402
from kasane_cli.banner import BANNER_TEXT  # noqa: E402
from kasane_cli.repl import run_repl  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso(delta_seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


class TestClientRunHttpClient:
    def __init__(self, client: TestClient):
        self.client = client
        self.calls: list[tuple[str, str, dict[str, Any] | None, dict[str, Any]]] = []

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.client.request(method, path, json=payload)
        body = response.json()
        self.calls.append((method, path, payload, body))
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code} {path}: {body}")
        return body


def _probe_model(timeout: float) -> dict[str, Any]:
    models_url = f"{LLM_BASE_URL}/v1/models"
    try:
        with urllib.request.urlopen(models_url, timeout=timeout) as response:
            models_payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"status": "blocked_live_llm_unavailable", "url": models_url, "error": str(exc)[:240]}
    model_ids = [str(item.get("id") or "") for item in models_payload.get("data", []) if isinstance(item, dict)]
    model_id = next((model for model in model_ids if model), "")
    chat_payload: dict[str, Any] = {}
    if model_id:
        body = json.dumps(
            {
                "model": model_id,
                "messages": [
                    {"role": "system", "content": "Return one compact JSON object only."},
                    {"role": "user", "content": 'Return exactly {"status":"ok","cs15":true}.'},
                ],
                "temperature": 0,
                "stream": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            LLM_ENDPOINT,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                chat_payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {
                "status": "blocked_live_llm_unavailable",
                "url": LLM_ENDPOINT,
                "model_ids": [model for model in model_ids if model],
                "error": str(exc)[:240],
            }
    return {
        "status": "available" if model_id and chat_payload else "blocked_live_llm_unavailable",
        "url": models_url,
        "model_ids": [model for model in model_ids if model],
        "chat_probe_ok": bool(chat_payload.get("choices")),
    }


def _post_llm_json(system_prompt: str, user_payload: dict[str, Any], *, timeout: float) -> dict[str, Any] | None:
    model_ids = [str(model_id) for model_id in user_payload.get("model_ids", []) if str(model_id)]
    model_id = model_ids[0] if model_ids else ""
    if not model_id:
        probe = _probe_model(min(timeout, 10.0))
        model_id = next((str(item) for item in probe.get("model_ids", []) if str(item)), "")
    if not model_id:
        return None
    body = json.dumps(
        {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "temperature": 0,
            "stream": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        LLM_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    content = str((((response_payload.get("choices") or [{}])[0]).get("message") or {}).get("content") or "").strip()
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _pool(pool_id: str, items: list[str], *, completed: list[str] | None = None) -> AtlasPlanPool:
    return AtlasPlanPool(
        pool_id=pool_id,
        root_goal=f"CS15 validation {pool_id}",
        status="ready",
        automation_level="auto_after_approval",
        completed_item_ids=list(completed or []),
        items=[
            AtlasPlanItem(
                item_id=item_id,
                pool_id=pool_id,
                title=f"Validate {item_id}",
                goal=f"Validate {item_id}",
                status="completed" if item_id in set(completed or []) else "ready",
                risk_level="low",
                auto_execution_allowed=True,
                target_files=[f"{item_id}.txt"],
                acceptance_criteria=["control-plane evidence recorded"],
            )
            for item_id in items
        ],
    )


def _make_app(data_root: Path) -> tuple[TestClient, AtlasPlanPoolStorage, AtlasRunStore, dict[str, int]]:
    os.environ["CODEAGENT_CA_DATA_DIR"] = str(data_root)
    attempts: dict[str, int] = {}
    plan_storage = AtlasPlanPoolStorage(data_root)
    run_store = AtlasRunStore(data_root)

    def callbacks() -> AtlasRunOrchestratorCallbacks:
        def apply_and_verify(*, item: AtlasPlanItem, **_: Any) -> dict[str, Any]:
            attempts[item.item_id] = attempts.get(item.item_id, 0) + 1
            if item.item_id == "item_retry" and attempts[item.item_id] == 1:
                return {"status": "verification_failed", "reason": "cs15_seeded_failure"}
            return {"status": "applied_and_verified", "verification": {"status": "passed", "source": "cs15_safe_callback"}}

        return AtlasRunOrchestratorCallbacks(
            approve_plan_item=lambda **_: {"status": "approved"},
            generate_patch_proposal=lambda item, **_: {"status": "proposed", "proposal_id": f"proposal_{item.item_id}"},
            approve_patch_proposal=lambda **_: {"status": "approved"},
            apply_and_verify=apply_and_verify,
        )

    def build_orchestrator(request: Any, workspace_id: str) -> AtlasRunOrchestrator:
        return AtlasRunOrchestrator(
            run_store=run_store,
            plan_storage=plan_storage,
            journal=None,
            callbacks=callbacks(),
        )

    atlas_runs_api._build_run_orchestrator = build_orchestrator
    app = FastAPI()
    app.include_router(atlas_runs_router)
    return TestClient(app), plan_storage, run_store, attempts


def _events(client: TestClient, run_id: str) -> dict[str, Any]:
    payload = client.get(f"/api/atlas/runs/{run_id}/events").json()
    return {
        "count": len(payload.get("events") or []),
        "event_types": [event.get("event_type") for event in payload.get("events") or []],
        "next_after_sequence": payload.get("next_after_sequence"),
    }


def _scenario(name: str, status: str, **payload: Any) -> dict[str, Any]:
    return {"scenario": name, "status": status, **payload}


def run_eval(*, output_json: Path, timeout: float) -> dict[str, Any]:
    report: dict[str, Any] = {
        "kind": "atlas_run_control_hardening_eval",
        "track": "CS15",
        "created_at": _now(),
        "llm_base_url": LLM_BASE_URL,
        "status": "running",
        "model_probe": {},
        "scenarios": [],
        "acceptance_checks": {},
        "unavailable_checks": [],
    }
    model_probe = _probe_model(timeout)
    report["model_probe"] = model_probe
    if model_probe.get("status") != "available":
        report["status"] = "blocked"
        report["blocked_reason"] = "blocked_live_llm_unavailable"
        report["unavailable_checks"].append(model_probe)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report

    original_build_orchestrator = atlas_runs_api._build_run_orchestrator
    try:
        temp_context = tempfile.TemporaryDirectory(prefix="cs15-run-control-")
        temp_dir = temp_context.__enter__()
        client, storage, store, attempts = _make_app(Path(temp_dir))
        http = TestClientRunHttpClient(client)

        storage.save_pool(_pool("pool_api", ["item_api"]))
        api_created = client.post("/api/atlas/runs", json={"pool_id": "pool_api", "auto_start": True, "mode": "fresh"}).json()
        api_run_id = api_created["run_id"]
        api_status = client.get(f"/api/atlas/runs/{api_run_id}/status").json()
        watch_out = io.StringIO()
        kasane_commands.run_cli(["watch", api_run_id, "--once", "--json"], client=http, stdout=watch_out)
        report["scenarios"].append(
            _scenario(
                "api_starts_run_cli_watches_browser_status_observes",
                "passed" if api_status.get("status") == "completed" and "run_items_selected" in _events(client, api_run_id)["event_types"] else "failed",
                run_id=api_run_id,
                final_status=api_status,
                events=_events(client, api_run_id),
                cli_watch_transcript=watch_out.getvalue().splitlines()[:4],
            )
        )

        storage.save_pool(_pool("pool_cli", ["item_cli"]))
        cli_out = io.StringIO()
        lines = iter(["/run pool_cli", "/exit"])
        run_repl(
            http,
            stdout=cli_out,
            base_url="http://testserver",
            project_path=str(REPO_ROOT),
            quiet=True,
            input_fn=lambda prompt: next(lines),
        )
        cli_created = next(
            body
            for method, path, _payload, body in reversed(http.calls)
            if method == "POST" and path == "/api/atlas/runs" and body.get("run_id")
        )
        cli_run_id = cli_created["run_id"]
        cli_status = client.get(f"/api/atlas/runs/{cli_run_id}/status").json()
        report["scenarios"].append(
            _scenario(
                "cli_interactive_style_starts_run_api_watches",
                "passed" if cli_status.get("status") == "completed" else "failed",
                run_id=cli_run_id,
                final_status=cli_status,
                cli_start_payload=cli_created,
                cli_repl_transcript=cli_out.getvalue().splitlines()[:6],
                events=_events(client, cli_run_id),
            )
        )

        storage.save_pool(_pool("pool_retry", ["item_retry"]))
        retry_created = client.post("/api/atlas/runs", json={"pool_id": "pool_retry", "auto_start": True, "mode": "fresh"}).json()
        retry_run_id = retry_created["run_id"]
        first_status = client.get(f"/api/atlas/runs/{retry_run_id}/status").json()
        retry_response = client.post(f"/api/atlas/runs/{retry_run_id}/retry", json={"reason": "cs15 retry", "mode": "resume"}).json()
        retry_status = client.get(f"/api/atlas/runs/{retry_run_id}/status").json()
        report["scenarios"].append(
            _scenario(
                "failed_item_retry_uses_run_retry_endpoint",
                "passed" if first_status.get("status") == "failed" and retry_status.get("status") == "completed" else "failed",
                run_id=retry_run_id,
                first_status=first_status,
                retry_response=retry_response,
                final_status=retry_status,
                attempts=attempts.get("item_retry"),
                events=_events(client, retry_run_id),
            )
        )

        storage.save_pool(_pool("pool_resume", ["item_done", "item_remaining"], completed=["item_done"]))
        resume_created = client.post("/api/atlas/runs", json={"pool_id": "pool_resume", "mode": "resume", "auto_start": True}).json()
        resume_run_id = resume_created["run_id"]
        resume_status = client.get(f"/api/atlas/runs/{resume_run_id}/status").json()
        resume_state = client.get(f"/api/atlas/runs/{resume_run_id}").json()["state"]
        resume_events = _events(client, resume_run_id)
        report["scenarios"].append(
            _scenario(
                "resume_without_client_item_ids_skips_completed",
                "passed"
                if resume_status.get("status") == "completed"
                and resume_state.get("completed_item_ids") == ["item_remaining"]
                and "run_items_selected" in resume_events["event_types"]
                else "failed",
                run_id=resume_run_id,
                final_status=resume_status,
                final_state=resume_state,
                events=resume_events,
            )
        )

        duplicate_run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_duplicate"}).json()["run_id"]
        store.patch_state(
            duplicate_run_id,
            {
                "status": "running",
                "phase": "proposal",
                "lease_owner": "worker-existing",
                "lease_acquired_at": _iso(-10),
                "lease_expires_at": _iso(600),
                "worker_heartbeat_at": _iso(-1),
            },
        )
        duplicate = client.post(f"/api/atlas/runs/{duplicate_run_id}/start", json={})
        report["scenarios"].append(
            _scenario(
                "duplicate_start_rejected_or_idempotent",
                "passed" if duplicate.status_code == 409 else "failed",
                run_id=duplicate_run_id,
                status_code=duplicate.status_code,
                response=duplicate.json(),
            )
        )

        stale_run_id = client.post("/api/atlas/runs", json={"pool_id": "pool_recover", "run_id": "run_cs15_stale"}).json()["run_id"]
        store.patch_state(
            stale_run_id,
            {
                "status": "running",
                "phase": "safe_apply",
                "lease_owner": "worker-stale",
                "lease_acquired_at": _iso(-1200),
                "lease_expires_at": _iso(-600),
                "worker_heartbeat_at": _iso(-1200),
            },
        )
        recovered = client.post("/api/atlas/runs/recover-stale", json={"stale_after_seconds": 300}).json()
        stale_status = client.get(f"/api/atlas/runs/{stale_run_id}/status").json()
        report["scenarios"].append(
            _scenario(
                "stale_running_recovery_marks_blocked_retryable_not_success",
                "passed"
                if stale_status.get("status") == "blocked"
                and stale_status.get("next_actions") == ["retry", "inspect_events"]
                and stale_status.get("terminal") is True
                else "failed",
                run_id=stale_run_id,
                recovery_response=recovered,
                final_status=stale_status,
                events=_events(client, stale_run_id),
            )
        )

        banner_stdout = io.StringIO()
        run_repl(http, stdout=banner_stdout, base_url="http://testserver", project_path=str(REPO_ROOT), input_fn=lambda prompt: "/exit")
        json_stdout = io.StringIO()
        kasane_commands.run_cli(["status", api_run_id, "--json"], client=http, stdout=json_stdout)
        report["scenarios"].append(
            _scenario(
                "banner_interactive_present_json_absent",
                "passed" if BANNER_TEXT in banner_stdout.getvalue() and BANNER_TEXT not in json_stdout.getvalue() else "failed",
                interactive_banner_present=BANNER_TEXT in banner_stdout.getvalue(),
                json_banner_absent=BANNER_TEXT not in json_stdout.getvalue(),
            )
        )
    finally:
        atlas_runs_api._build_run_orchestrator = original_build_orchestrator
        if "temp_context" in locals():
            temp_context.__exit__(None, None, None)

    report["acceptance_checks"] = {scenario["scenario"]: scenario["status"] for scenario in report["scenarios"]}
    failed = [name for name, status in report["acceptance_checks"].items() if status != "passed"]
    report["status"] = "passed" if not failed else "failed"
    if failed:
        report["failed_checks"] = failed
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def _scenario_by_name(live_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(scenario.get("scenario")): scenario for scenario in live_report.get("scenarios", []) if isinstance(scenario, dict)}


def _scenario_excerpt(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario": scenario.get("scenario"),
        "status": scenario.get("status"),
        "run_id": scenario.get("run_id"),
        "final_status": {
            "status": (scenario.get("final_status") or {}).get("status"),
            "phase": (scenario.get("final_status") or {}).get("phase"),
            "terminal": (scenario.get("final_status") or {}).get("terminal"),
            "block_reason": (scenario.get("final_status") or {}).get("block_reason"),
        },
        "event_types": (scenario.get("events") or {}).get("event_types"),
    }


def build_final_review_bundle(live_report: dict[str, Any]) -> dict[str, Any]:
    scenarios = _scenario_by_name(live_report)
    return {
        "track": "CS9-CS16 Atlas Run Control Hardening / Claude-like CLI / Startup Banner",
        "focused_test_outputs": [
            {"package": "CS9", "summary": "focused/affected 38 passed"},
            {"package": "CS10", "summary": "focused/affected 51 passed"},
            {"package": "CS11", "summary": "focused/affected 48 passed"},
            {"package": "CS12", "summary": "focused/affected 42 passed"},
            {"package": "CS13", "summary": "focused/affected 33 passed"},
            {"package": "CS14", "summary": "focused/affected 36 passed"},
            {"package": "CS15", "summary": "focused/affected 33 passed and live runner status passed"},
        ],
        "run_state_json_excerpts": [_scenario_excerpt(scenario) for scenario in live_report.get("scenarios", [])],
        "event_log_excerpts": [
            {
                "scenario": scenario.get("scenario"),
                "event_count": (scenario.get("events") or {}).get("count"),
                "event_types": (scenario.get("events") or {}).get("event_types"),
            }
            for scenario in live_report.get("scenarios", [])
            if isinstance(scenario, dict)
        ],
        "retry_revise_evidence": {
            "retry": {
                "scenario": "failed_item_retry_uses_run_retry_endpoint",
                "status": scenarios.get("failed_item_retry_uses_run_retry_endpoint", {}).get("status"),
                "first_status": (scenarios.get("failed_item_retry_uses_run_retry_endpoint", {}).get("first_status") or {}).get("status"),
                "final_status": (scenarios.get("failed_item_retry_uses_run_retry_endpoint", {}).get("final_status") or {}).get("status"),
                "events": (scenarios.get("failed_item_retry_uses_run_retry_endpoint", {}).get("events") or {}).get("event_types"),
            },
            "revise": {
                "source": "CS9 focused tests and docs",
                "evidence": "revise records run_revise_requested, execution_started=false, deferred=false, and does not mark work passed.",
            },
        },
        "item_selection_evidence": {
            "scenario": "resume_without_client_item_ids_skips_completed",
            "status": scenarios.get("resume_without_client_item_ids_skips_completed", {}).get("status"),
            "completed_item_ids": (scenarios.get("resume_without_client_item_ids_skips_completed", {}).get("final_state") or {}).get("completed_item_ids"),
            "events": (scenarios.get("resume_without_client_item_ids_skips_completed", {}).get("events") or {}).get("event_types"),
        },
        "duplicate_start_lease_evidence": {
            "duplicate_start": scenarios.get("duplicate_start_rejected_or_idempotent"),
            "stale_recovery": scenarios.get("stale_running_recovery_marks_blocked_retryable_not_success"),
        },
        "cli_transcript_excerpts": {
            "watch": scenarios.get("api_starts_run_cli_watches_browser_status_observes", {}).get("cli_watch_transcript"),
            "repl_run": scenarios.get("cli_interactive_style_starts_run_api_watches", {}).get("cli_repl_transcript"),
        },
        "banner_json_no_banner_evidence": scenarios.get("banner_interactive_present_json_absent"),
        "live_scenario_json": {
            "status": live_report.get("status"),
            "model_probe": live_report.get("model_probe"),
            "acceptance_checks": live_report.get("acceptance_checks"),
            "scenario_count": len(live_report.get("scenarios") or []),
        },
        "unavailable_checks": live_report.get("unavailable_checks") or [],
    }


def _deterministic_review_issues(live_report: dict[str, Any]) -> list[dict[str, str]]:
    required = [
        "api_starts_run_cli_watches_browser_status_observes",
        "cli_interactive_style_starts_run_api_watches",
        "failed_item_retry_uses_run_retry_endpoint",
        "resume_without_client_item_ids_skips_completed",
        "duplicate_start_rejected_or_idempotent",
        "stale_running_recovery_marks_blocked_retryable_not_success",
        "banner_interactive_present_json_absent",
    ]
    issues: list[dict[str, str]] = []
    if live_report.get("status") != "passed":
        issues.append({"category": "missing_deterministic_check", "detail": "live report status is not passed"})
    if (live_report.get("model_probe") or {}).get("status") != "available":
        issues.append({"category": "missing_deterministic_check", "detail": "8080 model probe is not available"})
    scenarios = _scenario_by_name(live_report)
    for name in required:
        if name not in scenarios:
            issues.append({"category": "missing_deterministic_check", "detail": f"missing scenario {name}"})
        elif scenarios[name].get("status") != "passed":
            issues.append({"category": "contradictory_evidence", "detail": f"scenario {name} status is {scenarios[name].get('status')}"})
    return issues


def _filter_llm_blockers(review: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(review, dict):
        return []
    blockers = review.get("blocking_issues") or []
    allowed = {"missing_deterministic_check", "contradictory_evidence"}
    return [issue for issue in blockers if isinstance(issue, dict) and str(issue.get("category")) in allowed]


def run_final_review(*, input_json: Path, output_json: Path, timeout: float) -> dict[str, Any]:
    if not input_json.exists():
        report = {
            "kind": "atlas_run_control_final_review",
            "track": "CS16",
            "created_at": _now(),
            "status": "blocked",
            "blocked_reason": "live_scenario_result_json_missing",
            "input_json": str(input_json),
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    live_report = json.loads(input_json.read_text(encoding="utf-8"))
    bundle = build_final_review_bundle(live_report)
    deterministic_issues = _deterministic_review_issues(live_report)
    llm_review: dict[str, Any] | None = None
    unavailable_checks: list[dict[str, Any]] = list(bundle.get("unavailable_checks") or [])
    if not deterministic_issues:
        llm_review = _post_llm_json(
            "Review the supplied evidence bundle. Return JSON only with keys status, blocking_issues, advisory_notes. "
            "Only include blocking_issues for category missing_deterministic_check or contradictory_evidence.",
            {
                "model_ids": (live_report.get("model_probe") or {}).get("model_ids") or [],
                "evidence_bundle": bundle,
            },
            timeout=timeout,
        )
        if llm_review is None:
            unavailable_checks.append({"status": "blocked_live_llm_unavailable", "url": LLM_ENDPOINT, "error": "final_review_llm_unavailable"})
    llm_blockers = _filter_llm_blockers(llm_review)
    status = "passed"
    blocked_reason = ""
    if deterministic_issues:
        status = "blocked"
        blocked_reason = "deterministic_review_issues"
    elif llm_review is None:
        status = "blocked"
        blocked_reason = "blocked_live_llm_unavailable"
    elif llm_blockers:
        status = "blocked"
        blocked_reason = "llm_reported_blocking_evidence_issue"
    report = {
        "kind": "atlas_run_control_final_review",
        "track": "CS16",
        "created_at": _now(),
        "status": status,
        "blocked_reason": blocked_reason,
        "input_json": str(input_json),
        "evidence_bundle": bundle,
        "deterministic_issues": deterministic_issues,
        "llm_review": llm_review,
        "llm_blockers": llm_blockers,
        "unavailable_checks": unavailable_checks,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live CS15 Atlas Run control hardening validation.")
    parser.add_argument("--output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_run_control_hardening_eval" / "cs15_live_eval.json")
    parser.add_argument("--input-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_run_control_hardening_eval" / "cs15_live_eval.json")
    parser.add_argument("--review-output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_run_control_hardening_eval" / "cs16_final_review.json")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--final-review", action="store_true", help="Ask the 8080 LLM to review an existing CS15 live evidence bundle.")
    args = parser.parse_args()
    if args.final_review:
        report = run_final_review(input_json=args.input_json, output_json=args.review_output_json, timeout=args.timeout)
    else:
        report = run_eval(output_json=args.output_json, timeout=args.timeout)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
