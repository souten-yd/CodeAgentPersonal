# Atlas Roadmap Index

This index maps the active Atlas planning documents to their ownership roles so
future automation PRs can verify the current milestone without copying active
PR pointers into new handoff documents.

## Current Position

- Completed automation PR: PR-ATLAS-SCALE-116
- Current / next automation track: PR-ATLAS-SCALE-117
- Completed phase: Readiness Metadata Review Phase
- Active phase: Level-1 Advancement Preparation
- Current runtime level: level_0_manual_only
- Target runtime level: level_1_guarded_single_step
- Final goal: fully_autonomous_code_agent
- Self-improvement goal: self_improving_codeagentpersonal_kasanecore

## Canonical Documents

| Area | Canonical file | Role |
| --- | --- | --- |
| Human roadmap | `docs/atlas_scale_master_roadmap.md` | PR-by-PR implementation plan and current automation pointer. |
| Safety policy | `docs/atlas_autonomous_execution_readiness_policy.md` | Runtime level, forbidden capabilities, and level-advancement gates. |
| Machine manifest | `docs/atlas_automation_phase_manifest.json` | Machine-readable current phase, planned PRs, and anti-drift flags. |
| UI surface manifest | `web/atlas_ui_surface_manifest.json` | UI safety flags, default surface metadata, and Vue/non-execution contracts. |
| Unified autopilot plan | `docs/atlas_unified_autopilot_master_plan.md` | Historical and architectural Atlas pipeline direction. |
| Unified checkpoint | `docs/atlas_unified_autopilot_checkpoint.md` | Historical checkpoint notes retained for context, not the active automation pointer. |
| Vue / Atlas UI notes | `docs/agent_guided_workflow_integration.md` | Vue/legacy UI migration notes and Atlas Workbench history. |
| Readiness validator | `scripts/validate_atlas_automation_plan.py` | Local contract checker for roadmap, policy, manifest, and UI safety alignment. |

## Completed And Next Milestones

SCALE-113 through SCALE-116 are completed within Level-1 Advancement Preparation:

- SCALE-113 consolidated the roadmap, removed duplicate planning docs, added the phase manifest, and added the validator.
- SCALE-114 added advisory readiness rollup and gate evidence summary.
- SCALE-115 added dry-run artifact schema v1.
- SCALE-116 added the verification allowlist resolver as metadata-only infrastructure.

The next unfinished milestone is SCALE-117: add a dry-run-only backend endpoint
skeleton. That PR must remain non-mutating and must not add patch apply, git
operations, autonomous loop behavior, or execution capability.

## Path To Full Automation

1. SCALE-117 through SCALE-120 finish Level-1 readiness evidence while runtime remains `level_0_manual_only`.
2. SCALE-121 through SCALE-127 introduce disabled/guarded single-step infrastructure and only transition runtime level at SCALE-127 if all gates pass.
3. SCALE-128 through SCALE-135 build patch, branch, and draft PR capability in explicitly staged steps.
4. SCALE-136 through SCALE-139 introduce bounded autonomous loop policy and checkpoints.
5. SCALE-140 through SCALE-146 introduce self-improvement proposal, preview, guarded apply, draft PR, and final Level-4 checkpoint.

## Recommended Next PRs

1. PR-ATLAS-SCALE-117: dry-run-only backend endpoint skeleton; no mutation, no patch apply, no git.
2. PR-ATLAS-SCALE-118: dry-run result artifact capture; capture real dry-run output only.
3. PR-ATLAS-SCALE-119: approval token backend contract; token contract only, no autonomous loop.
4. PR-ATLAS-SCALE-120: UI dry-run result viewer; Vue remains display-only and non-authoritative.
5. PR-ATLAS-SCALE-121: disabled single allowlisted command runner; default disabled, allowlisted only.

## Safety Boundary

Until an explicit transition PR changes these contracts:

- `ui.html` default behavior must be preserved.
- Vue must remain non-default, non-authoritative, display-only, and without execution capability.
- Backend workflow state remains authoritative.
- Runtime remains `level_0_manual_only`.
- No autonomous mutation, autonomous execution, self-modification, patch apply, raw source serving, or fallback/redirect safety bypass is allowed.
- Server startup must not run `npm build` or any equivalent frontend build.
