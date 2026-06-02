# Atlas Practical Full Automation Experience Plan

## Status

This is the accepted practical Atlas plan for bounded, backend-owned automation.
PR-O marks this checkpoint complete with PR-E-0-G through PR-N evidence while
preserving the safety invariants in the phase manifest and readiness policy.

The completed bounded loop is:

```text
unclear requirement
-> ask user
-> revise plan from the answer
-> rerun critique
-> rerun safety gates
-> continue only when safe, approved, and bounded
```

## Task

Maintain Atlas as a practical fully autonomous code-generation agent within the
accepted bounded backend-owned automation contract.

## Goal

Atlas must become a practical fully autonomous code-generation agent with
safe backend-owned automation. This does not enable direct merge, remote push,
self-apply, stable runtime mutation, Vue authority, or unbounded command execution.

## Final target behavior

```text
User requirement
-> requirement intake
-> initial plan
-> adversarial critique
-> clarification check
-> if unclear, ask user
-> revise plan from user answer
-> rerun critique and safety gates
-> if critical/high-risk, ask user for explicit decision
-> if user rejects/NGs, generate lower-impact alternative
-> revise/replan from lower-impact alternative
-> rerun gates
-> if safe/approved/bounded, perform autonomous code generation
-> apply candidate changes within allowed scope
-> run allowlisted verification
-> analyze failures
-> perform bounded repair attempts
-> produce final evidence-backed summary
-> prepare or update draft PR artifact when allowed
```

## Global constraints

- Read `AGENTS.md` and existing Atlas docs before editing when the file exists.
- Read main branch files directly; do not rely only on PR descriptions.
- Keep PRs small and safe.
- Prefer multiple focused PRs over one large risky PR.
- Do not duplicate active roadmap/current/next pointers in new docs.
- Do not enable direct merge.
- Do not enable remote git push.
- Do not enable self-apply.
- Do not enable stable runtime mutation.
- Do not make Vue authoritative.
- Do not add arbitrary shell execution.
- Do not add unbounded autonomous loops.
- Do not fabricate execution or verification results.
- Backend `workflow_state` remains authoritative.
- UI remains display/supervision only.
- Buildless ThinUX/FastUI remains usable.
- Do not require `npm install`, Vite build, Vue build, or Atlas Next dist at server startup.
- Critical events always require user judgment, even under `full_auto` or autonomous modes.
- If CI passes and scope is safe, auto-merge is allowed.

## Implementation efficiency rules

Apply these rules before implementing any PR from this plan:

1. Read only canonical sources first: `AGENTS.md` when present, `docs/atlas_scale_master_roadmap.md`, `docs/atlas_automation_phase_manifest.json`, `docs/atlas_autonomous_execution_readiness_policy.md`, and this file.
2. Treat manifest and roadmap as the source of truth for current/next state.
3. Do not reread broad docs repeatedly or summarize the whole roadmap unless needed.
4. Search for and reuse existing Atlas helpers before creating new modules. Prefer extending existing services over adding parallel normalizers, validators, policy files, or schemas.
5. Work narrowly per PR. Do not refactor, rename, update unrelated docs, touch UI, or change runtime semantics outside the current PR scope.
6. Keep progress output short: files changed, key behavior added, tests run, and blockers.
7. Search efficiently with exact symbols such as `critical_event`, `lower_impact_alternative`, `waiting_for_critical_decision`, `clarification`, `automation_profile`, `envelope`, `safe_apply`, verification allowlist, and autonomous loop.
8. Open only files needed for the current PR and prefer nearby call sites over broad repository scans.
9. Test the smallest focused set first, then broaden only when touched code is central. Always run `py_compile` for changed Python files and `node --check` only for changed JS files.
10. Preserve safety invariants without broad restatement: backend `workflow_state` authoritative, UI display/supervision only, no direct merge, no remote push, no self-apply, no stable runtime mutation, no Vue authority, no arbitrary unbounded command execution, and no fabricated verification results.
11. Keep diffs minimal and readable. Add docstrings only when they clarify a new contract. Avoid dependencies.
12. Update only canonical docs needed for the PR. Do not duplicate current/next PR pointers outside canonical files. Clearly label historical text when needed.
13. Completion reports must be concise and include Summary, Files changed, Tests run, Safety invariants preserved, and Remaining follow-up when applicable.

