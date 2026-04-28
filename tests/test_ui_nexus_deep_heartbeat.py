from pathlib import Path


def test_ui_uses_bundle_polling_and_health_fields() -> None:
    html = Path('ui.html').read_text(encoding='utf-8')
    assert '/nexus/research/jobs/' in html
    assert '/bundle' in html
    assert 'current_phase' in html
    assert 'current_message' in html
    assert 'seconds_since_last_heartbeat' in html
    assert 'is_stalled' in html
    assert 'stalled_reason' in html
    assert 'suggested_action' in html


def test_ui_shows_download_phase_progress_and_degraded() -> None:
    html = Path('ui.html').read_text(encoding='utf-8')
    assert 'download_completed' in html
    assert 'download_total' in html
    assert 'download_active' in html
    assert 'download_degraded' in html
    assert 'download_failed' in html
    assert 'download_skipped' in html
    assert 'latest_download_progress' in html


def test_ui_shows_stalled_warning_message() -> None:
    html = Path('ui.html').read_text(encoding='utf-8')
    assert 'heartbeatが120秒以上更新されていません。サーバー処理停止の可能性があります。' in html


def test_ui_shows_incomplete_warning() -> None:
    html = Path('ui.html').read_text(encoding='utf-8')
    assert 'output_incomplete' in html or 'output_truncated' in html
    assert 'finish_reason' in html
    assert 'max_tokensまたはtimeoutを増やしてください。' in html


def test_ui_stall_decision_uses_health_not_fixed_timeout() -> None:
    html = Path('ui.html').read_text(encoding='utf-8')
    assert 'health.is_stalled' in html or 'is_stalled === true' in html
    assert 'maxTicks = 300' in html
