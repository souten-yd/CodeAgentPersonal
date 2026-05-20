from agent.atlas_verification_recommendation_schema import AtlasVerificationRecommendationRequest
from agent.atlas_verification_recommendation_service import AtlasVerificationRecommendationService
import agent.atlas_verification_recommendation_service as mod


def test_uses_provided_planner_packaging_v2(tmp_path):
    svc = AtlasVerificationRecommendationService(data_root=tmp_path)
    req = AtlasVerificationRecommendationRequest(project_path=str(tmp_path), planner_packaging_v2={"status":"available","impacted_files":["a.py","a.py"],"related_tests":["t1"],"recommended_commands":["pytest -q"],"manual_verification_steps":["check ui"],"ci_selection_hints":[{"x":1}],"evidence":[{"item_id":"i1"}],"confidence":"medium"})
    out = svc.recommend(req)
    assert out.status in {"available","partial"}
    assert out.impacted_files == ["a.py"]
    assert out.metadata["commands_are_suggestions_only"] is True


def test_missing_packaging_non_blocking(tmp_path):
    out = AtlasVerificationRecommendationService(tmp_path).recommend(AtlasVerificationRecommendationRequest(project_path=str(tmp_path), include_planner_packaging_v2=False))
    assert out.status == "missing"
    assert "planner_packaging_v2_missing" in out.warnings


def test_build_when_missing(tmp_path, monkeypatch):
    class Fake:
        def __init__(self, data_root): pass
        def build_package(self, req):
            class R:
                def model_dump(self): return {"status":"available","related_tests":["t"]}
            return R()
    monkeypatch.setattr(mod, 'AtlasPlannerPackagingV2Service', Fake)
    out = AtlasVerificationRecommendationService(tmp_path).recommend(AtlasVerificationRecommendationRequest(project_path=str(tmp_path)))
    assert out.related_tests == ["t"]


def test_build_failure_non_blocking(tmp_path, monkeypatch):
    class Fake:
        def __init__(self, data_root): pass
        def build_package(self, req): raise RuntimeError('boom')
    monkeypatch.setattr(mod, 'AtlasPlannerPackagingV2Service', Fake)
    out = AtlasVerificationRecommendationService(tmp_path).recommend(AtlasVerificationRecommendationRequest(project_path=str(tmp_path)))
    assert out.status == 'missing'
    assert 'planner_packaging_v2_build_failed' in out.warnings


def test_item_filter_warning_and_limits(tmp_path):
    data={"status":"available","ci_selection_hints":[{"item_id":"x","k":str(i)} for i in range(25)],"evidence":[{"item_id":"x","k":str(i)} for i in range(100)],"impacted_files":[f"f{i}" for i in range(70)],"related_tests":[f"t{i}" for i in range(40)],"recommended_commands":[f"c{i}" for i in range(20)],"manual_verification_steps":[f"m{i}" for i in range(30)]}
    out=AtlasVerificationRecommendationService(tmp_path).recommend(AtlasVerificationRecommendationRequest(project_path=str(tmp_path), item_id='z', planner_packaging_v2=data))
    assert 'item_specific_recommendation_unavailable' in out.warnings
    assert len(out.impacted_files)==50 and len(out.related_tests)==30 and len(out.recommended_commands)==10 and len(out.manual_verification_steps)==20 and len(out.ci_selection_hints)==20 and len(out.evidence)==80
