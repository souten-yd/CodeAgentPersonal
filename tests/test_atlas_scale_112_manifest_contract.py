import json
from pathlib import Path


def test_manifest_forbids_stale_local_only_next_pr_metadata_after_scale_113() -> None:
    manifest_path = Path('web/atlas_ui_surface_manifest.json')
    text = manifest_path.read_text(encoding='utf-8').lower()
    _ = json.loads(manifest_path.read_text(encoding='utf-8'))

    assert 'next local-only metadata ux' not in text
    assert 'next pr may add local-only diff label conflict export' not in text
