from pathlib import Path
from tests.test_atlas_manual_next_action_executor_service import _mk_orch,_svc
from agent.atlas_manual_next_action_executor_schema import AtlasManualNextActionExecutorRequest

def test_markdown_contract_sections_and_no_secret_token_dump():
    _mk_orch(); svc,_,_,_,_,_,_=_svc()
    out=svc.execute(AtlasManualNextActionExecutorRequest(pool_id='p1',orchestrator_run_id='nextaction_1',dry_run=True))
    t=Path(f'ca_data/atlas/manual_next_action_executor/p1/{out.executor_run_id}.md').read_text(encoding='utf-8')
    assert '## Confirmation' in t and '## Action Contract' in t and '## Execution Result' in t and '## Safety' in t
    assert 'MANUAL_EXECUTE:' not in t
