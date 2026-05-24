import json
from pathlib import Path


def test_manifest_scale_108_fields_present_and_safe():
    data = json.loads(Path("web/atlas_ui_surface_manifest.json").read_text(encoding="utf-8"))
    assert data["level1_readiness_metadata_history_diff_labels_checkpoint"] == "PR-ATLAS-SCALE-108"
    assert data["level1_readiness_metadata_history_diff_labels_enabled"] is True
    assert data["level1_readiness_metadata_history_diff_labels_local_only"] is True
    assert data["level1_readiness_metadata_history_diff_labels_upload_enabled"] is False
    assert data["level1_readiness_metadata_history_diff_labels_backend_mutation_enabled"] is False
    assert data["level1_readiness_metadata_history_diff_labels_decides_readiness"] is False
    assert data["level1_readiness_metadata_history_diff_labels_computes_execution_eligibility"] is False
    assert data["level1_readiness_metadata_history_diff_labels_execution_enabled"] is False
    assert data["level1_readiness_metadata_history_diff_bookmarks_checkpoint"] == "PR-ATLAS-SCALE-107"
