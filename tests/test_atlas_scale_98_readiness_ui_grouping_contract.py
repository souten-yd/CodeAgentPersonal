from pathlib import Path


def test_scale_98_grouping_and_summary_present() -> None:
    t = Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text(encoding='utf-8')
    for token in [
        'Summary by owner', 'Summary by source', 'Summary by current_status',
        'summarizeBy(', "key: 'owner' | 'source' | 'current_status'",
        'ownerSummary', 'sourceSummary', 'statusSummary'
    ]:
        assert token in t
