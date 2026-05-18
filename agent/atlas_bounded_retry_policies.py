from __future__ import annotations

from agent.atlas_bounded_retry_schema import AtlasBoundedRetryPolicy


def list_bounded_retry_policies() -> list[AtlasBoundedRetryPolicy]:
    base = AtlasBoundedRetryPolicy(
        policy_id="verification_retry_v1",
        name="Verification Retry v1",
        description="Retry verification only for transient/environment failures.",
        retryable_error_patterns=["timeout","timed out","connection reset","connection refused","temporary failure","resource temporarily unavailable","runner unavailable","test runner unavailable","pytest collection failed due to missing cache","file lock","permission denied","interrupted","flaky","infrastructure","environment"],
        non_retryable_error_patterns=["assert","AssertionError","SyntaxError","ImportError","ModuleNotFoundError","NameError","TypeError","ValueError","failed test","test failed","expected","actual"],
    )
    dry = base.model_copy(update={"policy_id":"verification_retry_dry_run_v1","name":"Verification Retry Dry Run v1","description":"Eligibility-only dry run for bounded retry.","allow_verification_rerun":False})
    strict = base.model_copy(update={"policy_id":"verification_retry_strict_v1","name":"Verification Retry Strict v1","description":"Single attempt strict retry policy.","max_attempts":1,"retryable_error_patterns":["timeout","timed out","runner unavailable","test runner unavailable"]})
    return [base, dry, strict]


def get_bounded_retry_policy(policy_id: str) -> AtlasBoundedRetryPolicy:
    for p in list_bounded_retry_policies():
        if p.policy_id == policy_id:
            return p
    return list_bounded_retry_policies()[0]
