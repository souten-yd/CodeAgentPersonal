- PR-ATLAS-SCALE-97 completed.
- Completed automation PR: PR-ATLAS-SCALE-97.
- Current automation track: PR-ATLAS-SCALE-98.
- Next automation track: PR-ATLAS-SCALE-98.
- next work is PR-ATLAS-SCALE-98.
- SCALE-98 scope remains gate filtering/grouping and UX refinement, not execution enable.
- Level-1 execution remains disabled.
- Runtime remains level_0_manual_only.
- Autonomous execution remains disabled.
- Vue execution capability remains none.
- Backend workflow_state remains authoritative.

- PR-ATLAS-VUE-19 completed: Execution safety / non-execution boundary review UI (display-only metadata).
- PR-ATLAS-VUE-20 completed: Default-readiness preflight / route selection guard review (display-only metadata; no default switch).
## Current Atlas Vue UI Track State

- Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-21
- Current UI track: Vue defaultization complete
- Planned UI track: return to PR-ATLAS-SCALE-98 automation track
- Current automation track: PR-ATLAS-SCALE-98
- Next automation track: PR-ATLAS-SCALE-98
- SCALE-94 is disabled backend skeleton candidate only
- `/` is guarded Atlas Next default only when validated dist passes
- invalid/missing Vue dist falls back safely to legacy UI
- legacy UI remains available via /ui/
- `/atlas-next` remains guarded preview route
- backend workflow_state remains authoritative
- runtime remains level_0_manual_only
- Vue execution capability remains none
- VUE21 completed default-enable only, not execution-enable
- Level-1 execution remains disabled
- next work is PR-ATLAS-SCALE-98

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
- Historical note: Existing ui.html remained the default until Vue Atlas Next passed contract tests; this was completed by PR-ATLAS-VUE-21 guarded defaultization.
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
- Next UI track: `PR-ATLAS-VUE-07: Vue read-only parity tests / visual refinement` (followed by PR-ATLAS-VUE-08 safe static mount/dist strategy).
- `/atlas-next` mount remains future work until dist/static strategy is locked.
- Final goal remains `fully_autonomous_code_agent`; self-improving CodeAgentPersonal / KasaneCore remains in scope.


## PR-ATLAS-VUE-06 Contract Binding Checkpoint
- PR-ATLAS-VUE-06 completed: Vue read-only adapter is bound to `GET /api/atlas/workflow-state/read-only`.
- Adapter remains GET-only and fallback-safe: invalid/non-OK responses use a placeholder read-only snapshot fallback.
- `available_actions` remain metadata only; all actions are disabled/read-only in Vue.
- Backend workflow state remains authoritative; Vue does not compute execution eligibility and does not call mutation endpoints.
- Vue default route is guarded: `/` serves Atlas Next only when validated dist is available; otherwise it fail-closed falls back to legacy UI; existing `ui.html` remains default.
- Static mount remains deferred while dist/static artifact strategy is not locked.
- Automation track remains `PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint`.
- Final goal remains `fully_autonomous_code_agent` and self-improvement scope remains `self_improving_codeagentpersonal_kasanecore`.
- PR-ATLAS-VUE-05 remains a completed prerequisite contract-definition checkpoint.

## PR-ATLAS-VUE-07 Completion Update
- PR-ATLAS-VUE-07 completed: Vue read-only parity tests / visual refinement.
- Vue default route is guarded: `/` serves Atlas Next only when validated dist is available; otherwise it fail-closed falls back to legacy UI/no execution; existing ui.html remains default.
- Vue adapter remains GET-only to GET /api/atlas/workflow-state/read-only and fallback remains active.
- available_actions are metadata only; every available action remains disabled/read-only.
- Backend workflow state remains authoritative.
- Vue does not compute execution eligibility.
- Vue does not call mutation endpoints.
- Static mount remains deferred because dist/static artifact strategy is not locked.
- PR-ATLAS-SCALE-93 remains automation track current.
- Current UI track: PR-ATLAS-VUE-08: Safe static mount/dist strategy.
- Next UI track candidate: PR-ATLAS-VUE-09: Atlas Next read-only smoke route / build artifact policy.
- Final goal remains fully_autonomous_code_agent.
- Self-improving CodeAgentPersonal / KasaneCore remains in scope.


## Safe static mount / dist strategy (PR-ATLAS-VUE-08)
- Vue Next source remains under `web/atlas-next/`.
- Vue Next production artifacts are built into `web/atlas-next/dist/` via:
  - `cd web/atlas-next`
  - `npm install`
  - `npm run build`
