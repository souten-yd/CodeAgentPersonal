from agent.atlas_patch_candidate_approval_schema import AtlasPatchCandidateApprovalPolicy


def list_patch_candidate_approval_policies() -> list[AtlasPatchCandidateApprovalPolicy]:
    return [
        AtlasPatchCandidateApprovalPolicy(policy_id="patch_candidate_approval_v1", name="Patch Candidate Approval", description="Manual approval for proposal_ready regenerated candidates."),
        AtlasPatchCandidateApprovalPolicy(policy_id="patch_candidate_reject_only_v1", name="Reject Only", description="Safety/UI test policy.", allow_safe_apply_handoff=False, notes=["approve_disabled"]),
        AtlasPatchCandidateApprovalPolicy(policy_id="strict_patch_candidate_approval_v1", name="Strict", description="Strict approval with lower limits.", max_patch_chars=12000, max_target_files=2, notes=["block_on_any_warning"]),
    ]


def get_patch_candidate_approval_policy(policy_id: str) -> AtlasPatchCandidateApprovalPolicy:
    for p in list_patch_candidate_approval_policies():
        if p.policy_id == policy_id:
            return p
    raise ValueError("policy_not_found")
