from agent.atlas_multi_item_supervised_status_schema import AtlasMultiItemSupervisedStatusPolicy


def list_multi_item_supervised_status_policies():
    return [
        AtlasMultiItemSupervisedStatusPolicy(policy_id="multi_item_supervised_status_v1", name="Multi-item supervised status", description="Refresh and aggregate supervised item statuses."),
        AtlasMultiItemSupervisedStatusPolicy(policy_id="multi_item_supervised_status_dry_run_v1", name="Multi-item supervised status (dry-run)", description="Preview agenda only.", update_item_status=False),
        AtlasMultiItemSupervisedStatusPolicy(policy_id="strict_multi_item_supervised_status_v1", name="Strict multi-item supervised status", description="Strict selectable rules.", max_items=50),
    ]


def get_multi_item_supervised_status_policy(policy_id: str):
    for p in list_multi_item_supervised_status_policies():
        if p.policy_id == policy_id:
            return p
    raise ValueError(f"unknown policy_id: {policy_id}")
