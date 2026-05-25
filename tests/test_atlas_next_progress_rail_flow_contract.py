from pathlib import Path


def test_progress_rail_shows_full_start_to_guarded_execute_path() -> None:
    text = Path('web/atlas-next/src/components/ProgressRail.vue').read_text(encoding='utf-8')
    for marker in [
        'Atlas workflow path',
        'Start Atlas',
        'Plan Review',
        'Approval Review',
        'Execute Preview',
        'Patch Review',
        'Guarded Execute',
    ]:
        assert marker in text


def test_progress_rail_remains_display_only_and_backend_owned() -> None:
    text = Path('web/atlas-next/src/components/ProgressRail.vue').read_text(encoding='utf-8')
    assert '<button' not in text
    assert '@click' not in text
    assert 'fetch(' not in text
    assert 'createPlanPool' not in text
    assert 'Backend authoritative' in text
    assert 'Vue execution controls disabled' in text
    assert 'Vue does not apply changes' in text
