from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable

_LAST_FAILURE: dict[str, Any] = {}


def _make_result(
    *,
    ok: bool,
    tool: str,
    args: dict[str, Any],
    output: Any = None,
    error: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "tool": tool,
        "args": args,
        "output": output,
        "error": error,
        "meta": meta or {},
    }


def _load_legacy_tool(name: str) -> Callable[..., str]:
    import importlib

    module = importlib.import_module("main")
    func = getattr(module, name, None)
    if func is None or not callable(func):
        raise AttributeError(f"legacy tool '{name}' is not available")
    return func


def _record_failure(tool: str, args: dict[str, Any], stderr: str, returncode: int | None = None) -> None:
    _LAST_FAILURE.clear()
    _LAST_FAILURE.update(
        {
            "tool": tool,
            "args": args,
            "stderr": stderr,
            "returncode": returncode,
        }
    )


def read_file(path: str) -> dict[str, Any]:
    args = {"path": path}
    try:
        content = Path(path).read_text(encoding="utf-8")
        return _make_result(ok=True, tool="read_file", args=args, output=content)
    except Exception as exc:  # noqa: BLE001
        return _make_result(ok=False, tool="read_file", args=args, error=str(exc))


def write_file(path: str, content: str) -> dict[str, Any]:
    args = {"path": path, "content": content}
    try:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return _make_result(ok=True, tool="write_file", args=args, output=f"wrote {len(content)} bytes")
    except Exception as exc:  # noqa: BLE001
        return _make_result(ok=False, tool="write_file", args=args, error=str(exc))


def apply_patch(diff: str) -> dict[str, Any]:
    args = {"diff": diff}
    if not diff.strip():
        return _make_result(ok=False, tool="apply_patch", args=args, error="diff is empty")

    proc = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        input=diff,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=Path(__file__).resolve().parents[2],
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip() or "failed to apply patch"
        _record_failure("apply_patch", args, stderr, proc.returncode)
        return _make_result(
            ok=False,
            tool="apply_patch",
            args=args,
            error=stderr,
            meta={"returncode": proc.returncode},
        )

    return _make_result(ok=True, tool="apply_patch", args=args, output="patch applied")


def search_code(query: str, subdir: str = "", max_results: int = 100, project: str = "default") -> dict[str, Any]:
    args = {
        "query": query,
        "subdir": subdir,
        "max_results": max_results,
        "project": project,
    }
    try:
        search_in_files = _load_legacy_tool("search_in_files")
        output = search_in_files(
            query=query,
            subdir=subdir,
            max_results=max_results,
            project=project,
        )
        ok = not str(output).startswith("ERROR:")
        return _make_result(ok=ok, tool="search_code", args=args, output=output, error=None if ok else str(output))
    except Exception as exc:  # noqa: BLE001
        return _make_result(ok=False, tool="search_code", args=args, error=str(exc))


def run_command(cmd: str, project: str = "default", timeout: int | None = None) -> dict[str, Any]:
    args = {"cmd": cmd, "project": project, "timeout": timeout}
    try:
        run_shell = _load_legacy_tool("run_shell")
        output = run_shell(command=cmd, project=project, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        _record_failure("run_command", args, str(exc), None)
        return _make_result(ok=False, tool="run_command", args=args, error=str(exc))

    text_output = str(output)
    ok = text_output.startswith("[ok]")
    if not ok:
        _record_failure("run_command", args, text_output, None)
    return _make_result(ok=ok, tool="run_command", args=args, output=output, error=None if ok else text_output)


def run_tests(command: str | None = None, project: str = "default", timeout: int | None = None) -> dict[str, Any]:
    configured = command or os.getenv("CODEAGENT_TEST_CMD")
    if not configured:
        if Path("pytest.ini").exists() or Path("pyproject.toml").exists() or Path("tests").exists():
            configured = "pytest -q"
        elif Path("package.json").exists():
            configured = "npm test"
        else:
            configured = "pytest -q"

    args = {"command": configured, "project": project, "timeout": timeout}
    result = run_command(cmd=configured, project=project, timeout=timeout)
    result["tool"] = "run_tests"
    result["args"] = args
    if not result["ok"]:
        _record_failure("run_tests", args, str(result.get("error") or result.get("output") or ""), None)
    return result


def get_error_trace() -> dict[str, Any]:
    args: dict[str, Any] = {}
    if not _LAST_FAILURE:
        return _make_result(
            ok=True,
            tool="get_error_trace",
            args=args,
            output="",
            meta={"message": "no recent failures"},
        )

    return _make_result(
        ok=True,
        tool="get_error_trace",
        args=args,
        output=_LAST_FAILURE.get("stderr", ""),
        meta={
            "source_tool": _LAST_FAILURE.get("tool"),
            "source_args": _LAST_FAILURE.get("args", {}),
            "returncode": _LAST_FAILURE.get("returncode"),
        },
    )
