"""7th: route a test failure caused by a CODE bug back to regenerating the implementation item
(not just the test). Covers the linker, the test-vs-code diagnosis, and the router e2e with stubs."""
from __future__ import annotations

from types import SimpleNamespace

from agent.atlas_test_impl_linker import find_implementation_item
from agent.atlas_failure_diagnosis_service import AtlasFailureDiagnosisService, FIX_CODE, FIX_TEST, AMBIGUOUS


def _item(item_id, *, item_type="implementation", target_files=(), metadata=None, risk_level="low"):
    return SimpleNamespace(item_id=item_id, item_type=item_type, target_files=list(target_files), metadata=metadata or {}, risk_level=risk_level)


def _pool(items):
    def get_item(item_id):
        return next((it for it in items if it.item_id == item_id), None)
    return SimpleNamespace(items=items, project_path="", pool_id="pool_x", get_item=get_item)


# ---- linker ---------------------------------------------------------------

def test_linker_matches_by_test_name_convention():
    test_it = _item("t1", item_type="verification", target_files=["tests/test_calc.py"])
    impl_it = _item("i1", target_files=["calc.py"])
    link = find_implementation_item(pool=_pool([impl_it, test_it]), test_item=test_it)
    assert link == {"item_id": "i1", "files": ["calc.py"]}


def test_linker_matches_by_import_stem():
    test_it = _item("t1", target_files=["tests/test_thing.py"])
    impl_it = _item("i1", target_files=["pkg/widget.py"])
    link = find_implementation_item(pool=_pool([impl_it, test_it]), test_item=test_it, test_content="from pkg.widget import build\n")
    assert link["item_id"] == "i1"


def test_linker_ambiguous_returns_empty():
    test_it = _item("t1", target_files=["tests/test_calc.py"])
    a = _item("i1", target_files=["calc.py"])
    b = _item("i2", target_files=["sub/calc.py"])  # two impl items both named calc.py
    assert find_implementation_item(pool=_pool([a, b, test_it]), test_item=test_it) == {}


def test_linker_no_match_for_html_target():
    # A static .html deliverable is not a code-routable target -> no link, caller regenerates test.
    test_it = _item("t1", target_files=["tests/test_page.py"])
    impl_it = _item("i1", target_files=["page.html"])
    assert find_implementation_item(pool=_pool([impl_it, test_it]), test_item=test_it) == {}


# ---- diagnosis ------------------------------------------------------------

def test_diagnosis_import_error_is_fix_code():
    d = AtlasFailureDiagnosisService()
    assert d.diagnose(stderr="ModuleNotFoundError: No module named 'calc'")["decision"] == FIX_CODE


def test_diagnosis_no_tests_is_fix_test():
    d = AtlasFailureDiagnosisService()
    assert d.diagnose(stdout="no tests ran", exit_code=5)["decision"] == FIX_TEST


def test_diagnosis_assertion_is_ambiguous_then_defaults_fix_code_without_llm():
    d = AtlasFailureDiagnosisService()
    assert d.heuristic(stderr="E       AssertionError: assert 1 == 2") == AMBIGUOUS
    out = d.diagnose(stderr="E       AssertionError: assert 1 == 2")
    assert out["decision"] == FIX_CODE and out["source"] == "default_no_llm"


def test_diagnosis_ambiguous_uses_llm_when_available():
    calls = {"n": 0}

    def llm(system, user):
        calls["n"] += 1
        return {"decision": "fix_test", "reason": "test asserts wrong value"}

    d = AtlasFailureDiagnosisService(llm_json_fn=llm)
    out = d.diagnose(stderr="AssertionError", test_content="assert add(1,1)==3", impl_content="def add(a,b): return a+b")
    assert calls["n"] == 1
    assert out["decision"] == FIX_TEST and out["source"] == "llm"


# ---- router e2e (stubbed services) ---------------------------------------

class _StubStorage:
    def __init__(self, pool):
        self._pool = pool
        self.root_dir = "/tmp/does-not-matter"
        self.saved = 0

    def load_pool(self, pool_id):
        return self._pool

    def save_pool(self, pool):
        self.saved += 1


class _StubProposal:
    def __init__(self, ok=True):
        self.ok = ok
        self.seen = []

    def propose_for_item(self, request):
        self.seen.append(request.item_id)
        meta = {
            "patch_content_available": self.ok,
            "patch_generation": {
                "run_id": getattr(request, "run_id", ""),
                "state": "succeeded" if self.ok else "failed",
                "outcome": "success" if self.ok else "failure",
                "patch_content_available": self.ok,
            },
        }
        return SimpleNamespace(status="proposed" if self.ok else "failed", metadata=meta)