## PR-A: Critical-event NG replanning connection

Purpose:

Atlas already detects critical events and can create `lower_impact_alternative`
metadata after user NG/rejects. Complete the missing connection so NG actually
creates a revised candidate, reruns gates, and blocks the original unsafe path.

Files to inspect:

- `agent/atlas_critical_event_policy.py`
- `agent/atlas_plan_quality_gate.py`
- `agent/atlas_approval_service.py`
- `agent/atlas_automation_gate_service.py`
- `agent/atlas_full_auto_gate.py`
- `agent/atlas_safe_apply_adapter.py`
- `app/api/atlas_pipeline.py`
- `web/js/atlas_dashboard.js`
- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_critical_event_policy.py`
- existing plan pool / `PlanItem` schemas

Required implementation:

1. Add backend-owned service: `agent/atlas_critical_replanning_service.py`.
2. The service must support creating a lower-impact revised candidate from a rejected critical event, marking the original item/path as not allowed to continue, rerunning plan critique gate, rerunning automation/safety gate, and producing next status plus next required action.
3. Inputs must include pool, original item when item-level, pool-level critical event when pool-level, user decision record, `lower_impact_alternative` payload, profile/preset/envelope context, and current workflow state.
4. Output must include revised `PlanItem` or revised plan candidate, `revision_id`, `original_item_id` / `original_pool_id`, rerun critique gate, rerun safety gate, rerun result status, next required user action, and evidence metadata.
5. Persist metadata for original critical event, original user decision, `original_path_blocked: true`, lower-impact alternative, `created_from_critical_event: true`, `revision_id`, revised plan snapshot, gate rerun required/performed, rerun critique/safety gates, rerun result status, and next required user action.
6. If user rejects/NGs a critical event, the original item must not continue.
7. Original item status should become `needs_revision` or `superseded_by_lower_impact_revision`.
8. A new/revised candidate must be created from `lower_impact_alternative`.
9. The candidate must be rechecked by the same critique/safety gates.
10. If the revised candidate still has critical/safety-sensitive findings, status must remain `waiting_for_critical_decision`.
11. If the revised candidate is non-critical but still requires approval, status should be `approval_required`.
12. If it is safe and within an active bounded envelope, it may become `ready`.
13. This PR must not apply patches, run commands, verify, push, merge, self-apply, or mutate stable runtime.
14. In `AtlasApprovalService.decide()`, when `decision == rejected` and `critical_event` exists, generate `lower_impact_alternative`, call the critical replanning service, attach revised candidate / gate rerun metadata, and persist approval record with revision reference.
15. API response must show that the original critical path was rejected, lower-impact alternative was generated, gates reran, and next action is required.

Tests:

- Rejecting/NGing a critical item creates a lower-impact revision.
- Original critical item cannot continue.
- Revised candidate has reduced file scope.
- Revised candidate reruns critique/safety metadata.
- If rerun finds critical event, status remains `waiting_for_critical_decision`.
- If rerun is safe but needs approval, status becomes `approval_required`.
- No patch apply, command execution, verification, push, merge, or self-apply occurs.

## PR-B: Pool-level critical-event approval visibility

Purpose:

Critical events may be stored on `pool.metadata`, not only `item.metadata`.
Ensure pool-level critical events are never hidden from approval endpoints or UI.

Files to inspect:

- `app/api/atlas_pipeline.py`
- `agent/atlas_approval_service.py`
- `agent/atlas_critical_event_policy.py`
- `web/js/atlas_dashboard.js`
- `web/js/atlas_claude_panel.js`
- tests covering approval/list endpoints and dashboard strings

Required implementation:

1. Add normalized backend decision representation for pool-level critical events. It may be a virtual decision item, but backend must own it.
2. When `pool.status == waiting_for_critical_decision` or `pool.metadata.critical_event` exists, approval/list response must include `scope: pool`, `pool_id`, status, critical event, required options, safer alternatives, recommended decision, and next required user action.
3. UI must show critical event detected, reason, affected files, affected capabilities, estimated impact, recommended decision, safer alternatives, approve with explicit consent, reject/NG and request safer alternative, cancel, and edit requirement/scope.
4. Persist user decision as one of `approved`, `rejected_ng_safer_replan`, `cancelled`, or `edit_scope_requested`.
5. If user rejects/NGs a pool-level critical event, call the PR-A critical replanning service, create lower-impact replanning metadata, and keep original critical path blocked.
6. Do not require item-level `critical_event` for visibility.
7. UI posts decision, backend validates and persists, and backend computes next state.

Tests:

- `pool.status == waiting_for_critical_decision` appears in approval list.
- `pool.metadata.critical_event` appears even without item critical event.
- Pool-level Reject/NG creates lower-impact replanning metadata.
- Pool-level Approve persists bounded approval metadata.
- UI string/snapshot test confirms critical decision options are visible.

## PR-C: Unify profile / preset / envelope / automation-level schema

Purpose:

Atlas currently has several overlapping concepts:

- automation safety profile
- preset id
- automation level
- critical handling
- full-auto detection
- pre-authorized envelope
- self-improvement mode

Unify them into one backend resolver so complete automation behavior is consistent.

Files to inspect:

- `agent/atlas_auto_policy_schema.py`
- `agent/atlas_plan_quality_gate.py`
- `agent/atlas_full_auto_gate.py`
- `agent/atlas_critical_handling_policy.py`
- `agent/atlas_automation_gate_service.py`
- `app/atlas/automation_safety_profile.py`
- `app/atlas/pre_authorized_bounded_dev_envelope.py`
- `app/atlas/autonomous_loop_envelope_runner.py`
- `app/api/atlas_automation_safety_profile.py`
- `web/js/atlas_claude_panel.js`
- `docs/atlas_automation_phase_manifest.json`
- tests for profiles/presets/envelopes

Required implementation:

1. Add `agent/atlas_automation_profile_resolver.py`.
2. Normalize profiles: `review_only`, `guarded_single_action`, `supervised_bounded_auto`, `autonomous_dev_agent`.
3. Normalize presets: `review_only`, `single_action`, `supervised_auto`, `autonomous_custom`, `autonomous_bounded_dev`, `full_auto`, `full_auto_multi_item_v1`.
4. Normalize legacy automation levels: `manual_only`, `guarded_low_risk`, `supervised_auto`, `full_autopilot`.
5. Normalize envelopes: `none`, `pre_authorized_bounded_dev_envelope`, `pre_authorized_self_improvement_envelope`.
6. Normalized output must include profile, preset id, automation level, envelope id, envelope active, self-improvement, runtime level, full-auto capable, autonomous loop active, critical handling default, whether critical user approval is required, false safety invariants for direct merge / remote push / self-apply / stable runtime mutation / Vue authority / arbitrary command execution, max actions, max retries, max changed files, max runtime seconds, allowed paths, and blocked paths.
7. Unknown profile/preset falls back safely.
8. Profile selection alone must not activate a loop.
9. `autonomous_dev_agent` means Level-8 capable, not loop-active by itself.
10. Active pre-authorized bounded dev envelope may activate a bounded dev loop.
11. Pre-authorized self-improvement envelope requires strict self-improvement gate.
12. Critical events always require user judgment.
13. Direct merge, remote push, self-apply, and stable runtime mutation remain false.
14. Update plan quality gate, full-auto gate, critical handling policy, automation gate service, and API exposure to use or align with the resolver.
15. Existing `AtlasAutoPolicyPreset` callers must still work. If changing existing Pydantic schema is risky, add v2 schema and adapter.

Tests:

- All supported profile/preset/envelope combinations normalize.
- Unknown values fall back to safe `review_only` / ask / block behavior.
- `autonomous_dev_agent` without envelope does not start loop.
- `autonomous_bounded_dev` with active bounded envelope can start bounded loop.
- Self-improvement envelope requires strict gate.
- `critical_handling=auto` cannot bypass critical events.
- Direct merge, remote push, self-apply, stable runtime mutation, and Vue authority remain false.

## PR-D: Align docs, manifest, and active policy wording

Purpose:

Remove stale active wording and pointer drift. Manifest, roadmap, and policy docs
must agree.

Files to inspect:

- `docs/atlas_scale_master_roadmap.md`
- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_autonomous_execution_readiness_policy.md`
- `docs/atlas_practical_full_automation_experience_plan.md`
- `scripts/validate_atlas_automation_plan.py`
- `tests/test_atlas_scale_113_master_plan_consolidation_contract.py`

