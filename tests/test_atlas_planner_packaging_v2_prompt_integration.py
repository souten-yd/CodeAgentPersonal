from agent.atlas_planner_bridge import AtlasPlannerBridge
from agent.atlas_planner_bridge_schema import AtlasPlannerBridgeRequest

def test_prompt_gets_advisory_context(tmp_path):
    cap={}
    class R:
        def __init__(self,**k):pass
        def run(self, **kw):
            cap['user_input']=kw['user_input']
            return {"status":"planned","plan":{"implementation_steps":[{"title":"x"}]}}
    b=AtlasPlannerBridge(ca_data_dir=str(tmp_path), llm_json_fn=lambda s,u:{}, planning_runner_factory=R)
    b.create_plan_pool(AtlasPlannerBridgeRequest(input='goal', planner_context_text_v2='manual-only do not execute'))
    assert 'ADVISORY REPOSITORY CONTEXT' in cap['user_input'] and 'do not execute' in cap['user_input']
