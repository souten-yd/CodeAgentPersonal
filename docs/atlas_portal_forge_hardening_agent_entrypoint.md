# Atlas Portal + Model Forge Hardening — Agent Entrypoint

Use this file as the Goal-mode entrypoint for post-PFG hardening.

## Goal prompt

```text
Read AGENTS.md first.

Continue the Atlas Portal + Model Forge Hardening track.

Read:
1. docs/atlas_portal_forge_current_status.md
2. docs/atlas_portal_forge_hardening_current_status.md
3. docs/atlas_portal_forge_hardening_plan.md
4. docs/atlas_portal_forge_hardening_test_plan.md

Start from the current PFH package selected by docs/atlas_portal_forge_hardening_current_status.md.

Do not restart Portal or Forge from scratch. PFG-0..PFG-38 created the foundation.

Implement PFH packages sequentially:
PFH-1 benchmark preset identity and execution semantics.
PFH-2 OpenRouter catalog product integration.
PFH-3 provider configured state vs runtime readiness.
PFH-4 ForgeModelExecutionBridge shadow-first.
PFH-5 real cutover and rollback.
PFH-6 real evidence through Forge provider/preset runner.
PFH-7 actual Portal runtime replay for Capsule evidence.
PFH-8 guarded Candidate-to-Proposal handoff.

Use real code inspection and tests. Use LLMs for review/evaluation only as advisory unless paired with mechanical or runtime evidence.

Do not claim:
- OpenRouter live evidence without FORGE_OPENROUTER_LIVE_SMOKE=1 and OPENROUTER_API_KEY.
- Portal runtime evidence without an actual Portal/Play runtime run.
- production cutover without the real Atlas model execution bridge returning Forge output.
- legacy retirement while consumers remain.
- unavailable checks as passed.

After each package:
- update docs/atlas_portal_forge_hardening_current_status.md;
- record exact commands and results;
- advance to the next package only when acceptance criteria pass.
```

## First implementation target

PFH-1.

Focus files:

```text
agent/model_forge/benchmark_presets.py
app/api/forge.py
agent/model_forge/forge_service.py
web/js/forge.js
tests/test_model_forge_benchmark_presets.py
tests/test_forge_benchmark_render.py
```

Expected PFH-1 outcome:

```text
The Forge benchmark UI derives primary presets from real backend preset IDs or family aliases.
Multi-selected presets are sent to backend or visibly unsupported.
Depth is implemented or visibly unavailable.
Tests fail before the fix and pass after the fix.
```
