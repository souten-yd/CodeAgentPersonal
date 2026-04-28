from pathlib import Path


def _ui_html() -> str:
    return Path('ui.html').read_text(encoding='utf-8')


def test_ui_uses_bundle_debug_and_events_endpoints() -> None:
    html = _ui_html()
    assert '/nexus/research/jobs/' in html
    assert '/bundle' in html
    assert '/debug' in html
    assert '/events' in html


def test_ui_shows_download_phase_progress_and_breakdown() -> None:
    html = _ui_html()
    assert 'current_phase' in html
    assert 'download_completed' in html
    assert 'download_total' in html
    assert 'download_active' in html
    assert 'download_degraded' in html
    assert 'download_failed' in html
    assert 'download_skipped' in html
    assert 'ダウンロード中 ${completed}/${total} 件完了' in html


def test_ui_shows_stalled_warning_message_from_health() -> None:
    html = _ui_html()
    assert 'health.is_stalled' in html or 'is_stalled === true' in html
    assert 'stalled_reason' in html
    assert 'suggested_action' in html
    assert 'heartbeatが120秒以上更新されていません。サーバー処理停止の可能性があります。' in html


def test_ui_shows_incomplete_output_warning() -> None:
    html = _ui_html()
    assert 'output_incomplete' in html
    assert 'output_truncated' in html
    assert 'finish_reason' in html
    assert 'max_tokensまたはtimeoutを増やしてください。' in html
