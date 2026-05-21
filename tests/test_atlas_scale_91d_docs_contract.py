from pathlib import Path

DOCS = [
    "docs/atlas_scale_master_roadmap.md",
    "docs/atlas_development_handoff.md",
    "docs/atlas_unified_autopilot_checkpoint.md",
    "docs/atlas_autopilot_current_status.md",
    "docs/atlas_autopilot_scale_master_plan.md",
    "docs/atlas_thinui_readiness.md",
    "docs/atlas_autonomous_execution_readiness_policy.md",
    "docs/atlas_self_development_rules.md",
]


def test_scale_91d_docs_contract():
    text = "\n".join(Path(p).read_text(encoding="utf-8").lower() for p in DOCS)

    required = [
        "pr-atlas-scale-91d",
        "pr-atlas-scale-92: readiness gate rollup / level-0 completion checkpoint",
        "pr-atlas-scale-93: level-1 guarded execution design checkpoint",
        "self_improvement_scope is self_improving_codeagentpersonal_kasanecore",
        "final_goal remains fully_autonomous_code_agent",
        "vue implementation has not started in this pr series",
        "level 0 manual-only",
    ]
    for s in required:
        assert s in text

    forbidden = [
        "pr-atlas-scale-92 completed",
        "vue implementation started",
    ]
    for s in forbidden:
        assert s not in text
