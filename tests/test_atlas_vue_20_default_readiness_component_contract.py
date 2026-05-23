from pathlib import Path

def test_default_readiness_component_exists_and_display_only() -> None:
    text = Path('web/atlas-next/src/components/DefaultReadinessPreflight.vue').read_text(encoding='utf-8').lower()
    for marker in ['default readiness preflight (display-only)','current default route remains existing <code>ui.html</code>','/atlas-next','guarded preview','non-default','vue20 does not change default routes','vue21 is the earliest default-enable checkpoint']:
        assert marker in text
    for banned in ['<button', '@click', 'submit', 'fetch(', 'atlasclient']:
        assert banned not in text
