from app.atlas.workflow_state_contract import build_read_only_workflow_state


def test_vue_15b_workflow_state_metadata_truthfulness_contract() -> None:
    payload = build_read_only_workflow_state(
        goal="g", project_path="p", phase="read_only_preview", status="ok", primary_cta_label="Read-only"
    )
    assert payload["contract"] == "read_only_workflow_state"
    assert payload["vue_execution_enabled"] is False
    assert payload["safety"]["mutation_endpoints_enabled"] is False

    meta = payload["workflow_state_metadata"]
    assert meta["data_freshness"] in {"unknown", "fresh", "stale"}