class _StubApply:
    def execute_one(self, request):
        return SimpleNamespace(status="applied", changed_files=list(getattr(request, "item_id", "") and [f"{request.item_id}.py"] or []))


class _StubVerify:
    def __init__(self, status):
        self.status = status
        self.verified = []

    def run_after_auto_safe_apply(self, request):
        self.verified.append(request.item_id)
        return SimpleNamespace(status=self.status, warnings=[], model_dump=lambda: {"status": self.status})


class _StubSelfCorrection:
    def __init__(self):
        self.called_with = []

    def run(self, request):
        self.called_with.append(request.item_id)
        from agent.atlas_self_correction_schema import AtlasSelfCorrectionResult
        return AtlasSelfCorrectionResult(pool_id=request.pool_id, item_id=request.item_id, status="exhausted", reason="stub_self_correction")


def _router(pool, *, verify_status="passed", proposal_ok=True, self_corr=None):
    from agent.atlas_correction_router_service import AtlasCorrectionRouterService
    return AtlasCorrectionRouterService(
        storage=_StubStorage(pool),
        journal=SimpleNamespace(append_event=lambda *a, **k: None),
        patch_proposal_service=_StubProposal(ok=proposal_ok),
        auto_safe_apply_service=_StubApply(),
        auto_verification_service=_StubVerify(verify_status),
        self_correction_service=self_corr or _StubSelfCorrection(),
        diagnosis_service=AtlasFailureDiagnosisService(),  # no llm -> heuristic/default
    )


def _sc_request(pool, item_id, vr):
    from agent.atlas_self_correction_schema import AtlasSelfCorrectionRequest
    return AtlasSelfCorrectionRequest(pool_id=pool.pool_id, item_id=item_id, run_id="r1", verification_result=vr)


def test_router_fix_code_regenerates_impl_and_reverifies_test():
    impl = _item("i1", target_files=["calc.py"], metadata={"safe_apply": {"status": "applied"}}, risk_level="low")
    test = _item("t1", item_type="verification", target_files=["tests/test_calc.py"], metadata={"safe_apply": {"status": "applied"}})
    pool = _pool([impl, test])
    router = _router(pool, verify_status="passed", proposal_ok=True)
    vr = {"status": "failed", "stderr_tail": "ImportError: cannot import name 'add' from 'calc'", "exit_code": 1}
    out = router.run(_sc_request(pool, "t1", vr))
    assert out.status == "recovered"
    # The implementation item (i1) was regenerated, and the TEST item (t1) was re-verified.
    assert router.patch_proposal_service.seen == ["i1"]
    assert router.auto_verification_service.verified == ["t1"]


def test_router_falls_back_to_self_correction_when_no_impl_link():
    # HTML deliverable: no python impl item -> router must fall back to self-correction on the test.
    test = _item("t1", item_type="verification", target_files=["tests/test_page.py"], metadata={"safe_apply": {"status": "applied"}})
    impl = _item("i1", target_files=["page.html"], metadata={"safe_apply": {"status": "applied"}})
    pool = _pool([impl, test])
    sc = _StubSelfCorrection()
    router = _router(pool, self_corr=sc)
    out = router.run(_sc_request(pool, "t1", {"status": "failed", "stderr_tail": "AssertionError"}))
    assert sc.called_with == ["t1"]
    assert out.reason == "stub_self_correction"


def test_router_fix_code_still_failing_falls_through_to_test_fix():
    impl = _item("i1", target_files=["calc.py"], metadata={"safe_apply": {"status": "applied"}}, risk_level="low")
    test = _item("t1", item_type="verification", target_files=["tests/test_calc.py"], metadata={"safe_apply": {"status": "applied"}})
    pool = _pool([impl, test])
    sc = _StubSelfCorrection()
    router = _router(pool, verify_status="failed", proposal_ok=True, self_corr=sc)
    vr = {"status": "failed", "stderr_tail": "ImportError: no name", "exit_code": 1}
    out = router.run(_sc_request(pool, "t1", vr))
    # Code fix attempted (i1 regenerated) but test still fails -> falls through to self-correction on t1.
    assert router.patch_proposal_service.seen == ["i1"]
    assert sc.called_with == ["t1"]
    assert "code_fix_result" in out.metadata
