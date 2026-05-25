from pathlib import Path


def test_vue16_non_default_and_no_execution_controls() -> None:
    ui = Path('ui.html').read_text(encoding='utf-8')
    assert 'type="module"' not in ui

    req = Path('web/atlas-next/src/components/RequirementInput.vue').read_text(encoding='utf-8').lower()
    assert 'start atlas' in req
    assert '<button type="submit"' in req
    assert 'execute one action' not in req

    app = Path('web/atlas-next/src/components/AtlasNextApp.vue').read_text(encoding='utf-8')
    assert 'RequirementInput' in app
