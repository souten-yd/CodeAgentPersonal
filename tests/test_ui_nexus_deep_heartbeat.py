from pathlib import Path


def test_ui_uses_heartbeat_and_stalled_message() -> None:
    html = Path('ui.html').read_text(encoding='utf-8')
    assert '/nexus/research/jobs/' in html
    assert '/bundle' in html
    assert 'seconds_since_last_heartbeat' in html
    assert '120秒以上heartbeatがありません。サーバー側処理停止の可能性があります。' in html
    assert 'latest_download_progress' in html or 'download_completed' in html


def test_ui_shows_incomplete_warning() -> None:
    html = Path('ui.html').read_text(encoding='utf-8')
    assert 'output_incomplete' in html or 'output_truncated' in html
    assert 'generation:' in html
