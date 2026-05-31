"""Best-effort test-harness provisioning.

When verification cannot run because the test harness (pytest) is not installed in the interpreter
that runs tests, this mirrors Claude Code's "see a missing dependency -> install it -> re-run"
behaviour instead of declaring success we never verified. It is deliberately narrow: it only
installs the pytest harness, into the SAME interpreter that verification uses (sys.executable, the
one running this server), with a timeout, and it degrades gracefully — if the install fails (e.g.
no network) the caller falls back to an honest "unverified" status rather than a fake "completed".
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import time


class AtlasTestHarnessProvisioner:
    HARNESS_PACKAGES = ("pytest",)

    def __init__(self, *, timeout_seconds: int = 180):
        self.timeout_seconds = timeout_seconds

    def pytest_available(self) -> bool:
        try:
            importlib.invalidate_caches()
            return importlib.util.find_spec("pytest") is not None
        except Exception:  # noqa: BLE001
            return False

    def ensure_pytest(self, *, project_path: str = "") -> dict:
        """Install pytest into sys.executable if it is missing. Returns a status dict:
        already_present | installed | failed (with reason)."""
        if self.pytest_available():
            return {"status": "already_present", "packages": list(self.HARNESS_PACKAGES)}
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pip", "install", *self.HARNESS_PACKAGES],
                cwd=project_path or None,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001 (e.g. pip missing, network blocked at socket level)
            return {"status": "failed", "reason": exc.__class__.__name__, "duration_seconds": time.monotonic() - started}
        if completed.returncode == 0 and self.pytest_available():
            return {"status": "installed", "packages": list(self.HARNESS_PACKAGES), "duration_seconds": time.monotonic() - started}
        return {
            "status": "failed",
            "reason": "pip_install_failed",
            "returncode": completed.returncode,
            "stderr_tail": (completed.stderr or "")[-1000:],
            "duration_seconds": time.monotonic() - started,
        }