- `dist/` is a build artifact, not workflow truth and not source of truth.
- Raw Vite source files must not be served as production UI.
- Existing `ui.html` remains the default UI for `/` and `/ui.html`.
- Any future Vue preview route must be `/atlas-next` only, read-only only, built-dist only, not default, with no execution controls and no mutation endpoint calls.
- If dist is absent at runtime, future `/atlas-next` must fail safely (defer/404) rather than exposing source files.
- Static mount decision in this PR remains deferred; implementation is carried by PR-ATLAS-VUE-09 smoke route/build artifact policy.
- Vue default route is guarded: `/` serves Atlas Next only when validated dist is available; otherwise it fail-closed falls back to legacy UI, backend workflow state remains authoritative, available_actions are metadata only, and Vue does not compute execution eligibility.

## PR-ATLAS-VUE-08B docs pointer contract
- PR-ATLAS-VUE-08 is completed: Safe static mount/dist strategy.
- Current UI track is PR-ATLAS-VUE-09: Atlas Next read-only smoke route / build artifact policy.
- Next UI track is PR-ATLAS-VUE-11: Atlas Next preview route observability / fallback hardening.
- Current automation track remains PR-ATLAS-SCALE-94: Level-1 guarded execution design checkpoint (not completed here).
- Dist strategy is defined as `dist_required` with production artifacts in `web/atlas-next/dist`.
- Raw Vite source must not be served as production UI.
- Static mount remains deferred until VUE-09 / smoke route policy.


## Atlas Next read-only smoke route / build artifact policy
- PR-ATLAS-VUE-09 defines policy/tests only; `/atlas-next` stays unmounted by default in this PR.
- Vue Next source of truth for implementation remains `web/atlas-next/` source files.
- Vue Next production build output is generated at `web/atlas-next/dist/` via:
  - `cd web/atlas-next`
  - `npm install`
  - `npm run build`
- `dist/` is a generated artifact and not the workflow source of truth.
- Raw Vite source (including `web/atlas-next/src`) must never be served as production UI.
- Any future preview route must be `/atlas-next` only, read-only preview only, built-dist only, not default, no execution controls, and no mutation endpoint calls.
- Vue route must never replace `/` and must never replace `/ui.html`; existing `ui.html` remains default.
- If dist is missing, future `/atlas-next` must fail closed (disabled/deferred or 404) rather than serving source.
- Build artifact policy and smoke route policy must be covered by contract tests before any route mount is enabled.
- Vue default route is guarded: `/` serves Atlas Next only when validated dist is available; otherwise it fail-closed falls back to legacy UI/no execution; backend workflow state remains authoritative; `available_actions` remain metadata only; Vue does not compute execution eligibility and does not call mutation endpoints.


## Guarded Atlas Next Preview Route
- PR-ATLAS-VUE-10 adds optional guarded `/atlas-next` preview route hardening.
- `/atlas-next` serves built assets only from `web/atlas-next/dist`.
- Route fails closed (404) when dist or `dist/index.html` is missing.
- Route never serves raw Vite source and never serves `web/atlas-next/src`.
- Route never replaces `/` or `/ui.html`; existing `ui.html` remains default.
- Vue default route is guarded: `/` serves Atlas Next only when validated dist is available; otherwise it fail-closed falls back to legacy UI and does not call mutation endpoints.
- Vue adapter remains GET-only to `/api/atlas/workflow-state/read-only`.
- `available_actions` remain metadata-only and disabled/read-only.
- Backend workflow state remains authoritative; Vue does not compute execution eligibility.
- PR-ATLAS-SCALE-93 remains the current automation track.
- Final goal remains `fully_autonomous_code_agent`.
- Self-improvement scope remains `self_improving_codeagentpersonal_kasanecore`.

## PR-ATLAS-VUE-11 Update
- Historical checkpoint pointer: Current UI track: PR-ATLAS-VUE-12.
- PR-ATLAS-VUE-11 completed: Atlas Next preview route observability / fallback hardening.
- Preview route remains guarded, dist-backed, fail-closed, and read-only.
- Added GET-only metadata diagnostics endpoint: `/api/atlas/vue-next-preview/diagnostics`.
- Existing `ui.html` remains default; Vue default route is guarded: `/` serves Atlas Next only when validated dist is available; otherwise it fail-closed falls back to legacy UI.
- Backend `workflow_state` remains authoritative; Vue execution capability remains none.
- Completed UI PR: PR-ATLAS-VUE-12.
- Historical marker (superseded): Current UI track was PR-ATLAS-VUE-14. See Current Atlas Vue UI Track State.
- Current automation track remains PR-ATLAS-SCALE-94.

