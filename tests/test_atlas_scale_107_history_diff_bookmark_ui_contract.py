from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_bookmark_controls_present():
    for t in ['Bookmark changed gate','Bookmark added gate','Bookmark removed gate','Clear local bookmarks','bookmarkedDiffItems','toggleDiffBookmark']:
        assert t in TEXT

def test_bookmark_labels_non_execution_words():
    blocked=['execute','apply','approve','verify','rollback','retry','continue','dry-run']
    lines='\n'.join(l.lower() for l in TEXT.splitlines() if 'bookmark' in l.lower())
    for b in blocked: assert b not in lines
