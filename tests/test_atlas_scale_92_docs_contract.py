from pathlib import Path
DOCS=['docs/atlas_scale_master_roadmap.md','docs/atlas_development_handoff.md','docs/atlas_unified_autopilot_checkpoint.md','docs/atlas_autopilot_current_status.md','docs/atlas_autopilot_scale_master_plan.md','docs/atlas_thinui_readiness.md','docs/atlas_autonomous_execution_readiness_policy.md','docs/atlas_vue_migration_plan.md']

def test_scale_92_docs_contract():
    text='\n'.join(Path(p).read_text(encoding='utf-8').lower() for p in DOCS)
    for s in ['pr-atlas-scale-92 completed','current implementation pr is pr-atlas-scale-93','level-0 completion checkpoint','readiness gate rollup','level-0 metadata-only readiness foundation','does not enable level-1 execution','does not authorize autonomous execution','runtime remains level 0 manual-only','pr-atlas-vue-01','existing ui.html remains default','backend workflow_state remains authoritative','fully_autonomous_code_agent','self_improving_codeagentpersonal_kasanecore']:
        assert s in text
    for s in ['pr-93 completed','vue implementation started in pr-92','level-1 execution enabled','autonomous execution enabled','automatic patch generation enabled','automatic patch apply enabled','automatic verification enabled','git operations enabled','execute-all enabled','auto-continue enabled','current next pr']:
        assert s not in text