Required implementation:

1. Treat `docs/atlas_automation_phase_manifest.json` as machine-readable source of truth.
2. Update `docs/atlas_autonomous_execution_readiness_policy.md` so the active section matches manifest, `runtime_level_model` is `profile_dependent`, current level is described as maximum backend milestone rather than always-on runtime, default behavior remains safe/profile-dependent, current/next automation tracks match manifest, and old SCALE-152 / Level-4 text moves into a clearly labeled historical baseline section.
3. Do not leave stale active `Current level: Level 4` wording in the active section.
4. Update validators to fail on stale active SCALE-152 current-boundary wording, current/next track drift between manifest and roadmap, duplicate active pointers in deleted docs, and to allow historical text only in clearly marked historical sections.
5. Do not change runtime behavior in this PR.

Tests:

- Plan validator passes.
- Stale active Level-4 wording is detected.
- Manifest and roadmap current/next tracks are consistent.
- Historical section is allowed.

## PR-E: Clarification-driven plan revision loop

Purpose:

Unclear requirement handling must not stop at asking a question. User answers
must revise the plan, update constraints/acceptance criteria/target files/tests,
and rerun gates before implementation.

Files to inspect:

- `agent/atlas_clarification_gate_service.py`
- `agent/atlas_critique_gate_service.py`
- `agent/atlas_plan_quality_gate.py`
- `agent/atlas_plan_pool_schema.py`
- `app/api/atlas_pipeline.py`
- `web/js/atlas_claude_panel.js`
- `web/js/atlas_dashboard.js`
- relevant clarification / pipeline tests

