from pathlib import Path

def test_docs_checkpoint_mentions_pr52():
    t=Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-52' in t

def test_no_arbitrary_command_shell_remote_git():
    text=Path('agent/atlas_patch_regen_recommendation_service.py').read_text(encoding='utf-8')
    assert 'shell=True' not in text
    assert 'run_command' not in text
    assert 'git push' not in text and 'git pull' not in text and 'git fetch' not in text
