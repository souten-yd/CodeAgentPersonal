"""Contract: the /git/* routes are extracted from main.py into app/api/git.py.

Behavior-preserving refactor (see docs/MAINTAINABILITY_PLAN.md M1): the six git endpoints now live
in an APIRouter registered via app.server.include_routers; main.py keeps only the git helper
functions. This guards that the routes do not silently move back into main.py and that the router
stays wired.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = (ROOT / "main.py").read_text(encoding="utf-8")
GIT_PY = (ROOT / "app" / "api" / "git.py").read_text(encoding="utf-8")
SERVER_PY = (ROOT / "app" / "server.py").read_text(encoding="utf-8")

_ROUTES = ["/git/status", "/git/commit", "/git/checkout", "/git/reset", "/git/diff", "/git/log"]


def test_git_routes_live_in_router_module():
    assert "router = APIRouter" in GIT_PY
    for path in _ROUTES:
        assert f'"{path}"' in GIT_PY, f"{path} must be defined in app/api/git.py"


def test_main_no_longer_defines_git_routes():
    for path in _ROUTES:
        assert f'@app.get("{path}"' not in MAIN_PY
        assert f'@app.post("{path}"' not in MAIN_PY


def test_git_helpers_remain_in_main():
    # The helpers are intentionally kept in main for now (router imports them lazily).
    for helper in ("def git_status(", "def git_commit(", "def _git_run("):
        assert helper in MAIN_PY


def test_server_registers_git_router():
    assert "from app.api.git import router as git_router" in SERVER_PY
    assert "app.include_router(git_router)" in SERVER_PY


def test_router_imports_helpers_lazily_not_at_module_top():
    # Lazy import inside handlers avoids a circular import (helpers are defined late in main.py).
    assert "from main import" in GIT_PY
    # The module-level import block must not pull from main at import time.
    head = GIT_PY[: GIT_PY.index("router = APIRouter")]
    assert "from main import" not in head