Required implementation:

1. Add `agent/atlas_clarification_replanning_service.py`.
2. When ambiguity or missing required info is detected, set status to `needs_scope_confirmation`.
3. Ask one focused question at a time.
4. Provide selectable options where possible.
5. Explain why the answer matters.
6. Persist clarification decision.
7. Update requirement summary, plan, PlanItem fields, target files, allowed/blocked paths, acceptance criteria, done definition, expected changes, verification intent/test commands, and risk level when the answer changes risk.
8. Persist metadata for clarification required, question, options, answer, decision id, original/revised requirement summaries, original/revised plan snapshots, plan revision diff, gate rerun required/performed, rerun critique/safety gates, and next required user action.
9. Required flow is `needs_scope_confirmation` -> user answers -> revise plan -> rerun adversarial critique -> rerun safety/automation gates -> continue only if revised plan is safe or approved.
10. Do not proceed directly from `needs_scope_confirmation` to implementation.
11. Do not proceed without `revised_plan_snapshot` and gate rerun.
12. Do not silently use default assumption unless `clarification_mode == auto`.
13. Safe default assumption must be recorded.
14. Full auto may use safe default only for non-critical ambiguity.
15. Security, deletion, data loss, runtime, self-improvement, command execution, remote git, direct merge, and stable runtime ambiguity must always ask the user.
16. If user answer expands scope or raises risk, status must require approval or critical decision.
17. If answer reduces scope, update target files and allowed paths.
18. If answer changes tests, update verification intent.
19. UI must show one question at a time, options, why Atlas is asking, effect of selected option when known, and `use safe default` only when backend allows it. UI posts the answer; backend revises the plan.

Tests:

- Ambiguous request pauses at `needs_scope_confirmation`.
- User answer creates `revised_plan_snapshot`.
- Revised plan differs from original plan.
- PlanItem fields are updated.
- Gates rerun after answer.
- Implementation cannot start before revised plan exists.
- Safe default is recorded when `clarification_mode == auto`.
- Critical ambiguity never auto-defaults.
- Answer expanding scope triggers higher risk / approval.
- Answer reducing scope updates target files.

