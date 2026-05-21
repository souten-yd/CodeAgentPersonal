from pathlib import Path

DOCS = [
    'docs/atlas_scale_master_roadmap.md','docs/atlas_development_handoff.md','docs/atlas_unified_autopilot_checkpoint.md',
    'docs/atlas_autopilot_current_status.md','docs/atlas_autopilot_scale_master_plan.md','docs/atlas_thinui_readiness.md',
    'docs/atlas_autonomous_execution_readiness_policy.md','docs/atlas_self_development_rules.md'
]


def test_scale_91b_docs_contract():
    text='\n'.join(Path(p).read_text(encoding='utf-8').lower() for p in DOCS)
    required=[
        'pr-atlas-scale-91b','pr-atlas-scale-92: readiness gate rollup / level-0 completion checkpoint','pr-atlas-scale-93: level-1 guarded execution design checkpoint',
        'self-improvement gate integration wiring','manifest contract drift','self_improvement_scope is self_improving_codeagentpersonal_kasanecore',
        'final_goal remains fully_autonomous_code_agent','invalid or unreadable referenced manifests block self-improvement readiness',
        'does not modify code','does not generate patches','does not apply patches','does not run safe_apply','does not run tests or verification','does not run git commands',
        'autonomous self-improvement remains disabled','automatic self-modification remains disabled','strict-gate by default',
        'does not authorize automatic execution','does not authorize patch apply','does not authorize git operations',
        'automatic command execution','automatic patch generation','automatic patch apply','automatic safe_apply','automatic verification','automatic restore','automatic rollback','automatic loop execution','automatic retry',
        'auto-continue remains disabled','execute-all remains forbidden','autonomous execution remains disabled','level 0 manual-only','single existing manual action only'
    ]
    for s in required:
        assert s in text
    forbidden=['autonomous self-improvement enabled','self-modification automatic','patch generation automatic','patch apply automatic','pr-atlas-scale-92 completed','current next pr']
    for s in forbidden:
        assert s not in text
