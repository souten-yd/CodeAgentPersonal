from agent.atlas_planner_bridge import AtlasPlannerBridge
from agent.atlas_planner_bridge_schema import AtlasPlannerBridgeRequest


def test_prompt_prefers_planner_context_text_v2_and_preserves_input(tmp_path):
    cap = {}
    class Runner:
        def __init__(self, **kwargs):
            pass
        def run(self, **kw):
            cap['user_input'] = kw['user_input']
            return {'status': 'planned', 'plan': {'implementation_steps': [{'title': 'x'}]}}

    b = AtlasPlannerBridge(ca_data_dir=str(tmp_path), llm_json_fn=lambda s, u: {}, planning_runner_factory=Runner)
    b.create_plan_pool(AtlasPlannerBridgeRequest(input='ORIGINAL INPUT', planner_context_text='old text', planner_context_text_v2='manual-only DO NOT EXECUTE advisory block'))
    ui = cap['user_input']
    assert 'ORIGINAL INPUT' in ui
    assert 'manual-only' in ui and 'DO NOT EXECUTE' in ui and 'ADVISORY REPOSITORY CONTEXT' in ui


def test_prompt_uses_advisory_context_text_fallback(tmp_path):
    cap = {}
    class Runner:
        def __init__(self, **kwargs):
            pass
        def run(self, **kw):
            cap['user_input'] = kw['user_input']
            return {'status': 'planned', 'plan': {'implementation_steps': [{'title': 'x'}]}}
    b = AtlasPlannerBridge(ca_data_dir=str(tmp_path), llm_json_fn=lambda s, u: {}, planning_runner_factory=Runner)
    b.create_plan_pool(AtlasPlannerBridgeRequest(input='goal', advisory_context_text='manual-only context'))
    assert 'manual-only context' in cap['user_input']
