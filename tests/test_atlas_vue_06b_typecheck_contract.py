from pathlib import Path


def test_vue_06b_status_card_sfc_typecheck_contract() -> None:
    status_card = Path('web/atlas-next/src/components/StatusCard.vue').read_text(encoding='utf-8')
    lower = status_card.lower()

    for required in [
        '<script setup lang="ts">',
        'defineProps',
        'title: string',
    ]:
        assert required in status_card

    for forbidden in [
        'fetch(',
        '@click',
        '/execute',
        '/apply',
        '/approve',
        '/safe_apply',
        '/rollback',
        '/restore',
    ]:
        assert forbidden.lower() not in lower


def test_vue_06b_docs_pointer_if_updated() -> None:
    roadmap = Path('docs/atlas_scale_master_roadmap.md').read_text(encoding='utf-8').lower()
    assert 'pr-atlas-vue-06: bind vue read-only adapter to stable get workflow_state contract' in roadmap
    assert 'pr-atlas-vue-06b: fix vue next statuscard sfc typecheck failure' in roadmap
