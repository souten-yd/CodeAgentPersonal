from agent.atlas_verification_recommendation_handoff_schema import AtlasVerificationRecommendationHandoffRequest
from agent.atlas_verification_recommendation_handoff_service import AtlasVerificationRecommendationHandoffService


def test_handoff_uses_provided_recommendation_and_flags(tmp_path):
    svc = AtlasVerificationRecommendationHandoffService(tmp_path)
    res = svc.build_handoff(AtlasVerificationRecommendationHandoffRequest(project_path='.', verification_recommendation={"status":"ok","confidence":"high","impacted_files":["a"],"related_tests":["t"],"recommended_commands":["pytest"],"manual_verification_steps":["check"]}))
    assert res.status == 'ok'
    assert 'Manual approval only' in res.approval_summary
    assert res.metadata['manual_approval_only'] is True
    assert res.handoff_metadata['executed'] is False


def test_handoff_missing_non_blocking_and_size_limits(tmp_path):
    svc = AtlasVerificationRecommendationHandoffService(tmp_path)
    payload = {"impacted_files":[str(i) for i in range(50)],"related_tests":[str(i) for i in range(30)],"recommended_commands":[str(i) for i in range(10)],"manual_verification_steps":[str(i) for i in range(20)]}
    res = svc.build_handoff(AtlasVerificationRecommendationHandoffRequest(project_path='.', verification_recommendation=payload, item_id='i1'))
    assert len(res.impacted_files) == 20
    assert len(res.related_tests) == 15
    assert len(res.recommended_commands) == 5
    assert len(res.manual_verification_steps) == 10
