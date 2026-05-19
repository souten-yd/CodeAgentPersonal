from pathlib import Path

def test_docs_mentions_pr54():
    text = Path('docs/atlas_unified_autopilot_checkpoint.md').read_text(encoding='utf-8')
    assert 'PR-ATLAS-PIPE-54' in text

def test_no_task_agent_routes():
    assert '/api/task/' not in Path('app/api/atlas_supervised_item_status.py').read_text(encoding='utf-8')
    assert '/api/agent/' not in Path('app/api/atlas_supervised_item_status.py').read_text(encoding='utf-8')

def test_no_arbitrary_command_shell_remote_git():
    t=Path('agent/atlas_supervised_item_status_service.py').read_text(encoding='utf-8')
    assert 'shell=True' not in t and 'git push' not in t and 'git pull' not in t and 'git fetch' not in t
