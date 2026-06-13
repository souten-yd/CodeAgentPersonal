"""Contract: skills / memory / repo routes are extracted from main.py into app/api routers.

Behavior-preserving refactor (docs/MAINTAINABILITY_PLAN.md M1). Each route group moves into an
APIRouter registered via app.server.include_routers; the domain helper functions stay in main.py and
are imported lazily inside the handlers. Guards that the routes don't drift back into main.py and the
routers stay wired.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = (ROOT / "main.py").read_text(encoding="utf-8")
SERVER_PY = (ROOT / "app" / "server.py").read_text(encoding="utf-8")


_GROUPS = {
    "skills": {
        "module": "app/api/skills.py",
        "routes": ["/skills", "/skills/{name}", "/skills/reload"],
        "helpers": ["def _load_all_skills(", "def _active_skills(", "def _upsert_skill("],
    },
    "memory": {
        "module": "app/api/memory.py",
        "routes": ["/memory", "/memory/{mid}", "/memory/analyze/{job_id}"],
        "helpers": ["def memory_save(", "def memory_get_all(", "def memory_delete("],
    },
    "repo": {
        "module": "app/api/repo.py",
        "routes": ["/repo/config", "/repo/init", "/repo/sync", "/repo/test-connection", "/repo/status"],
        "helpers": ["def repo_config_load(", "def creds_load(", "def _ensure_ca_data_gitignore("],
    },
}


def test_routes_live_in_router_modules():
    for name, spec in _GROUPS.items():
        mod = (ROOT / spec["module"]).read_text(encoding="utf-8")
        assert "router = APIRouter" in mod, name
        for path in spec["routes"]:
            assert f'"{path}"' in mod, f"{path} must be in {spec['module']}"


def test_main_no_longer_defines_these_routes():
    for spec in _GROUPS.values():
        for path in spec["routes"]:
            assert f'@app.get("{path}"' not in MAIN_PY
            assert f'@app.post("{path}"' not in MAIN_PY
            assert f'@app.put("{path}"' not in MAIN_PY
            assert f'@app.delete("{path}"' not in MAIN_PY


def test_helpers_remain_in_main():
    for spec in _GROUPS.values():
        for helper in spec["helpers"]:
            assert helper in MAIN_PY, helper


def test_server_registers_each_router():
    for name in _GROUPS:
        assert f"from app.api.{name} import router as {name}_router" in SERVER_PY
        assert f"app.include_router({name}_router)" in SERVER_PY


def test_routers_import_helpers_lazily():
    for spec in _GROUPS.values():
        mod = (ROOT / spec["module"]).read_text(encoding="utf-8")
        assert "from main import" in mod
        head = mod[: mod.index("router = APIRouter")]
        assert "from main import" not in head
