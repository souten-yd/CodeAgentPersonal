from __future__ import annotations

from pathlib import Path

from agent.atlas_context_refresh_schema import AtlasContextRefreshRequest, AtlasContextSource
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_schema import AtlasPlanItem, AtlasPlanPool
from agent.project_intelligence.adapters.context_refresh_v1 import ProjectIntelligenceContextRefreshAdapter


class _FakeNexus:
    def search_local(self, query: str, max_sources: int):
        return [AtlasContextSource(source_id="n1", source_type="nexus_local", title="Nexus Local", summary="Local summary")], []

    def search_web(self, query: str, max_sources: int):
        return [AtlasContextSource(source_id="w1", source_type="nexus_web", title="Nexus Web", summary="Web summary")], []

    def start_deep_research(self, query: str, options: dict):
        return [AtlasContextSource(source_id="d1", source_type="nexus_deep_research", title="Nexus Deep", summary="Deep summary")], []


def test_nexus_sources_are_added_to_bundle(tmp_path: Path):
    (tmp_path / "x.py").write_text("x=1\n", encoding="utf-8")
    svc = ProjectIntelligenceContextRefreshAdapter(nexus_adapter=_FakeNexus())
    r = svc.refresh(AtlasContextRefreshRequest(pool_id="p0", trigger="manual", project_path=str(tmp_path), changed_files=["x.py"]))
    assert any(s.source_type == "nexus_local" for s in r.sources)
    assert "Nexus Local" in r.context_text


def test_changed_files_resolved_from_item_metadata(tmp_path: Path):
    journal = AtlasJournal(tmp_path / "data")
    pool = AtlasPlanPool(pool_id="p1", root_goal="g", items=[AtlasPlanItem(item_id="i1", pool_id="p1", title="t", goal="g", metadata={"target_files": ["a.py"]})])
    journal.save_plan_pool(pool)
    svc = ProjectIntelligenceContextRefreshAdapter(journal=journal)
    r = svc.refresh(AtlasContextRefreshRequest(pool_id="p1", item_id="i1", trigger="manual", changed_files=[]))
    assert r.changed_files == ["a.py"]


def test_changed_files_resolved_from_auto_safe_apply_metadata(tmp_path: Path):
    journal = AtlasJournal(tmp_path / "data")
    pool = AtlasPlanPool(pool_id="p2", root_goal="g", items=[AtlasPlanItem(item_id="i2", pool_id="p2", title="t", goal="g", metadata={"auto_safe_apply": {"changed_files": ["b.py"]}})])
    journal.save_plan_pool(pool)
    svc = ProjectIntelligenceContextRefreshAdapter(journal=journal)
    r = svc.refresh(AtlasContextRefreshRequest(pool_id="p2", item_id="i2", trigger="manual", changed_files=[]))
    assert r.changed_files == ["b.py"]


def test_context_refresh_blocks_web_without_policy(tmp_path: Path):
    (tmp_path / "x.py").write_text("x=1\n", encoding="utf-8")
    r = ProjectIntelligenceContextRefreshAdapter().refresh(AtlasContextRefreshRequest(pool_id="p3", trigger="manual", project_path=str(tmp_path), include_nexus_search=True))
    assert r.status == "blocked"
    assert "web_search_not_allowed" in r.warnings


def test_context_bundle_metadata_limits(tmp_path: Path):
    (tmp_path / "x.py").write_text("x=1\n", encoding="utf-8")
    svc = ProjectIntelligenceContextRefreshAdapter(nexus_adapter=_FakeNexus())
    r = svc.refresh(AtlasContextRefreshRequest(pool_id="p4", trigger="manual", project_path=str(tmp_path), changed_files=["x.py"], max_context_chars=50))
    assert r.metadata["max_sources"] >= 1
    assert "source_count_before_truncation" in r.metadata
    assert "source_count_after_truncation" in r.metadata
    assert "context_chars" in r.metadata


def test_context_refresh_events_recorded(tmp_path: Path):
    journal = AtlasJournal(tmp_path / "data")
    svc = ProjectIntelligenceContextRefreshAdapter(journal=journal)
    svc.refresh(AtlasContextRefreshRequest(pool_id="p5", run_id="r1", trigger="manual", changed_files=["x.py"]))
    events = (tmp_path / "data" / "atlas" / "workspaces" / "default" / "plan_pools" / "p5" / "pipeline_runs" / "r1" / "events.ndjson").read_text(encoding="utf-8")
    assert "context_refresh_started" in events
    assert "context_refresh_" in events
