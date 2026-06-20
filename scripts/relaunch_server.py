#!/usr/bin/env python3
"""Detached helper that relaunches the FastAPI (uvicorn) server after a self-update.

The running server spawns this as a detached child (see app/services/self_update.py),
then terminates itself. This helper waits for the old server to release the HTTP port,
then starts a fresh ``python -m uvicorn main:app`` with the same host/port — picking up
any pulled code changes. Environment and LLM state are left untouched (a lightweight
restart, not a full launcher re-run), and it works the same on Windows and Linux.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time


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


def _parent_gone(pid: int) -> bool:
    if pid <= 0:
        return True
    try:
        os.kill(pid, 0)
        return False
    except OSError:
        return True


def _wait_for_old_server(host: str, port: int, parent_pid: int, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _parent_gone(parent_pid) and _port_released(host, port):
            return
        time.sleep(0.5)


def _spawn_uvicorn(host: str, port: int, base_dir: str) -> subprocess.Popen:
    cmd = [
        sys.executable, "-m", "uvicorn", "main:app",
        "--host", host, "--port", str(port),
        "--log-level", "info", "--app-dir", base_dir,
    ]
    print(f"[relaunch] starting: {' '.join(cmd)}", flush=True)
    kwargs: dict = {"cwd": base_dir}
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP so the new server outlives this helper.
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Relaunch the KasaneCore FastAPI server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    _wait_for_old_server(args.host, args.port, args.parent_pid, args.timeout)
    _spawn_uvicorn(args.host, args.port, args.base_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
