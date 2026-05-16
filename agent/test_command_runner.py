from __future__ import annotations

import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from agent.atlas_plan_pool_schema import AtlasPlanItem
from agent.test_command_runner_schema import (
    AtlasTestCommandBatchResult,
    AtlasTestCommandBlockReason,
    AtlasTestCommandRequest,
    AtlasTestCommandResult,
)


DEFAULT_ALLOWED_COMMANDS = [
    "python -m py_compile",
    "pytest -q",
    "node --check",
    "python -m json.tool",
    "python scripts/check_ui_inline_script_syntax.py",
]

DEFAULT_FORBIDDEN_TOKENS = [
    "rm ",
    "rm -",
    "del ",
    "rmdir ",
    "sudo ",
    "chmod ",
    "chown ",
    "pip install",
    "npm install",
    "pnpm install",
    "yarn add",
    "curl ",
    "wget ",
    "|",
    "&&",
    ";",
    "`",
    "$(",
    ">",
    "<",
]

SHELL_OPERATOR_TOKENS = {"|", "&&", ";", "`", "$(", ">", "<"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestCommandRunner:
    __test__ = False

    def __init__(
        self,
        allowed_commands: list[str] | None = None,
        forbidden_tokens: list[str] | None = None,
        default_timeout_seconds: int = 120,
        max_output_chars: int = 20000,
    ):
        self.allowed_commands = list(allowed_commands or DEFAULT_ALLOWED_COMMANDS)
        self.forbidden_tokens = list(forbidden_tokens or DEFAULT_FORBIDDEN_TOKENS)
        self.default_timeout_seconds = default_timeout_seconds
        self.max_output_chars = max_output_chars

    def is_allowed_command(self, command: str) -> bool:
        normalized = command.strip()
        if not normalized:
            return False
        if self._first_forbidden_token(normalized) is not None:
            return False
        return any(normalized.startswith(allowed) for allowed in self.allowed_commands)

    def validate_request(self, request: AtlasTestCommandRequest) -> AtlasTestCommandResult | None:
        command = request.command.strip()
        if not command:
            return self._blocked_result(request, "empty_command", "Command is empty.")
        if request.timeout_seconds <= 0:
            return self._blocked_result(request, "timeout_invalid", "Timeout must be greater than zero.")
        if request.cwd and not Path(request.cwd).is_dir():
            return self._blocked_result(request, "working_directory_invalid", "Working directory does not exist.")

        forbidden_token = self._first_forbidden_token(command)
        if forbidden_token is not None:
            if forbidden_token in SHELL_OPERATOR_TOKENS:
                return self._blocked_result(request, "shell_operator", "Command contains a shell operator.")
            return self._blocked_result(request, "forbidden_token", "Command contains a forbidden token.")

        if not any(command.startswith(allowed) for allowed in self.allowed_commands):
            return self._blocked_result(request, "not_allowlisted", "Command is not allowlisted.")

        return None

    def run_command(self, request: AtlasTestCommandRequest) -> AtlasTestCommandResult:
        blocked_result = self.validate_request(request)
        if blocked_result is not None:
            return blocked_result

        command = request.command.strip()
        started_at = _utc_now_iso()
        started = time.monotonic()
        try:
            completed = subprocess.run(
                shlex.split(command),
                cwd=request.cwd or None,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                shell=False,
                check=False,
            )
            finished_at = _utc_now_iso()
            status = "passed" if completed.returncode == 0 else "failed"
            result = AtlasTestCommandResult(
                command=command,
                status=status,
                returncode=completed.returncode,
                stdout=self._truncate(completed.stdout),
                stderr=self._truncate(completed.stderr),
                duration_seconds=time.monotonic() - started,
                started_at=started_at,
                finished_at=finished_at,
                metadata=dict(request.metadata),
            )
            if status == "failed" and not result.stderr:
                result.errors.append("Command failed without stderr output.")
            return result
        except subprocess.TimeoutExpired as exc:
            finished_at = _utc_now_iso()
            return AtlasTestCommandResult(
                command=command,
                status="timed_out",
                returncode=None,
                stdout=self._truncate(self._decode_output(exc.stdout)),
                stderr=self._truncate(self._decode_output(exc.stderr)),
                duration_seconds=time.monotonic() - started,
                started_at=started_at,
                finished_at=finished_at,
                errors=[f"Command timed out after {request.timeout_seconds} seconds."],
                metadata=dict(request.metadata),
            )

    def run_many(
        self,
        requests: list[AtlasTestCommandRequest],
        stop_on_failure: bool = True,
    ) -> AtlasTestCommandBatchResult:
        batch = AtlasTestCommandBatchResult()
        for request in requests:
            result = self.run_command(request)
            batch.results.append(result)
            self._increment_count(batch, result.status)
            if stop_on_failure and result.status in {"failed", "blocked", "timed_out"}:
                break
        return batch

    def run_item_tests(
        self,
        item: AtlasPlanItem,
        cwd: str = "",
        stop_on_failure: bool = True,
    ) -> AtlasTestCommandBatchResult:
        requests = [
            AtlasTestCommandRequest(
                command=command,
                cwd=cwd,
                timeout_seconds=self.default_timeout_seconds,
                metadata={"item_id": item.item_id, "pool_id": item.pool_id, "item_type": item.item_type},
            )
            for command in item.test_commands
        ]
        return self.run_many(requests, stop_on_failure=stop_on_failure)

    def _blocked_result(
        self,
        request: AtlasTestCommandRequest,
        reason: AtlasTestCommandBlockReason,
        error: str,
    ) -> AtlasTestCommandResult:
        now = _utc_now_iso()
        return AtlasTestCommandResult(
            command=request.command.strip(),
            status="blocked",
            blocked_reason=reason,
            errors=[error],
            started_at=now,
            finished_at=now,
            metadata=dict(request.metadata),
        )

    def _first_forbidden_token(self, command: str) -> str | None:
        return next((token for token in self.forbidden_tokens if token in command), None)

    def _truncate(self, output: str) -> str:
        if self.max_output_chars < 0:
            return output
        if len(output) <= self.max_output_chars:
            return output
        return output[: self.max_output_chars]

    def _decode_output(self, output: str | bytes | None) -> str:
        if output is None:
            return ""
        if isinstance(output, bytes):
            return output.decode(errors="replace")
        return output

    def _increment_count(self, batch: AtlasTestCommandBatchResult, status: str) -> None:
        if status == "passed":
            batch.passed_count += 1
        elif status == "failed":
            batch.failed_count += 1
        elif status == "blocked":
            batch.blocked_count += 1
        elif status == "timed_out":
            batch.timed_out_count += 1
        elif status == "skipped":
            batch.skipped_count += 1
