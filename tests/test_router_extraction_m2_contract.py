"""Contract: ensemble / voice routes are extracted from main.py into app/api routers.

Behavior-preserving refactor (docs/MAINTAINABILITY_PLAN.md, M2 start). Each group moves into an
APIRouter registered via app.server.include_routers; domain helpers stay in main.py and are imported
lazily inside the handlers.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = (ROOT / "main.py").read_text(encoding="utf-8")
SERVER_PY = (ROOT / "app" / "server.py").read_text(encoding="utf-8")

_GROUPS = {
    "ensemble": {
        "routes": ["/ensemble/settings", "/ensemble/vram"],
        "helpers": ["def get_ensemble_resource_status("],
    },
    "voice": {
        # /voice/status is owned by a different (pre-existing) router; only these 3 moved from main.
        "routes": ["/voice/load", "/voice/unload", "/voice/transcribe"],
        "helpers": ["def voice_load(", "def voice_unload("],
    },
}


def test_routes_live_in_router_modules():
    for name, spec in _GROUPS.items():
        mod = (ROOT / "app" / "api" / f"{name}.py").read_text(encoding="utf-8")
        assert "router = APIRouter" in mod
        for path in spec["routes"]:
            assert f'"{path}"' in mod, f"{path} must be in app/api/{name}.py"


def test_main_no_longer_defines_these_routes():
    for spec in _GROUPS.values():
        for path in spec["routes"]:
            for verb in ("get", "post", "put", "delete"):
                assert f'@app.{verb}("{path}"' not in MAIN_PY


def test_helpers_remain_in_main():
    for spec in _GROUPS.values():
        for helper in spec["helpers"]:
            assert helper in MAIN_PY, helper


def test_server_registers_each_router():
    for name in _GROUPS:
        assert f"from app.api.{name} import router as {name}_router" in SERVER_PY
        assert f"app.include_router({name}_router)" in SERVER_PY
