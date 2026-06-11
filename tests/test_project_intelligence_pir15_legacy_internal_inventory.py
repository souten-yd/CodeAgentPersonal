"""PIR-15 legacy-internal dependency inventory tests."""

from __future__ import annotations

from pathlib import Path

from agent.project_intelligence.inspection.consumer_inventory import build_inventory


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_legacy_owner_internals_are_not_counted_as_direct_production_consumers() -> None:
    inventory = build_inventory(REPO_ROOT)
    rows = {row["legacy_module"]: row for row in inventory["legacy_consumers"]}
    assert "agent.atlas_repo_context_service" not in rows

    adapters = {row["module"]: row for row in inventory["project_intelligence"]["adapters"]}
    assert adapters["agent.project_intelligence.adapters.repo_context_service"]["present"] is True
