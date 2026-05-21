from pathlib import Path

def test_scale_90_docs_contract():
    docs = "\n".join(Path(p).read_text(encoding='utf-8') for p in [
      'docs/atlas_scale_master_roadmap.md','docs/atlas_development_handoff.md','docs/atlas_unified_autopilot_checkpoint.md','docs/atlas_autopilot_current_status.md','docs/atlas_autopilot_scale_master_plan.md','docs/atlas_thinui_readiness.md','docs/atlas_autonomous_execution_readiness_policy.md'])
    must=["PR-ATLAS-SCALE-90","Current implementation PR:\n- PR-ATLAS-SCALE-91","Next implementation PR:\n- PR-ATLAS-SCALE-92","remote git gate consolidation","metadata-only","does not run git commands","no git push","no git pull","no git clone","no git fetch","no git remote","does not create branches","does not create PRs","no direct merge","Automatic PR creation remains disabled","future explicit policy PR","does not authorize git operations","PR-89 added loop bound gate consolidation","Automatic loop execution remains disabled","Automatic retry remains disabled","Auto-continue remains disabled","Execute-all remains forbidden","Automatic execute remains disabled","Automatic command execution remains disabled","Automatic safe_apply remains disabled","Automatic patch generation remains disabled","Automatic patch apply remains disabled","Automatic restore remains disabled","Automatic rollback remains disabled","Autonomous execution remains disabled","Level 0 manual-only","Primary CTA remains single existing manual action only","out-of-order architecture checkpoint","fully autonomous code agent","Self-improving CodeAgentPersonal / KasaneCore"]
    for s in must: assert s in docs
    bad=["PR-91 completed","Current next PR"]
    for s in bad: assert s not in docs
