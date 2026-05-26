from pathlib import Path


def test_default_readiness_component_exists_and_display_only() -> None:
    text = Path('web/atlas-next/src/components/DefaultReadinessPreflight.vue').read_text(encoding='utf-8').lower()
    for marker in [
        'default readiness preflight (display-only)',
        'current root default is guarded atlas next when the prebuilt dist is valid',
        '/atlas-next',
        'legacy fallback route',
        'guarded root default applied',
        'default apply does not enable execution controls',
    ]:
        assert marker in text
    for banned in ['<button', '@click', 'submit', 'fetch(', 'atlasclient']:
        assert banned not in text
