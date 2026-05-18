from pathlib import Path

def test_no_task_agent_routes():
    t = Path('app/api/atlas_bounded_retry.py').read_text(encoding='utf-8')
    assert '/api/task/' not in t and '/api/agent/' not in t

def test_no_arbitrary_command_shell_remote_git():
    t = Path('agent/atlas_bounded_retry_service.py').read_text(encoding='utf-8')
    assert 'shell=True' not in t
    assert 'run_command' not in t
    assert 'git push' not in t and 'git fetch' not in t and 'git pull' not in t
