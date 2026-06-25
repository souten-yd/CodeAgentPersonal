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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live CS15 Atlas Run control hardening validation.")
    parser.add_argument("--output-json", type=Path, default=REPO_ROOT / "ca_data" / "atlas_run_control_hardening_eval" / "cs15_live_eval.json")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    report = run_eval(output_json=args.output_json, timeout=args.timeout)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
