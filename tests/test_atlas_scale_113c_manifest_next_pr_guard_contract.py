import json
from pathlib import Path


MANIFEST_PATH = Path('web/atlas_ui_surface_manifest.json')
HISTORICAL_COMPLETED_ALLOWLIST = {
    'level1_next_pr_may_add_disabled_backend_skeleton',
    'level1_next_pr_may_add_readiness_diagnostics_get',
    'level1_next_pr_may_add_readiness_ui_display',
    'level1_next_pr_may_add_gate_filtering_or_grouping',
    'level1_next_pr_may_add_export_or_copy_metadata',
    'level1_next_pr_may_add_metadata_snapshot_comparison',
    'level1_next_pr_may_add_metadata_history_local_storage',
    'level1_next_pr_may_add_history_import_export_local_only',
    'level1_next_pr_may_add_history_diff_view_local_only',
    'level1_next_pr_may_add_history_diff_filtering_local_only',
    'level1_next_pr_may_add_history_diff_export_local_only',
    'level1_next_pr_may_add_history_diff_annotation_local_only',
    'level1_next_pr_may_add_history_diff_bookmarks_local_only',
    'level1_next_pr_may_add_history_diff_labels_local_only',
    'level1_next_pr_may_add_history_diff_label_filter_local_only',
    'level1_next_pr_may_add_history_diff_label_import_local_only',
}


def test_manifest_forbids_unallowlisted_level1_next_pr_keys_after_scale_113() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    next_pr_keys = {k for k in manifest if k.startswith('level1_next_pr_may_add_')}

    unexpected = sorted(next_pr_keys - HISTORICAL_COMPLETED_ALLOWLIST)
    assert not unexpected, f'unallowlisted level1_next_pr_may_add_ keys found: {unexpected}'


def test_manifest_no_deleted_planning_doc_references_in_ui_manifest() -> None:
    manifest_text = MANIFEST_PATH.read_text(encoding='utf-8')
    for removed_doc in (
        'docs/atlas_development_handoff.md',
        'docs/atlas_thinui_readiness.md',
        'docs/atlas_vue_migration_plan.md',
    ):
        assert removed_doc not in manifest_text
