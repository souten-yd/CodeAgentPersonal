# Atlas Vue Migration Plan

## Purpose
- Record PR-80 as the official architecture checkpoint for the Vue-based Atlas Next UI migration.
- Prevent UI development from diverging into another large, hard-to-operate dashboard.
- Preserve the existing final goal: fully autonomous code agent and self-improving CodeAgentPersonal / KasaneCore platform.
- Make Vue UI a replaceable supervision client, not the workflow authority.

## Final Goal Preserved
- Atlas remains a fully autonomous code agent target.
- Final workflow remains: goal → research → plan → implement → test → fix → PR.
- Self-improving CodeAgentPersonal / KasaneCore remains in scope.
- Vue UI is the visual supervision layer for autonomous execution, not a replacement for autonomous execution.

## Migration Timing
- PR-80 records the migration plan, architecture contract, and cleanup policy.
- Vue implementation starts after PR-80 in a separate PR series unless explicitly approved.
- Existing ui.html remains the default until Vue Atlas Next passes contract tests.
- Vue Atlas Next must initially be added as a parallel UI, for example:
  - web/atlas-next/
  - /atlas-next
  - or another explicitly documented static mount.
- Existing Atlas UI remains available as legacy until Vue reaches feature parity for the minimal workflow contract.

## Recommended PR Sequence
- PR-80: Record migration plan and autonomous-first UI cleanup policy.
- PR-81: Add backend-owned workflow_state / available_actions contract if not already complete.
- PR-82: Add Vue/Vite scaffold as a parallel read-only Atlas Next UI.
- PR-83: Add read-only workflow dashboard using backend workflow_state.
- PR-84: Add graphical plan timeline / plan item cards / risk badges / verification summary.
- PR-85: Add manual guarded actions through backend available_actions only.
- PR-86: Add diagnostics drawer for advanced information.
- PR-87: Run parity tests between classic ThinUI and Vue Atlas Next.
- PR-88: Make Vue Atlas Next default candidate behind a setting or route flag.
- PR-89: Keep classic Atlas UI as atlas-legacy.
- PR-90: Architecture review before removing or archiving legacy surfaces.

## Vue Stack Decision
- Use Vue 3 + Vite + TypeScript.
- Do not use Nuxt.
- Do not use Next.js.
- Do not add large component frameworks in the first Vue PR.
- Do not add Pinia until shared state complexity requires it.
- Do not add Vue Router until there are multiple stable routes.
- Prefer CSS/SVG for the initial graphical workflow.
- Reuse existing CSS variables where possible.

## Architecture
Backend owns:
- workflow_state
- phase
- status
- current item
- next action
- primary CTA
- available_actions
- blocked_reasons
- safety flags
- readiness policy
- artifact references
- approval summary
- verification summary

Frontend owns:
- rendering
- graphical layout
- user input collection
- POSTing user-selected actions
- displaying returned state
- opening/closing advanced and diagnostics drawers

Frontend must not own:
- execution eligibility
- dry-run-first decision
- confirmation gate logic
- risk classification authority
- auto-execution policy
- rollback policy
- retry policy
- patch generation policy
- workflow truth

## Vue Atlas Next Minimum UI
Visible by default:
- Goal / task
- Project path
- current phase
- current status
- strategic implementation plan summary
- current item
- next recommended action
- primary CTA
- stop / pause / emergency control
- approval summary
- risk summary
- verification summary
- artifacts summary
- progress timeline

Hidden by default:
- raw JSON
- run IDs
- pool IDs
- direct repo index controls
- direct repo context controls
- PlanItem Impact Map direct controls
- Context Refresh v2 direct controls
- Planner Packaging v2 direct controls
- Verification Recommendation direct controls
- direct Operator Loop internals
- manual queue/build/prepare/token internals
- debug-only panels

Always visible or easily accessible:
- Stop
- Pause, when available
- rollback/restore status, once implemented
- current risk level
- confirmation requirement
- dry-run requirement
- failure state
- manual approval requirement

## Migration Rules
- Add Vue as a parallel UI first.
- Do not rewrite ui.html in place.
- Do not add type="module" to existing classic Atlas scripts.
- Do not move existing execution logic into Vue.
- Do not duplicate workflow decision logic in Vue.
- Vue must consume backend workflow_state / available_actions.
- Vue must be able to run without depending on existing Atlas DOM IDs.
- Existing DOM IDs may remain for legacy UI tests.
- Deletion of old UI surfaces requires a later explicit deprecation PR.

## Default Switch Criteria
Vue Atlas Next may become default only when:
- backend workflow_state API is stable
- backend available_actions API is stable
- primary CTA is backend-derived
- safety flags are backend-derived
- dry-run-first and EXECUTE ONE ACTION gates remain enforced
- minimal workflow contract tests pass
- advanced and diagnostics surfaces remain accessible but hidden by default
- CLI can consume the same workflow contract
- legacy UI remains available for rollback

## Non-goals
- Do not implement full autonomous execution in the Vue migration PR.
- Do not hide safety-critical state.
- Do not remove advanced tools without replacement access.
- Do not remove diagnostics needed for debugging.
- Do not weaken manual approval requirements.
- No execution semantics change in PR-80.
