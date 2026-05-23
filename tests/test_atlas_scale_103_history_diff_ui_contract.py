from pathlib import Path
TEXT=Path('web/atlas-next/src/components/Level1ReadinessPanel.vue').read_text()

def test_diff_controls_exist_local_only():
    for token in ['Select diff baseline snapshot','Select diff target snapshot','Compare selected history snapshots','Compare current diagnostics to selected baseline','Clear diff selection','local history diff view']:
        assert token in TEXT

def test_diff_labels_do_not_use_execution_words():
    banned=['>Execute<','>Apply<','>Approve<','>Verify<','>Rollback<','>Retry<','>Continue<','Dry Run']
    for token in banned:
        assert token not in TEXT