## PR-F: Practical autonomous code-generation loop v1

Purpose:

Implement the actual bounded autonomous code-generation runner. This is the core
practical automation loop.

Files to inspect:

- `agent/atlas_multi_item_autopilot_service.py`
- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `app/api/atlas_autonomous_codegen.py`
- `app/atlas/autonomous_loop_envelope_runner.py`
- `app/atlas/pre_authorized_bounded_dev_envelope.py`
- `agent/atlas_automation_gate_service.py`
- `agent/atlas_safe_apply_adapter.py`
- `agent/atlas_plan_quality_gate.py`
- `agent/atlas_critical_replanning_service.py`
- `agent/atlas_clarification_replanning_service.py`
- verification allowlist modules
- `agent/atlas_plan_pool_schema.py`
- `web/js/atlas_claude_panel.js`
- `web/js/atlas_dashboard.js`

Required implementation:

1. Add or complete bounded autonomous code-generation runner.
2. Runner input must include user requirement, project path, selected profile, selected preset, envelope, max actions, max changed files, max retries, max runtime, allowed paths, blocked paths, allowed verification commands, clarification mode, critical handling mode, and self-improvement flag.
3. Runner phases are `idle`, `understanding_goal`, `planning`, `adversarial_review`, `needs_scope_confirmation`, `revising_plan_from_clarification`, `waiting_for_critical_decision`, `replanning_lower_impact`, `candidate_generation`, `candidate_apply`, `verification`, `failure_analysis`, `bounded_repair`, `final_summary`, and `draft_pr_preparation`.
4. Hard stops include critical event, missing project path, unsafe path, protected path, forbidden action, content missing, verification allowlist mismatch, max actions/retries/runtime exceeded, user stop/cancel, ambiguous scope with pause clarification mode, self-improvement without strict gate, and selected profile with inactive envelope.
5. Candidate mutation must operate only on allowed target project/candidate scope and must not mutate stable runtime, remote push, direct merge, self-apply, mutate outside allowed paths, or touch blocked paths.
6. Reuse existing safe apply / patch transaction path.
7. Require executor-readable patch or file changes content.
8. Capture before/after evidence, changed files, and rollback metadata.
9. Do not create fake execution results.
10. Use only allowlist-resolved verification commands.
11. Capture stdout, stderr, and exit status when actually run.
12. If command execution is unavailable, record `verification_not_run` with reason.
13. Verification failure triggers bounded repair if retries remain.
14. Bounded repair analyzes failure, generates repair candidate, reruns safety gates before repair apply, stops on forbidden/protected paths, stops after max retries, and records every attempt.
15. Final summary must include status, changed files, applied/skipped actions, verification results, repair attempts, unresolved risks, user decisions required, draft PR readiness, and evidence paths.
16. API must add or complete start/status/read endpoints, return workflow-state-compatible summary, support polling and stop/cancel, and expose current phase plus next action.
17. UI must show phase, progress, changed files, verification status, clarification question, critical decision panel, lower-impact replanning, repair attempts, and final summary. UI must not approve or execute by itself.

Tests:

- Happy path low-risk file change completes.
- Missing project path stops safely.
- Unsafe path stops.
- Critical event stops for user decision.
- NG creates lower-impact replanning path.
- Clarification answer revises plan before implementation.
- Verification failure triggers bounded repair.
- Max retries stops.
- Stop/cancel stops continuation.
- Unknown profile falls back safely.
- `autonomous_dev_agent` without active envelope does not run.
- Active bounded envelope allows bounded loop.
- No direct merge, remote push, self-apply, or stable runtime mutation.

## PR-G: Candidate workspace and recovery integration for autonomous loop

Purpose:

The autonomous loop must not casually mutate stable runtime or unsafe workspaces.
Connect candidate workspace and recovery evidence to practical automation.

Files to inspect:

- candidate workspace manager modules
- recovery supervisor modules
- boot self-diagnosis / stable checkpoint modules
- `app/atlas/autonomous_loop_envelope_runner.py`
- `agent/atlas_safe_apply_adapter.py`
- `docs/atlas_full_automation_self_recovery_ux_plan.md`
- tests for candidate workspace/recovery

