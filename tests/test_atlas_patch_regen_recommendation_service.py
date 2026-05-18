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

from agent.atlas_patch_regen_recommendation_schema import AtlasPatchRegenRecommendationRequest, AtlasPatchRegenRecommendationResult


def _result(**overrides):
    payload = SimpleNamespace(target_files=["src/a.py"], changed_files=["src/a.py"])
    data = dict(
        pool_id="p1",
        item_id="i1",
        run_id="run1",
        handoff_id="handoff_abc123",
        safe_apply_execution_id="safehandoff_abc123",
        verification_run_id="verifyhandoff_abc123",
        supervised_retry_run_id="retryhandoff_abc123",
        recommendation_run_id="regenrec_abc123",
        policy_id="patch_regen_recommendation_v1",
        patch_regen_policy_id="supervised_patch_regen_v1",
        status="recommendation_ready",
        recommended_payload=payload,
        eligibility={"reason":"eligible_retry_terminal_failure"},
        created_at="2026-05-18T00:00:00+00:00",
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def test_item_metadata_patch_regen_recommendations_appended():
    svc = AtlasPatchRegenRecommendationService()
    item = SimpleNamespace(metadata={})
    handoff = {"metadata": {}}
    res = _result()

    svc._update_metadata(None, item, handoff, res)

    assert item.metadata["patch_regen_recommendations"] == [
        {
            "recommendation_run_id": "regenrec_abc123",
            "handoff_id": "handoff_abc123",
            "safe_apply_execution_id": "safehandoff_abc123",
            "verification_run_id": "verifyhandoff_abc123",
            "supervised_retry_run_id": "retryhandoff_abc123",
            "status": "recommendation_ready",
            "reason": "eligible_retry_terminal_failure",
            "patch_regen_policy_id": "supervised_patch_regen_v1",
            "target_files": ["src/a.py"],
            "created_at": "2026-05-18T00:00:00+00:00",
            "result_path": "ca_data/atlas/patch_regen_recommendations/p1/regenrec_abc123.json",
        }
    ]


def test_item_metadata_latest_patch_regen_recommendation_id_set():
    svc = AtlasPatchRegenRecommendationService()
    item = SimpleNamespace(metadata={})
    svc._update_metadata(None, item, {"metadata": {}}, _result())
    assert item.metadata["latest_patch_regen_recommendation_id"] == "regenrec_abc123"


def test_item_safe_apply_handoff_entry_updated():
    svc = AtlasPatchRegenRecommendationService()
    item = SimpleNamespace(metadata={"safe_apply_handoffs": [{"handoff_id": "handoff_other"}, {"handoff_id": "handoff_abc123"}]})
    svc._update_metadata(None, item, {"metadata": {}}, _result())
    assert item.metadata["safe_apply_handoffs"] == [
        {"handoff_id": "handoff_other"},
        {
            "handoff_id": "handoff_abc123",
            "patch_regen_recommended": True,
            "patch_regen_reason": "eligible_retry_terminal_failure",
            "last_patch_regen_recommendation_id": "regenrec_abc123",
        },
    ]


def test_item_patch_safe_apply_auto_safe_apply_not_overwritten():
    svc = AtlasPatchRegenRecommendationService()
    original_patch = {"diff": "keep"}
    original_safe_apply = {"status": "keep"}
    original_auto_safe_apply = {"enabled": False}
    item = SimpleNamespace(metadata={"patch": original_patch, "safe_apply": original_safe_apply, "auto_safe_apply": original_auto_safe_apply})

    svc._update_metadata(None, item, {"metadata": {}}, _result())

    assert item.metadata["patch"] is original_patch
    assert item.metadata["safe_apply"] is original_safe_apply
    assert item.metadata["auto_safe_apply"] is original_auto_safe_apply
    assert "patch_regen_candidates" not in item.metadata


def test_eligibility_contains_retry_status_verification_status_retry_reason():
    svc = AtlasPatchRegenRecommendationService()
    out = svc.assess(*_base(), get_patch_regen_recommendation_policy("patch_regen_recommendation_v1"))
    assert out["retry_status"] == "not_retryable"
    assert out["verification_status"] == "failed"
    assert out["retry_reason"] == "deterministic_test_failure_or_code_error"
    assert out["target_files"] == ["src/a.py"]
    assert out["target_files_validated"] is True
    assert out["deterministic_failure_detected"] is True
    assert out["transient_failure_detected"] is False
    assert out["evidence_sources"] == ["retryability", "verification_logs"]
    assert out["reason"] == "eligible_retry_terminal_failure"
    assert out["status"] == "recommendation_ready"
    assert out["errors"] == []
    assert out["warnings"] == []


def test_markdown_contains_retry_status_verification_status_retry_reason_target_files(tmp_path):
    svc = AtlasPatchRegenRecommendationService(storage=SimpleNamespace(root_dir=tmp_path))
    result = AtlasPatchRegenRecommendationResult(
        pool_id="p1",
        item_id="i1",
        run_id="run1",
        handoff_id="handoff_abc123",
        safe_apply_execution_id="safehandoff_abc123",
        verification_run_id="verifyhandoff_abc123",
        supervised_retry_run_id="retryhandoff_abc123",
        recommendation_run_id="regenrec_abc123",
        policy_id="patch_regen_recommendation_v1",
        patch_regen_policy_id="supervised_patch_regen_v1",
        status="blocked",
        recommended_payload=None,
        eligibility={
            "reason": "safe_apply_not_applied",
            "retry_status": "not_retryable",
            "verification_status": "failed",
            "retry_reason": "deterministic_test_failure_or_code_error",
            "target_files": ["src/a.py"],
        },
    )

    svc._save(result)

    md = (tmp_path / "atlas" / "patch_regen_recommendations" / "p1" / "regenrec_abc123.md").read_text(encoding="utf-8")
    assert "- retry_status: not_retryable" in md
    assert "- verification_status: failed" in md
    assert "- retry_reason: deterministic_test_failure_or_code_error" in md
    assert "- target_files: ['src/a.py']" in md


def test_payload_truncation_fields_recorded():
    svc = AtlasPatchRegenRecommendationService()
    retry, ver, safe, handoff, item = _base()
    retry["bounded_retry_result"] = {"log": "x" * 200}
    policy = get_patch_regen_recommendation_policy("patch_regen_recommendation_v1").model_copy(update={"max_payload_chars": 100})
    elig = svc.assess(retry, ver, safe, handoff, item, policy)

    payload = svc.build_payload(
        AtlasPatchRegenRecommendationRequest(pool_id="p1", item_id="i1", handoff_id="handoff_abc123", safe_apply_execution_id="safehandoff_abc123", verification_run_id="verifyhandoff_abc123", supervised_retry_run_id="retryhandoff_abc123"),
        "regenrec_abc123",
        retry,
        ver,
        safe,
        handoff,
        item,
        elig,
        policy,
    )

    assert payload.bounded_retry_result == {"truncated": True}
    assert payload.metadata["payload_truncated"] is True
    assert payload.metadata["payload_truncation_fields"] == ["bounded_retry_result"]
    assert payload.metadata["payload_chars"] > 0
