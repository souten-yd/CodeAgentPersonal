from pathlib import Path
TARGETS=['agent/atlas_next_action_orchestrator_service.py','app/api/atlas_pipeline.py','web/js/atlas_dashboard.js']
FORBIDDEN=['shell=True','subprocess.run','git push','git pull','git clone']
def test_forbidden_execution_paths_not_introduced_in_changed_runtime_files():
    joined='\n'.join(Path(f).read_text(encoding='utf-8') for f in TARGETS)
    for token in FORBIDDEN:
        assert token not in joined
