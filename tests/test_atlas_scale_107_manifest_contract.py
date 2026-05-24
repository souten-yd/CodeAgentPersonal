import json
from pathlib import Path
MANIFEST=json.loads(Path('web/atlas_ui_surface_manifest.json').read_text())

def test_scale_107_fields():
    expected={
        'level1_readiness_metadata_history_diff_bookmarks_checkpoint':'PR-ATLAS-SCALE-107',
        'level1_readiness_metadata_history_diff_bookmarks_enabled':True,
        'level1_readiness_metadata_history_diff_bookmarks_local_only':True,
        'level1_readiness_metadata_history_diff_bookmarks_upload_enabled':False,
        'level1_readiness_metadata_history_diff_bookmarks_backend_mutation_enabled':False,
        'level1_readiness_metadata_history_diff_bookmarks_decides_readiness':False,
        'level1_readiness_metadata_history_diff_bookmarks_computes_execution_eligibility':False,
        'level1_readiness_metadata_history_diff_bookmarks_execution_enabled':False,
        'level1_next_pr_may_add_history_diff_labels_local_only':True,
        'level1_next_pr_must_not_enable_execution':True,
        'level1_next_pr_may_add_history_diff_bookmarks_local_only':True,
    }
    for k,v in expected.items(): assert MANIFEST.get(k)==v
