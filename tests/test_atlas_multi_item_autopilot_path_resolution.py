"""Regression test for the FileNotFoundError that crashed the full-auto flow.

Plan pools are saved under the absolute resolved ca_data root
(``resolve_atlas_ca_data_root``), but the multi-item autopilot service factory
used to build storage from the hardcoded relative path ``"ca_data"``. When the
process cwd differed from the data root (e.g. cwd ``/app`` while data lives at
``/workspace/ca_data`` on RunPod), ``load_pool`` raised
``FileNotFoundError: 'ca_data/atlas/plan_pools/pool_*.json'``.
"""

import os
from pathlib import Path

from agent.atlas_plan_pool_schema import AtlasPlanPool
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage
from app.api.atlas_multi_item_autopilot import _service


class _FakeState:
    pass


class _FakeApp:
    def __init__(self, ca_data_dir: str):
        self.state = _FakeState()
        self.state.atlas_ca_data_dir = ca_data_dir


class _FakeRequest:
    def __init__(self, ca_data_dir: str):
        self.app = _FakeApp(ca_data_dir)


def test_service_loads_pool_from_resolved_root_regardless_of_cwd(tmp_path: Path, monkeypatch) -> None:
    ca_root = tmp_path / "ca_data_abs"
    # Pool saved under the absolute resolved root (mimics create_plan_pool).
    AtlasPlanPoolStorage(ca_root).save_pool(AtlasPlanPool(pool_id="pool_fix", root_goal="g", items=[]))

    # Run from an unrelated cwd that has no ./ca_data (mimics /app on RunPod).
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    request = _FakeRequest(str(ca_root))
    svc = _service(request, "myproject")

    # storage is rooted at the resolved absolute root, journal scoped to workspace
    assert Path(svc.storage.root_dir).resolve() == ca_root.resolve()
    assert svc.journal.workspace_id == "myproject"

    # the load that used to crash now succeeds
    loaded = svc.storage.load_pool("pool_fix")
    assert loaded.pool_id == "pool_fix"


def test_old_relative_path_would_fail(tmp_path: Path, monkeypatch) -> None:
    ca_root = tmp_path / "ca_data_abs"
    AtlasPlanPoolStorage(ca_root).save_pool(AtlasPlanPool(pool_id="pool_fix", root_goal="g", items=[]))
    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    # The previous behavior (relative "ca_data") cannot find the pool.
    try:
        AtlasPlanPoolStorage("ca_data").load_pool("pool_fix")
        raised = False
    except FileNotFoundError:
        raised = True
    assert raised
