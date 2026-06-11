from fastapi.testclient import TestClient

from app.server import create_app


def test_planpool_integration_plan_payload_has_metadata(tmp_path):
    c = TestClient(create_app())
    payload = {
        "input": "x",
        "project_path": str(tmp_path),
        "enable_repo_context": True,
        "plan_payload": {
            "items": [
                {"item_id": "i1", "title": "one", "target_files": ["app/a.py"]},
                {"item_id": "i2", "title": "two", "target_files": ["app/b.py"]},
            ]
        },
    }
    r = c.post('/api/atlas/plan-pools?sync=1', json=payload)
    assert r.status_code == 200
    pool = r.json()["plan_pool"]
    pim = pool.get("metadata", {}).get("plan_item_impact_map", {})
    assert pim and pim.get("advisory_only") is True and pim.get("executed") is False
    assert pim.get("auto_verification_triggered") is False
    assert pim.get("auto_test_execution_triggered") is False
    for item in pool.get("items", []):
        impact = item.get("metadata", {}).get("impact_map", {})
        assert impact
        assert impact.get("advisory_only") is True
        assert impact.get("executed") is False


def test_planpool_changed_target_top_level_priority(tmp_path, monkeypatch):
    c = TestClient(create_app())
    captured = {}

    def fake_build_map(self, req):
        captured["changed_files"] = list(req.changed_files or [])
        captured["target_files"] = list(req.target_files or [])
        from agent.atlas_plan_item_impact_map_schema import AtlasPlanItemImpactMap

        return AtlasPlanItemImpactMap(status="missing")

    monkeypatch.setattr(
        'agent.project_intelligence.adapters.plan_item_impact_map.ProjectIntelligencePlanItemImpactMapAdapter.build_map',
        fake_build_map,
    )
    r = c.post('/api/atlas/plan-pools?sync=1', json={
        "input": "do x",
        "project_path": str(tmp_path),
        "enable_repo_context": True,
        "changed_files": ["top/a.py"],
        "target_files": ["top/b.py"],
        "metadata": {"changed_files": ["meta/a.py"], "target_files": ["meta/b.py"]},
    })
    assert r.status_code == 200
    assert captured["changed_files"] == ["top/a.py"]
    assert captured["target_files"] == ["top/b.py"]


def test_planpool_changed_target_metadata_fallback(tmp_path, monkeypatch):
    c = TestClient(create_app())
    captured = {}

    def fake_build_map(self, req):
        captured["changed_files"] = list(req.changed_files or [])
        captured["target_files"] = list(req.target_files or [])
        from agent.atlas_plan_item_impact_map_schema import AtlasPlanItemImpactMap

        return AtlasPlanItemImpactMap(status="missing")

    monkeypatch.setattr(
        'agent.project_intelligence.adapters.plan_item_impact_map.ProjectIntelligencePlanItemImpactMapAdapter.build_map',
        fake_build_map,
    )
    r = c.post('/api/atlas/plan-pools?sync=1', json={
        "input": "do x",
        "project_path": str(tmp_path),
        "enable_repo_context": True,
        "metadata": {"changed_files": ["meta/a.py"], "target_files": ["meta/b.py"]},
    })
    assert r.status_code == 200
    assert captured["changed_files"] == ["meta/a.py"]
    assert captured["target_files"] == ["meta/b.py"]


def test_disable_repo_context_no_map(tmp_path):
    c = TestClient(create_app())
    r = c.post('/api/atlas/plan-pools?sync=1', json={"input": "do x", "project_path": str(tmp_path), "enable_repo_context": False})
    pool = r.json()["plan_pool"]
    assert "plan_item_impact_map" not in pool.get("metadata", {})
