from __future__ import annotations

import io
from pathlib import Path

from kasane_cli import commands
from kasane_cli.repl import run_repl


class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        self.calls.append((method, path, payload))
        if path == "/api/system/status":
            return {"model": "local-test-model"}
        if path.endswith("/events?after_sequence=0"):
            return {"run_id": "run_1", "events": [{"sequence": 1, "event_type": "run_created"}], "next_after_sequence": 1}
        if path.endswith("/status"):
            return {"run_id": "run_1", "status": "completed", "phase": "final_summary", "terminal": True}
        if path == "/api/atlas/plan-pools?sync=1":
            return {"pool_id": "pool_1", "ok": True}
        if path == "/api/atlas/runs":
            return {"run_id": "run_1", "ok": True, "payload": payload or {}}
        return {"ok": True, "method": method, "path": path, "payload": payload or {}}


def test_module_help_works_without_banner(capsys) -> None:
    try:
        commands.run_cli(["--help"], client=FakeClient())
    except SystemExit as exc:
        assert exc.code == 0
    output = capsys.readouterr().out
    assert "KasaneCore Atlas CLI" in output
    assert "Atlas * Portal" not in output


def test_status_json_is_machine_readable_and_banner_free() -> None:
    client = FakeClient()
    stdout = io.StringIO()

    assert commands.run_cli(["status", "--json"], client=client, stdout=stdout) == 0

    output = stdout.getvalue()
    assert "local-test-model" in output
    assert "Atlas * Portal" not in output
    assert client.calls == [("GET", "/api/system/status", None)]


def test_interactive_slash_commands_use_run_api() -> None:
    client = FakeClient()
    stdout = io.StringIO()
    lines = iter(["/plan build app", "/run pool_1", "/retry run_1", "/revise run_1 smaller", "/cancel run_1", "/exit"])

    rc = run_repl(
        client,
        stdout=stdout,
        base_url="http://127.0.0.1:8000",
        project_path=".",
        input_fn=lambda prompt: next(lines),
    )

    assert rc == 0
    assert ("POST", "/api/atlas/plan-pools?sync=1", {"input": "build app", "project_path": str(Path(".").resolve()), "workspace_id": "default"}) in client.calls
    assert ("POST", "/api/atlas/runs", {"pool_id": "pool_1", "mode": "fresh", "auto_start": True}) in client.calls
    assert ("POST", "/api/atlas/runs/run_1/retry", {"reason": "cli_retry", "mode": "resume"}) in client.calls
    assert ("POST", "/api/atlas/runs/run_1/revise", {"reason": "smaller"}) in client.calls
    assert ("POST", "/api/atlas/runs/run_1/cancel", {"reason": "cli_cancel"}) in client.calls


def test_kasane_cli_sources_do_not_call_direct_patch_apply_or_verify_endpoints() -> None:
    root = Path(__file__).resolve().parents[1]
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            root / "kasane_cli" / "commands.py",
            root / "kasane_cli" / "client.py",
            root / "kasane_cli" / "repl.py",
            root / "scripts" / "atlas_run_cli.py",
        ]
    )
    forbidden = [
        "/api/atlas/patch-proposals/generate",
        "/api/atlas/patch-proposals/decide",
        "/api/atlas/automation/safe-apply-one",
        "/api/atlas/automation/safe-apply-one-and-verify",
        "/api/atlas/multi-item-autopilot/run",
    ]
    for endpoint in forbidden:
        assert endpoint not in sources