Required implementation:

1. Before autonomous mutation, resolve work target as ordinary project repair/development, platform self-improvement, candidate workspace, or stable runtime.
2. Ordinary project work must validate project path, allowed paths, blocked paths, and snapshot/rollback metadata where available.
3. Platform self-improvement must require self-improvement profile/scope, strict gate, active pre-authorized self-improvement envelope, candidate-first boundaries, and no self-apply to stable runtime.
4. If candidate workspace exists, use it.
5. If no candidate workspace exists, produce `candidate_workspace_required` or `workspace_not_available`.
6. Do not silently fall back to stable runtime mutation.
7. Capture recovery manifest references and restore/rollback plan references when available.
8. If recovery evidence is missing, record explicit warning.
9. Do not execute recovery unless already allowed by existing policy.
10. Do not fabricate recovery results.
11. If platform work is requested, require stable checkpoint evidence and stop clearly when missing.

Tests:

- Ordinary project path validates.
- Blocked path prevents mutation.
- Self-improvement without strict gate stops.
- Candidate workspace missing stops or records required state.
- No stable runtime mutation occurs.
- Recovery metadata is recorded but not executed.

## PR-H: Draft PR preparation and update experience

Purpose:

Complete the final output of autonomous development. Atlas should produce a
reviewable PR artifact and use existing safe injected-client draft PR mechanisms
only when allowed.

Files to inspect:

- existing draft PR policy modules
- existing injected PR client helpers
- `app/api/atlas_autonomous_codegen.py`
- `agent/atlas_multi_item_autopilot_service.py`
- `app/atlas/autonomous_loop_envelope_runner.py`
- `docs/atlas_scale_master_roadmap.md`
- tests for draft PR creation/update

Required implementation:

1. After successful bounded autonomous run, collect changed files, verification evidence, risk summary, user decisions, critical events, clarification answers, repair attempts, remaining warnings, and rollback notes.
2. Produce PR summary artifact.
3. If draft PR creation/update is allowed, use existing injected client only. Do not direct remote push, direct merge, runtime auto-merge, or bypass draft PR metadata/result.
4. If draft PR creation is not allowed, produce copyable PR body and branch instructions, and explain what was not done and why.
5. PR body must include Summary, Scope, Safety constraints, Changed files, Tests / verification, Clarification decisions, Critical events / user decisions, Repair attempts, Remaining risks, and Rollback notes.

Tests:

- Successful run produces PR artifact.
- Draft PR path uses injected client only.
- No remote push.
- No direct merge.
- Failed/needs_revision run does not claim PR ready.
- Critical decisions and clarification answers appear in PR body.

## PR-I: UI and API practical automation experience

Purpose:

Make the autonomous loop visible and controllable. The user must understand what
Atlas is doing, why it stopped, what it changed, and what decision is needed.

Files to inspect:

- `web/js/atlas_claude_panel.js`
- `web/js/atlas_dashboard.js`
- `web/css` or relevant UI files
- `app/api/atlas_pipeline.py`
- `app/api/atlas_autonomous_codegen.py`
- `app/api/atlas_automation_safety_profile.py`
- existing UI tests

Required implementation:

1. UI must show current phase, active profile/preset/envelope, runtime level resolved from backend, goal/requirement summary, current plan summary, clarification question, critical event decision panel, lower-impact replanning state, changed files, verification status, repair attempts, final summary, and next required user action.
2. Required controls are Start, Stop, Cancel, Answer clarification, Approve critical event, Reject/NG and request safer alternative, Edit scope, and Continue after backend says ready.
3. UI sends user intent/decision only. Backend computes next state.
4. UI must display backend-provided state.
5. Do not expose raw internal JSON by default. Diagnostics may show raw JSON only in explicit diagnostics mode.
6. API must return normalized workflow state, phase, next action, decision targets, evidence summaries, user-visible warnings, and whether automation is active/stopped/blocked.

Tests:

