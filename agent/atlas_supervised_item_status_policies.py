from agent.atlas_supervised_item_status_schema import AtlasSupervisedItemStatusPolicy


def list_supervised_item_status_policies() -> list[AtlasSupervisedItemStatusPolicy]:
    return [
        AtlasSupervisedItemStatusPolicy(policy_id="supervised_item_status_v1",name="Supervised Item Status v1",description="Finalize supervised item status and next_action without side effects."),
        AtlasSupervisedItemStatusPolicy(policy_id="supervised_item_status_dry_run_v1",name="Supervised Item Status Dry Run v1",description="Transition preview only.",update_plan_item_status=False),
        AtlasSupervisedItemStatusPolicy(policy_id="strict_supervised_item_status_v1",name="Strict Supervised Item Status v1",description="Strict completion rules and manual fallback for ambiguity."),
    ]


def get_supervised_item_status_policy(policy_id: str) -> AtlasSupervisedItemStatusPolicy:
    for p in list_supervised_item_status_policies():
        if p.policy_id == policy_id:
            return p
    return list_supervised_item_status_policies()[0]
