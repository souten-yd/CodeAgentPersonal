from pathlib import Path
from types import SimpleNamespace

from agent.atlas_bounded_retry_service import AtlasBoundedRetryService
from agent.atlas_bounded_retry_schema import AtlasBoundedRetryRequest
from agent.atlas_journal import AtlasJournal
from agent.atlas_plan_pool_builder import AtlasPlanPoolBuilder
from agent.atlas_plan_pool_storage import AtlasPlanPoolStorage

class _Ctx:
    def refresh(self, *_a, **_k):
        return SimpleNamespace(bundle_id='ctx1', status='completed')
class _Ev:
    def evaluate(self, *_a, **_k):
        return SimpleNamespace(decision=SimpleNamespace(model_dump=lambda: {'decision':'continue'}), metadata={'eval_id':'ev1'})
class _Vr:
    def __init__(self): self.n=0
    def run_after_auto_safe_apply(self, *_a, **_k):
        self.n += 1
        st = 'passed' if self.n > 1 else 'failed'
        return SimpleNamespace(status=st, model_dump=lambda: {'status': st})

def _svc(tmp_path):
    storage = AtlasPlanPoolStorage(tmp_path); journal = AtlasJournal(tmp_path)
    pool = AtlasPlanPoolBuilder().build_fallback_pool(root_goal='g', project_path=str(tmp_path), project_name='p'); storage.save_pool(pool)
    return AtlasBoundedRetryService(storage=storage, journal=journal, auto_verification_service=_Vr(), context_refresh_service=_Ctx(), evaluator_service=_Ev()), pool

def test_classify_timeout_failure_retryable(tmp_path):
    s,_ = _svc(tmp_path)
    d = s.classify_retryability({'status':'failed','stderr_tail':'timeout'}, {}, __import__('agent.atlas_bounded_retry_policies',fromlist=['']).get_bounded_retry_policy('verification_retry_v1'))
    assert d['retry_allowed'] is True

def test_classify_assertion_error_not_retryable(tmp_path):
    s,_ = _svc(tmp_path)
    d = s.classify_retryability({'status':'failed','stderr_tail':'AssertionError'}, {}, __import__('agent.atlas_bounded_retry_policies',fromlist=['']).get_bounded_retry_policy('verification_retry_v1'))
    assert d['retry_allowed'] is False

def test_retry_recovered_after_second_verification_passes(tmp_path):
    s,pool = _svc(tmp_path); item = pool.items[0]
    r = s.run(AtlasBoundedRetryRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1', verification_result={'status':'failed','stderr_tail':'timeout'}))
    assert r.status == 'recovered'

def test_result_saved_json_and_markdown(tmp_path):
    s,pool = _svc(tmp_path); item = pool.items[0]
    r = s.run(AtlasBoundedRetryRequest(pool_id=pool.pool_id, item_id=item.item_id, run_id='r1', verification_result={'status':'failed','stderr_tail':'timeout'}))
    root = Path('ca_data/atlas/bounded_retry') / pool.pool_id
    assert (root / f'{r.retry_run_id}.json').exists() and (root / f'{r.retry_run_id}.md').exists()
