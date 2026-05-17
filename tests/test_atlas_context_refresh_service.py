from __future__ import annotations

from pathlib import Path

from agent.atlas_context_refresh_schema import AtlasContextRefreshRequest
from agent.atlas_context_refresh_service import AtlasContextRefreshService


def test_local_first_context_refresh_collects_dev_tools(tmp_path: Path):
    (tmp_path / 'x.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    svc = AtlasContextRefreshService()
    r = svc.refresh(AtlasContextRefreshRequest(pool_id='p1', trigger='manual', project_path=str(tmp_path), changed_files=['x.py']))
    kinds = {s.source_type for s in r.sources}
    assert 'git_status' in kinds and 'file_outline' in kinds and 'symbol_index' in kinds and 'related_tests' in kinds
    assert r.status in {'ready', 'partial'}


def test_context_refresh_respects_max_context_chars(tmp_path: Path):
    (tmp_path / 'x.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    svc = AtlasContextRefreshService()
    r = svc.refresh(AtlasContextRefreshRequest(pool_id='p2', trigger='manual', project_path=str(tmp_path), changed_files=['x.py'], max_context_chars=50))
    assert len(r.context_text) <= 50
    assert 'truncated' in r.warnings


def test_context_refresh_blocks_web_without_policy(tmp_path: Path):
    (tmp_path / 'x.py').write_text('x=1\n', encoding='utf-8')
    r = AtlasContextRefreshService().refresh(AtlasContextRefreshRequest(pool_id='p3', trigger='manual', project_path=str(tmp_path), include_nexus_search=True))
    assert r.status == 'blocked'
    assert 'web_search_not_allowed' in r.warnings
