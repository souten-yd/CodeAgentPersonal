from pathlib import Path
import json


def test_diagnostics_drawer_dom_contract():
    html = Path("ui.html").read_text(encoding="utf-8")
    assert 'id="atlas-diagnostics-drawer"' in html
    assert 'id="atlas-json-panel"' in html
    assert 'id="atlas-planpool-id"' in html
    assert 'id="atlas-pipeline-run-id"' in html


def test_diagnostics_manifest_classification_contract():
    manifest = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in manifest["surfaces"]}
    diagnostics_ids = [
        "atlas-diagnostics-drawer",
        "atlas-json-panel",
        "atlas-planpool-id",
        "atlas-pipeline-run-id",
        "atlas-next-action-multi-status-run-id",
        "atlas-operator-loop-pool-id",
        "atlas-operator-loop-run-id",
        "atlas-repo-index-card",
        "atlas-repo-context-snapshot-btn",
        "atlas-repo-context-scope-btn",
        "atlas-repo-context-impacted-tests-btn",
        "atlas-repo-context-verification-plan-btn",
    ]
    for sid in diagnostics_ids:
        assert by_id[sid]["category"] == "diagnostics"
        assert by_id[sid]["default_visible"] is False
        assert by_id[sid]["can_hide"] is True
