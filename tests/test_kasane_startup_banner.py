from __future__ import annotations

import io

from app.startup_banner import (
    BANNER_TEXT,
    print_server_startup_banner_once,
    should_show_cli_banner,
    should_show_server_banner,
)
from kasane_cli.repl import run_repl


class FakeClient:
    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        if path == "/api/system/status":
            return {"model": "local-test-model"}
        return {"ok": True, "method": method, "path": path, "payload": payload or {}}


def test_banner_text_is_plain_ascii() -> None:
    BANNER_TEXT.encode("ascii")
    assert "Atlas * Portal * Forge * Twin" in BANNER_TEXT


def test_cli_interactive_prints_banner_by_default() -> None:
    stdout = io.StringIO()

    rc = run_repl(
        FakeClient(),
        stdout=stdout,
        base_url="http://127.0.0.1:8000",
        project_path=".",
        input_fn=lambda prompt: "/exit",
    )

    assert rc == 0
    output = stdout.getvalue()
    assert BANNER_TEXT in output
    assert "KasaneCore Atlas CLI" in output


def test_cli_banner_suppression_controls() -> None:
    assert should_show_cli_banner(json_mode=True, env={}) is False
    assert should_show_cli_banner(quiet=True, env={}) is False
    assert should_show_cli_banner(env={"KASANE_NO_BANNER": "1"}) is False
    assert should_show_cli_banner(env={"KASANE_BANNER": "0"}) is False
    assert should_show_cli_banner(env={}) is True


def test_server_banner_requires_tty_or_explicit_enable() -> None:
    assert should_show_server_banner(env={}, stream=io.StringIO(), is_pytest=False) is False
    assert should_show_server_banner(env={"KASANE_BANNER": "1"}, stream=io.StringIO(), is_pytest=False) is True


def test_server_banner_suppressed_for_pytest_and_machine_readable_modes() -> None:
    assert should_show_server_banner(env={"KASANE_BANNER": "1"}, stream=io.StringIO(), is_pytest=True) is False
    assert should_show_server_banner(
        env={"KASANE_BANNER": "1", "KASANE_LOG_FORMAT": "json"},
        stream=io.StringIO(),
        is_pytest=False,
    ) is False
    assert should_show_server_banner(
        env={"KASANE_BANNER": "1", "KASANE_JSON_MODE": "1"},
        stream=io.StringIO(),
        is_pytest=False,
    ) is False


def test_print_server_startup_banner_writes_identity_when_allowed() -> None:
    stdout = io.StringIO()

    printed = print_server_startup_banner_once(
        env={"KASANE_BANNER": "1"},
        stream=stdout,
        is_pytest=False,
    )

    assert printed is True
    output = stdout.getvalue()
    assert BANNER_TEXT in output
    assert "KasaneCore server startup" in output


def test_print_server_startup_banner_returns_false_when_suppressed() -> None:
    stdout = io.StringIO()

    printed = print_server_startup_banner_once(
        env={"KASANE_BANNER": "1", "KASANE_NO_BANNER": "1"},
        stream=stdout,
        is_pytest=False,
    )

    assert printed is False
    assert stdout.getvalue() == ""
