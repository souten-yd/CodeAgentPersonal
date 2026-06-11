"""PIR-15 legacy-internal dependency inventory tests."""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.inspection.consumer_inventory import build_inventory


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_owner_internals_are_not_counted_as_direct_production_consumers() -> None:
    inventory = build_inventory(REPO_ROOT)
    rows = {row["legacy_module"]: row for row in inventory["legacy_consumers"]}
    repo_context = rows["agent.atlas_repo_context_service"]
    planner_packager = rows["agent.atlas_repo_context_planner_packager"]

    assert repo_context["production_consumer_count"] == 0
    assert repo_context["production_consumers"] == []
    assert repo_context["legacy_internal_consumer_count"] == 2
    assert {
        consumer["path"] for consumer in repo_context["legacy_internal_consumers"]
    } == {
        "agent/atlas_context_refresh_service.py",
        "agent/atlas_repo_context_planner_packager.py",
    }
    assert repo_context["adapter_consumer_count"] == 1

    assert planner_packager["production_consumer_count"] == 0
    assert planner_packager["production_consumers"] == []
    assert planner_packager["legacy_internal_consumer_count"] == 3

    context_refresh = rows["agent.atlas_context_refresh_service"]
    context_refresh_v2 = rows["agent.atlas_context_refresh_v2_service"]
    assert context_refresh["production_consumer_count"] == 0
    assert context_refresh["production_consumers"] == []
    assert context_refresh["adapter_consumer_count"] == 1
    assert context_refresh_v2["production_consumer_count"] == 0
    assert context_refresh_v2["adapter_consumer_count"] == 1