## PR-ATLAS-VUE-13 Route Packaging/Deployment Integration Policy
- PR-ATLAS-VUE-13 completed.
- Completed UI PR: PR-ATLAS-VUE-13.
- Historical marker (superseded): Current UI track was PR-ATLAS-VUE-14. See Current Atlas Vue UI Track State.
- Current automation track remains PR-ATLAS-SCALE-94.
- Existing `ui.html` remains default.
- Vue default route is guarded: `/` serves Atlas Next only when validated dist is available; otherwise it fail-closed falls back to legacy UI; supervision UI only.
- `/atlas-next` remains guarded/dist-backed/fail-closed.
- Diagnostics endpoint remains GET-only/metadata-only: `/api/atlas/vue-next-preview/diagnostics`.
- Backend `workflow_state` remains authoritative.
- No Vue execution capability exists.
- Deployment integration must use prebuilt dist artifacts only.
- Server startup must not run `npm install` or `npm run build` automatically.
- Missing or invalid dist must continue to fail closed.
- Generated dist is not source of truth.
- Source remains `web/atlas-next`.
- Dist remains `web/atlas-next/dist`.
- Build commands remain:
  - `cd web/atlas-next`
  - `npm install`
  - `npm run build`
  - `npm run typecheck`
- Deployment packaging may include `web/atlas-next/dist` only after validation passes.
- No raw Vite source serving.
- No fallback to `/` or `ui.html`.


## PR-ATLAS-VUE-12 Packaging/Deployment Readiness Policy
- Completed UI PR: PR-ATLAS-VUE-12 (docs/manifest/tests alignment only; no runtime execution change).
- Vue source remains in `web/atlas-next`.
- Production artifacts are generated with:
  - `cd web/atlas-next`
  - `npm install`
  - `npm run build`
- Dist output remains `web/atlas-next/dist`.
- `/atlas-next` may serve only dist artifacts.
- Generated dist is not the source of truth.
- Deployment may include dist artifacts only after build validation passes.
- Missing or invalid dist must fail closed.
- No raw Vite source may be served.
- No fallback to `ui.html` or `/` is allowed.
- Existing `ui.html` remains default.
- Vue default route is guarded: `/` serves Atlas Next only when validated dist is available; otherwise it fail-closed falls back to legacy UI.
- Diagnostics endpoint remains GET-only and metadata-only: `/api/atlas/vue-next-preview/diagnostics`.
- Backend `workflow_state` remains authoritative; Vue execution capability remains none.
- This PR does not make Vue default and does not enable execution.
- Current UI track: PR-ATLAS-VUE-13.
- Current automation track remains PR-ATLAS-SCALE-94.

## Active Vue Defaultization Pointer Update

- Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-12.
- Current UI track: PR-ATLAS-VUE-13.
- Planned UI defaultization track: PR-ATLAS-VUE-13 through PR-ATLAS-VUE-21.
- Atlas Next is guarded default route for `/` only when dist validation passes.
- Vue Atlas Next remains non-default until PR-ATLAS-VUE-21.
- Current automation track remains PR-ATLAS-SCALE-94 and resumes as active focus after PR-ATLAS-VUE-21.

## Minimal UI Policy During Vue Defaultization (VUE-13 through VUE-21)

- Vue Atlas Next must not become another large dashboard.
- Vue must preserve the Atlas minimal UI policy in `docs/atlas_autonomous_first_ui_policy.md` before, during, and after defaultization.
- Default-visible Vue UI remains `minimal_workflow` + `safety_always_visible` only.
- Advanced execution controls, raw JSON, internal IDs, direct subsystem panels, diagnostics, and debug controls remain hidden by default.
- Direct subsystem buttons must not appear in minimal/default mode.
- New Vue surfaces in PR-ATLAS-VUE-13 through PR-ATLAS-VUE-21 must be manifest-classified in `web/atlas_ui_surface_manifest.json`.
- Any newly default-visible surface must directly support: goal → plan → review → approval → guarded execution/progress → report.
- Vue must not compute execution eligibility.
- Backend workflow_state remains authoritative.
- No execute-all, no auto-continue, and no autonomous execution are authorized by this roadmap.



## Vue Defaultization Numbering Realignment (post VUE-13)
- PR-ATLAS-VUE-13 is completed and is route packaging/deployment integration (docs/manifest metadata/tests), not diagnostics alignment work.
- PR-ATLAS-VUE-13 did not change runtime semantics, did not make Vue default, and did not enable execution/mutation behavior.
- `/atlas-next` remains guarded, dist-backed, fail-closed, and non-default; prebuilt dist artifacts are required and server startup must not run `npm install`/`npm run build`.
- Completed UI PRs include PR-ATLAS-VUE-01 through PR-ATLAS-VUE-13.
- PR-ATLAS-VUE-15 completed. Current UI track is PR-ATLAS-VUE-16.
- Planned defaultization track runs PR-ATLAS-VUE-14 through PR-ATLAS-VUE-21, with PR-ATLAS-VUE-21 as the default-enable checkpoint.
- Existing `ui.html` remains default until PR-ATLAS-VUE-21.
- PR-ATLAS-SCALE-93 remains the current automation track; automation roadmap focus resumes after PR-ATLAS-VUE-21.
- PR-ATLAS-VUE-14 is now the preview route / manifest / backend diagnostics / client diagnostics state-alignment PR, including stale `routeMounted`/`staticMountDeferred` wording correction.
- Default-visible Vue UI remains `minimal_workflow` + `safety_always_visible` only.
- Advanced execution controls, raw JSON, internal IDs, direct subsystem panels, diagnostics, and debug controls remain hidden by default.
- Direct subsystem buttons must not appear in minimal/default mode.
- Vue must not compute execution eligibility; Backend workflow_state remains authoritative.
- No execute-all, no auto-continue, and no autonomous execution.


