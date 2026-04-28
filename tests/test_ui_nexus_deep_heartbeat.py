from pathlib import Path


def test_ui_uses_heartbeat_and_stalled_message() -> None:
    html = Path('ui.html').read_text(encoding='utf-8')
    assert '/nexus/research/jobs/' in html
    assert '/bundle' in html
    assert 'seconds_since_last_heartbeat' in html
    assert 'サーバー側の進捗更新が停滞しています。一部URLの応答待ちの可能性があります。' in html


def test_ui_shows_incomplete_warning() -> None:
    html = Path('ui.html').read_text(encoding='utf-8')
    assert 'output_incomplete' in html or 'output_truncated' in html