- UI displays clarification state.
- UI displays critical event state.
- UI displays lower-impact replanning state.
- UI displays verification and repair attempt state.
- UI does not show execute/apply controls unless backend allows next action.
- Backend remains source of truth.

## PR-J: End-to-end acceptance tests for practical full automation

Purpose:

Add realistic tests proving Atlas behaves as a practical autonomous code-generation
agent under safe constraints.

Required scenarios:

1. Simple documentation update: requirement, plan, critique, safe apply, completed.
2. Simple low-risk code fix: single file, safe apply, allowlisted test, completed.
3. Clarification: ambiguous requirement, `needs_scope_confirmation`, user answer, revised plan, gate rerun, implementation starts only after revision.
4. Critical event: security/destructive/protected path, `waiting_for_critical_decision`, full auto cannot bypass.
5. NG lower-impact: user rejects critical path, lower-impact alternative generated, original path blocked, gates rerun, revised candidate created.
6. Verification failure repair: first patch fails test, repair candidate generated, gates rerun, second attempt passes or stops after max retry.
7. Envelope behavior: `autonomous_dev_agent` without envelope cannot start autonomous loop, `autonomous_bounded_dev` with active bounded envelope can start bounded loop, and self-improvement envelope requires strict gate.
8. Forbidden operations: direct merge, remote push, self-apply, stable runtime mutation, Vue authority, and arbitrary command execution remain false.
9. UI/API state: status endpoint reports current phase, clarification visible, critical decision visible, verification visible, repair visible, final summary visible.

Run:

- focused pytest suite
- `py_compile` for changed Python files
- `node --check` for changed JS files

Acceptance:

- No fake verification success.
- No hidden critical event.
- No implementation from ambiguous plan without revision.
- No loop activation by profile alone.

## Final milestone acceptance criteria

Atlas reaches practical fully autonomous code generation only when all are true:

1. User can submit a development/repair requirement from Atlas UI/API.
2. Atlas creates and persists an initial plan.
3. Atlas runs adversarial critique.
4. Atlas detects ambiguity.
5. Atlas asks user for clarification when needed.
6. User answer revises the plan, not only metadata.
7. Revised plan updates requirement summary, target files, allowed/blocked paths, expected changes, acceptance criteria, verification intent, and risk level.
8. Atlas reruns critique and safety gates after clarification.
9. Atlas detects critical events.
10. Critical events always require explicit user judgment.
11. User can approve, reject/NG, cancel, or edit scope.
12. Reject/NG blocks original critical path.
13. Reject/NG generates lower-impact alternative.
14. Lower-impact alternative becomes a revised candidate.
15. Revised candidate reruns gates.
16. Approved/safe/bounded work can proceed under allowed profile/envelope.
17. Atlas can generate candidate code changes.
18. Atlas can apply candidate changes only inside allowed scope.
19. Atlas can run allowlisted verification or honestly record not-run reason.
20. Atlas can analyze verification failure.
21. Atlas can perform bounded repair attempts.
22. Atlas stops cleanly on critical event, unclear scope, unsafe path, forbidden action, max actions, max retries, max runtime, user stop/cancel, missing envelope, and missing strict gate for self-improvement.
23. Atlas produces evidence-backed final summary.
24. Atlas can prepare/update draft PR artifact when allowed.
25. Atlas never directly merges, remote pushes, self-applies, mutates stable runtime, gives Vue authority, executes arbitrary unbounded commands, or fabricates verification results.
26. Tests prove the above.

## Recommended implementation order

1. PR-A Critical-event NG replanning connection
2. PR-B Pool-level critical-event approval visibility
3. PR-C Profile/preset/envelope schema unification
4. PR-D Docs/manifest/policy alignment
5. PR-E Clarification-driven plan revision loop
6. PR-F Practical autonomous code-generation loop v1
7. PR-G Candidate workspace and recovery integration
8. PR-H Draft PR preparation and update experience
9. PR-I UI and API practical automation experience
10. PR-J End-to-end acceptance tests

The most important implementation step is PR-E. Practical autonomous code
generation cannot stop at asking clarifying questions. The answer must be
reflected into the plan, the plan must be revised, and critique / safety gates
must rerun before implementation proceeds.
