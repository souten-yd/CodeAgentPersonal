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
- PR-ATLAS-SCALE-80: planning checkpoint (docs/manifest/tests only; migration plan + autonomous-first UI policy).
- PR-ATLAS-SCALE-92: Level-0 readiness completion checkpoint; opened Vue work after merge.
- PR-ATLAS-VUE-01: Add parallel Vue/Vite Atlas Next read-only shell.
- PR-ATLAS-VUE-01B: Docs/test contract hardening for the parallel read-only shell.
- PR-ATLAS-VUE-02: Harden read-only workflow_state adapter and defer static mount.
- PR-ATLAS-VUE-03: Next UI track for read-only workflow cards / backend state parity hardening.

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


## PR-ATLAS-SCALE-92 Level-0 Completion Checkpoint
- Historical checkpoint: PR-ATLAS-VUE-02 completed safe static serving / read-only workflow_state adapter hardening; current UI track is PR-ATLAS-VUE-03: Read-only workflow cards / backend state parity hardening.
- PR-ATLAS-SCALE-92 completed the Level-0 metadata-only readiness foundation via readiness gate rollup.
- Level-0 completion checkpoint is metadata-only and does not enable Level-1 execution.
- Level-0 completion does not authorize autonomous execution, patch generation/apply, safe_apply, verification execution, rollback/restore, or git operations.
- Runtime remains Level 0 manual-only.
- Current implementation PR is PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint.
- Vue implementation is allowed only after PR-92 is merged and has not started in PR-92.
- Separate UI track after merge: PR-ATLAS-VUE-01 read-only parallel UI track; existing ui.html remains default and backend workflow_state remains authoritative.
- PR-80 remains Vue migration planning checkpoint and did not add Vue runtime code.
- automatic command execution disabled; automatic verification disabled; automatic patch generation disabled; automatic patch apply disabled; automatic safe_apply disabled; automatic rollback disabled; automatic restore disabled; automatic loop execution disabled; automatic retry disabled; auto-continue disabled; execute-all forbidden; autonomous execution disabled; autonomous self-improvement disabled; remote git disabled; direct merge forbidden; primary CTA remains single existing manual action only.

- PR-ATLAS-VUE-01 is a separate UI track and starts only after PR-ATLAS-SCALE-92.
- Vue is read-only and not default in PR-ATLAS-VUE-01.
- Vue available actions are metadata only in this track.
- Vue does not call mutation endpoints in this track.
- Vue does not compute execution eligibility.
- PR-80 was planning only and did not add Vue runtime code.

## PR-ATLAS-VUE-04 Decision Update
- PR-ATLAS-VUE-04 completed the safe backend GET adapter/static mount decision checkpoint.
- Safe GET adapter decision: deferred because no stable dedicated read-only workflow_state + available_actions endpoint contract is finalized yet.
- Static mount decision: deferred because committed dist/static artifact strategy for `/atlas-next` is not locked yet.
- Existing `ui.html` remains default; Vue Next remains parallel, replaceable, read-only, and not default.
- Backend workflow state remains authoritative. Vue does not compute execution eligibility.
- Vue available actions remain metadata-only (`readOnly:true`, `enabled:false`).
- Vue does not call mutation endpoints.
- Current automation track remains `PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint`.
- Next UI track: `PR-ATLAS-VUE-05: Define stable read-only workflow_state backend contract` (with parity tests/visual refinement after contract lock).
- `/atlas-next` mount remains future work until dist/static strategy is locked.
- Final goal remains `fully_autonomous_code_agent`; self-improving CodeAgentPersonal / KasaneCore remains in scope.