## PR-ATLAS-VUE-14 Route/Diagnostics Alignment
- PR-ATLAS-VUE-14 completed client/backend/manifest/docs diagnostics alignment for guarded `/atlas-next`.
- Completed UI PR: PR-ATLAS-VUE-14; current UI track: PR-ATLAS-VUE-15.
- Existing `ui.html` remains default until PR-ATLAS-VUE-21 default-enable checkpoint.
- Vue default route is guarded: `/` serves Atlas Next only when validated dist is available; otherwise it fail-closed falls back to legacy UI; backend workflow_state remains authoritative.
- `/atlas-next` remains mounted, guarded, dist-backed, fail-closed, and non-default.
- Diagnostics endpoint remains GET-only/metadata-only: `/api/atlas/vue-next-preview/diagnostics`.
- Vue client diagnostics now align with mounted guarded route state and no longer report static mount deferred.
- No execution capability exists in Vue; runtime remains `level_0_manual_only`.
- Default-visible Vue UI remains `minimal_workflow` + `safety_always_visible`; advanced execution controls, raw JSON, internal IDs, direct subsystem panels, diagnostics, and debug controls remain hidden by default.


- Vue workflow_state real-data connection is strengthened in PR-ATLAS-VUE-15 (metadata-only, GET-only, backend authoritative, no execution capability).


- PR-ATLAS-VUE-16 completed: Vue Requirement Input / Start Atlas Planning (POST /api/atlas/plan-pools only).
- Planning POST classification remains planning_metadata_only (non-execution).
- Vue remains non-default and execution capability remains none.
- Backend remains authoritative and runtime remains level_0_manual_only.
- VUE17 next: Requirement / clarification / plan review UI.


- PR-ATLAS-VUE-17 completed: Vue now shows read-only requirement/clarification/plan review metadata after Start Atlas Planning; execution controls remain unavailable.

- Historical marker preserved for contract tests: Current UI track: PR-ATLAS-VUE-17
- Historical marker preserved for contract tests: Planned UI track: PR-ATLAS-VUE-17 through PR-ATLAS-VUE-21


- PR-ATLAS-VUE-18 completed: Vue can display approval/dry-run readiness metadata only.
- Vue cannot approve, start dry-run, execute, apply, verify, rollback, retry, restore, or continue.
- Backend workflow_state remains authoritative, runtime remains level_0_manual_only, and Vue execution capability remains none.


## Historical Track Markers (Compatibility)
- Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-17
- Current UI track: PR-ATLAS-VUE-18
- Current automation track remains PR-ATLAS-SCALE-94
- no Vue execution capability exists
- Planned UI track: PR-ATLAS-VUE-18 through PR-ATLAS-VUE-21

- VUE21 is default-enable checkpoint, not execution-enable checkpoint.
- Vue can display execution safety boundary metadata only.
- Vue cannot approve, start dry-run, execute, apply, verify, rollback, retry, restore, or continue.
- VUE20 next scope: default-readiness preflight / route selection guard review.

- Historical marker: Current UI track: PR-ATLAS-VUE-19.
- Historical marker: Planned UI track: PR-ATLAS-VUE-19 through PR-ATLAS-VUE-21.

- Existing legacy ui.html remains available through `/ui/` and `/ui.html`.
- If Vue dist is invalid, root falls back safely to existing legacy UI.
- VUE21 is not execution-enable.
- Backend remains authoritative.
- Runtime remains level_0_manual_only.
- Vue execution capability remains none.
- After VUE21, return to automation roadmap: PR-ATLAS-SCALE-94.

- Completed automation PR: PR-ATLAS-SCALE-96
- Current automation track: PR-ATLAS-SCALE-98
- Next automation track: PR-ATLAS-SCALE-98
- next work is PR-ATLAS-SCALE-98
- SCALE-97 may add readiness UI display for gate-source mapping, not execution enable.
- Level-1 execution remains disabled.
- Runtime remains level_0_manual_only.
- Autonomous execution remains disabled.
- Vue execution capability remains none.
- Backend workflow_state remains authoritative.
