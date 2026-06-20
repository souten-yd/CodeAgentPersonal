#!/usr/bin/env python3
"""Detached helper that relaunches the FastAPI (uvicorn) server after a self-update.

The running server spawns this as a detached child (see app/services/self_update.py),
then terminates itself. This helper waits for the old server to release the HTTP port,
then starts a fresh ``python -m uvicorn main:app`` with the same host/port — picking up
any pulled code changes. Environment and LLM state are left untouched (a lightweight
restart, not a full launcher re-run), and it works the same on Windows and Linux.

IMPORTANT (Windows): this process is created with DETACHED_PROCESS, so it has no console
and the inherited stdio handles are invalid. Writing to stdout/stderr (including the
spawned uvicorn's logging) would raise OSError and crash the relaunch before the new
server starts. Everything here therefore logs to a file and the new uvicorn's stdout/
stderr are redirected to that same log — never to an inherited console.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.request

_LOG_FH = None


def _log(msg: str) -> None:
    """Append a line to the relaunch log. Never raises (best-effort diagnostics)."""
    try:
        if _LOG_FH is not None:
            _LOG_FH.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
            _LOG_FH.flush()
    except Exception:
        pass


def _port_released(host: str, port: int) -> bool:
    """True once nothing is accepting connections on the port (old server gone).

    Connects to a loopback address rather than binding, so a lingering TIME_WAIT socket
    on Windows does not produce a false "free" reading.
    """
    target = "127.0.0.1" if host in ("", "0.0.0.0", "::") else host
    try:
        with socket.create_connection((target, port), timeout=1.0):
            return False  # still accepting -> old server alive
    except OSError:
        return True


def _wait_for_port_release(host: str, port: int, timeout: float) -> bool:
    """Wait until the old server stops accepting on the port. Returns True if released.

    Port availability is the authoritative signal: the new uvicorn cannot bind until the
    old one frees the socket. (Parent-PID checks via os.kill are unreliable on Windows —
    os.kill there calls TerminateProcess rather than probing liveness — so they are not
    used.)
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_released(host, port):
            return True
        time.sleep(0.5)
    return _port_released(host, port)


def _spawn_uvicorn(host: str, port: int, base_dir: str):
    cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", host, "--port", str(port),
        "--log-level", "info", "--app-dir", base_dir,
    ]
    _log(f"starting: {' '.join(cmd)}")
    kwargs: dict = {"cwd": base_dir}
    # The new server MUST NOT inherit this detached process's invalid console handles, or
    # its first log write crashes it. Point its stdout/stderr at the log file instead.
    out = _LOG_FH if _LOG_FH is not None else subprocess.DEVNULL
    kwargs["stdout"] = out
    kwargs["stderr"] = out
    kwargs["stdin"] = subprocess.DEVNULL
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP so the new server outlives this helper.
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    _log(f"spawned uvicorn pid={proc.pid}")
    return proc


def _wait_for_health(port: int, timeout: float) -> bool:
    """Wait until the freshly started server answers /health with 200."""
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if getattr(resp, "status", resp.getcode()) == 200:
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _trigger_model_autoload(port: int) -> None:
    """Ask the new server to auto-load the default model, mirroring the launcher's post-start
    step. Without this the lightweight restart comes up with no LLM loaded, so Atlas planning /
    codegen (which call the local LLM) silently fail until a model is loaded by hand."""
    url = f"http://127.0.0.1:{port}/model/auto-load"
    body = b'{"reason":"self_update_restart"}'
    try:
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            _log(f"auto-load triggered: http={getattr(resp, 'status', resp.getcode())}")
    except Exception as exc:
        _log(f"auto-load request failed: {type(exc).__name__}: {exc}")


def main(argv: list[str] | None = None) -> int:
    global _LOG_FH
    parser = argparse.ArgumentParser(description="Relaunch the KasaneCore FastAPI server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--parent-pid", type=int, default=0)  # accepted for compat; not used
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--log-file", default="")
    parser.add_argument("--autoload", default="1")  # "0" to skip the post-start model auto-load
    args = parser.parse_args(argv)

    log_path = args.log_file or os.path.join(args.base_dir, "logs", "relaunch.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        _LOG_FH = open(log_path, "a", encoding="utf-8", errors="replace")
    except Exception:
        _LOG_FH = None

    _log(f"relaunch start host={args.host} port={args.port} base={args.base_dir}")
    released = _wait_for_port_release(args.host, args.port, args.timeout)
    _log(f"port_released={released} -> spawning uvicorn")
    try:
        _spawn_uvicorn(args.host, args.port, args.base_dir)
    except Exception as exc:  # pragma: no cover - surfaced via the log on a real failure
        _log(f"FAILED to spawn uvicorn: {type(exc).__name__}: {exc}")
        return 1
    # Restore the LLM the way the launcher does: wait for the new server, then auto-load the
    # default model. Skipped only when explicitly disabled (--autoload 0).
    if str(args.autoload).strip() not in ("0", "false", "False"):
        if _wait_for_health(args.port, timeout=max(args.timeout, 90.0)):
            _log("server healthy -> triggering model auto-load")
            _trigger_model_autoload(args.port)
        else:
            _log("server did not become healthy in time; skipping auto-load")
    _log("relaunch helper done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
