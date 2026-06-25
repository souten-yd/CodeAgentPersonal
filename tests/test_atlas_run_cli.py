from __future__ import annotations

import io
from pathlib import Path

from scripts import atlas_run_cli


class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        self.calls.append((method, path, payload))
        if path.endswith("/events?after_sequence=0"):
            return {"run_id": "run_1", "events": [{"sequence": 1, "event_type": "run_created"}], "next_after_sequence": 1}
        if path.endswith("/status"):
            return {"run_id": "run_1", "status": "completed", "terminal": True}
        return {"ok": True, "method": method, "path": path, "payload": payload or {}}


def _run(argv: list[str]) -> tuple[FakeClient, str]:
    client = FakeClient()
    stdout = io.StringIO()
    assert atlas_run_cli.run_cli(argv, client=client, stdout=stdout) == 0
    return client, stdout.getvalue()


def test_cli_start_uses_run_api_only() -> None:
    client, output = _run(["start", "--pool-id", "pool_1", "--item-ids", "item_1,item_2", "--mode", "resume"])

    assert client.calls == [
        (
            "POST",
            "/api/atlas/runs",
            {
                "pool_id": "pool_1",
                "workspace_id": "default",
                "item_id": "",
                "item_ids": ["item_1", "item_2"],
                "mode": "resume",
                "preset_id": "guarded_low_risk",
                "command_id": "",
                "auto_start": True,
            },
        )
    ]
    assert '"ok": true' in output


def test_cli_watch_resumes_from_event_cursor_once() -> None:
    client, output = _run(["watch", "run_1", "--once"])

    assert client.calls == [("GET", "/api/atlas/runs/run_1/events?after_sequence=0", None)]
    assert "run_created" in output


def test_cli_decision_cancel_and_retry_use_run_api_only() -> None:
    client, _ = _run(["decision", "run_1", "--decision", "approved", "--item-id", "item_1"])
    client2, _ = _run(["cancel", "run_1", "--reason", "stop"])
    client3, _ = _run(["retry", "run_1", "--reason", "again"])

    assert client.calls[0][1] == "/api/atlas/runs/run_1/decisions"
    assert client2.calls[0][1] == "/api/atlas/runs/run_1/cancel"
    assert client3.calls[0][1] == "/api/atlas/runs/run_1/retry"


def test_cli_plan_and_pool_views_use_planpool_api() -> None:
    client, _ = _run(["plan", "--input", "build feature", "--sync"])
    client2, _ = _run(["pools-list"])
    client3, _ = _run(["pool-show", "pool_1"])

    assert client.calls[0][1] == "/api/atlas/plan-pools?sync=1"
    assert client2.calls[0][1] == "/api/atlas/plan-pools"
    assert client3.calls[0][1] == "/api/atlas/plan-pools/pool_1"


def test_cli_does_not_call_direct_patch_apply_or_verify_endpoints() -> None:
    source = Path("scripts/atlas_run_cli.py").read_text(encoding="utf-8")

    forbidden = [
        "/api/atlas/patch-proposals/generate",
        "/api/atlas/patch-proposals/decide",
        "/api/atlas/automation/safe-apply-one",
        "/api/atlas/automation/safe-apply-one-and-verify",
        "/api/atlas/multi-item-autopilot/run",
    ]
    for endpoint in forbidden:
        assert endpoint not in source
