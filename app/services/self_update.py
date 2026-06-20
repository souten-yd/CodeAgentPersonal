"""Self-update service: pull the KasaneCore repo and relaunch the FastAPI server.

Backs ``POST /system/self-update`` so the operator can update code and restart from the
settings modal instead of doing it by hand on the PC each time. Design choices (per the
operator):
  * ``git pull --ff-only`` only — no stash, no reset. Conflicts/local divergence fail
    cleanly without destroying anything; ``--ff-only`` keeps it non-interactive.
  * A lightweight uvicorn relaunch (not a full launcher re-run): environment and the loaded
    LLM are unchanged, only pulled code is picked up. Works on Windows and Linux.

The pure functions take injectable ``runner``/``spawner``/``terminator`` callables so the
endpoint behaviour can be tested without touching git or killing the process.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from collections.abc import Callable

# (cmd, cwd, timeout) -> (returncode, stdout, stderr)
GitRunner = Callable[[list[str], str, float], "tuple[int, str, str]"]


def _default_runner(cmd: list[str], cwd: str, timeout: float) -> tuple[int, str, str]:
    env = dict(os.environ)
    # Never block on a credential / editor prompt during an unattended pull.
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GIT_EDITOR", "true")
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", env=env,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    except FileNotFoundError:
        return 127, "", "git executable not found"


def git_pull(base_dir: str, *, runner: GitRunner | None = None, timeout: float = 120.0) -> dict:
    """Fast-forward pull the repo at ``base_dir``. Never raises; returns a status dict.

    ``ok`` is True only when the working tree is on the latest commit afterwards (including
    the already-up-to-date case). A non-fast-forward / dirty tree / network error yields
    ``ok=False`` with a ``reason`` and the captured git output, leaving the tree untouched.
    """
    runner = runner or _default_runner
    rc, out, err = runner(["git", "-C", base_dir, "rev-parse", "--is-inside-work-tree"], base_dir, 15.0)
    if rc != 0 or "true" not in (out or "").lower():
        return {"ok": False, "reason": "not_a_git_repo", "stdout": out, "stderr": err}

    rc, out, err = runner(["git", "-C", base_dir, "pull", "--ff-only"], base_dir, timeout)
    combined = f"{out}\n{err}".lower()
    if rc == 0:
        already = "already up to date" in combined or "already up-to-date" in combined
        return {
            "ok": True,
            "reason": "already_up_to_date" if already else "updated",
            "changed": not already,
            "stdout": out,
            "stderr": err,
        }
    # Classify the common, recoverable failure modes so the UI can show an actionable message.
    if "not possible to fast-forward" in combined or "diverged" in combined:
        reason = "non_fast_forward"
    elif "local changes" in combined or "would be overwritten" in combined or "unstaged" in combined:
        reason = "dirty_working_tree"
    elif "could not resolve host" in combined or "unable to access" in combined or "timeout" in combined:
        reason = "network_error"
    else:
        reason = "pull_failed"
    return {"ok": False, "reason": reason, "changed": False, "stdout": out, "stderr": err}


def _default_spawn_relauncher(host: str, port: int, base_dir: str, parent_pid: int) -> subprocess.Popen:
    script = os.path.join(base_dir, "scripts", "relaunch_server.py")
    cmd = [
        sys.executable, script,
        "--host", host, "--port", str(port),
        "--base-dir", base_dir, "--parent-pid", str(parent_pid),
    ]
    kwargs: dict = {"cwd": base_dir}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def _default_terminate_self() -> None:  # pragma: no cover - exercised only in a real restart
    # The relauncher gates the new server on this port being released, so a hard exit here is
    # safe: the OS closes the listening socket and the fresh server can bind.
    os._exit(0)


def schedule_restart(
    host: str,
    port: int,
    base_dir: str,
    *,
    delay: float = 1.0,
    spawner: Callable[[str, int, str, int], object] | None = None,
    terminator: Callable[[], None] | None = None,
) -> dict:
    """Spawn the detached relauncher, then arm a timer to terminate this process.

    The short ``delay`` lets the HTTP response flush before the current server goes down.
    Returns immediately; the actual restart happens out-of-band.
    """
    spawner = spawner or _default_spawn_relauncher
    terminator = terminator or _default_terminate_self
    parent_pid = os.getpid()
    child = spawner(host, port, base_dir, parent_pid)
    timer = threading.Timer(delay, terminator)
    timer.daemon = True
    timer.start()
    return {"ok": True, "relauncher_pid": getattr(child, "pid", None), "parent_pid": parent_pid}
