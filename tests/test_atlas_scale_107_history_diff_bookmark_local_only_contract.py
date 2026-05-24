from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_bookmarks_local_only_storage_and_export():
    for t in ['DIFF_BOOKMARK_STORAGE_KEY','localStorage','local_diff_bookmarks','local_diff_bookmarks_local_only','bookmarks_local_only']:
        assert t in TEXT

def test_no_bookmark_backend_upload_or_mutation():
    for t in ['method: \'POST\'','method: \'PUT\'','method: \'PATCH\'','method: \'DELETE\'','/bookmarks','fetch(']:
        assert t not in TEXT
