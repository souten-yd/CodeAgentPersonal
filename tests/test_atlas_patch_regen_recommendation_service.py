from types import SimpleNamespace

from agent.atlas_patch_regen_recommendation_policies import get_patch_regen_recommendation_policy
from agent.atlas_patch_regen_recommendation_service import AtlasPatchRegenRecommendationService


def _base():
    retry={"status":"not_retryable","retryability":{"reason":"deterministic_test_failure_or_code_error","deterministic_failure_detected":True},"failure_stop_suggestion":{"stop":True}}
    ver={"verification_result":{"status":"failed"},"failure_stop_suggestion":{"stop":True}}
    safe={"status":"applied"}
    handoff={"target_files":["src/a.py"],"patch":"diff --git a"}
    item=SimpleNamespace(target_files=["src/a.py"], metadata={})
    return retry,ver,safe,handoff,item


def test_service_importable():
    assert AtlasPatchRegenRecommendationService is not None


def test_not_retryable_unknown_failed_not_recommended():
    svc=AtlasPatchRegenRecommendationService()
    retry,ver,safe,handoff,item=_base()
    retry["retryability"]={"reason":"failed_but_not_classified_retryable","deterministic_failure_detected":False}
    out=svc.assess(retry,ver,safe,handoff,item,get_patch_regen_recommendation_policy("patch_regen_recommendation_v1"))
    assert out["status"]=="not_recommended"


def test_not_retryable_deterministic_recommendation_ready():
    svc=AtlasPatchRegenRecommendationService()
    out=svc.assess(*_base(),get_patch_regen_recommendation_policy("patch_regen_recommendation_v1"))
    assert out["status"]=="recommendation_ready"


def test_stopped_requires_evidence():
    svc=AtlasPatchRegenRecommendationService(); retry,ver,safe,handoff,item=_base(); retry["status"]="stopped"; retry["retryability"]={"reason":"manual_required","deterministic_failure_detected":False}
    out=svc.assess(retry,ver,safe,handoff,item,get_patch_regen_recommendation_policy("patch_regen_recommendation_v1"))
    assert out["status"]=="not_recommended"


def test_stopped_with_evaluator_stop_and_deterministic_ready():
    svc=AtlasPatchRegenRecommendationService(); retry,ver,safe,handoff,item=_base(); retry["status"]="stopped"; retry["note"]="evaluator_stop"
    out=svc.assess(retry,ver,safe,handoff,item,get_patch_regen_recommendation_policy("patch_regen_recommendation_v1"))
    assert out["status"]=="recommendation_ready"


def test_target_path_safety_blocked_cases():
    svc=AtlasPatchRegenRecommendationService(); retry,ver,safe,handoff,item=_base(); handoff["target_files"]=["../x"]
    assert svc.assess(retry,ver,safe,handoff,item,get_patch_regen_recommendation_policy("patch_regen_recommendation_v1"))["status"]=="blocked"
    handoff["target_files"]=["/abs/path"]
    assert svc.assess(retry,ver,safe,handoff,item,get_patch_regen_recommendation_policy("patch_regen_recommendation_v1"))["status"]=="blocked"
    handoff["target_files"]=[]; item.target_files=[]
    assert svc.assess(retry,ver,safe,handoff,item,get_patch_regen_recommendation_policy("patch_regen_recommendation_v1"))["status"]=="blocked"


def test_target_path_safety_valid_relative_ok():
    svc=AtlasPatchRegenRecommendationService(); retry,ver,safe,handoff,item=_base(); handoff["target_files"]=["src/a.py","web/js/a.js"]
    assert svc.assess(retry,ver,safe,handoff,item,get_patch_regen_recommendation_policy("patch_regen_recommendation_v1"))["status"]=="recommendation_ready"
