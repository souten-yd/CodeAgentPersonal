# Atlas PR-E through PR-O implementation plan

This document is the Codex implementation plan after the PR-E-0 stabilization line. It reconciles the PR-E-0-B final audit with the newer PR-E-0-G through PR-O implementation plan.

Use this file together with:

- `docs/atlas_full_automation_codex_entrypoint.md`
- `docs/atlas_pr_e0_b_hardening_instruction.md`
- `docs/atlas_corrective_pr_split_plan_after_1510.md`
- `docs/atlas_practical_full_automation_experience_plan.md`
- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_autonomous_execution_readiness_policy.md`

## Relationship to PR-E-0-B final audit

The earlier PR-E-0-B final audit instruction is not a separate long-lived track. It is absorbed into **PR-E-0-G** below.

PR-E-0-G must verify the PR-E-0-B acceptance checklist and patch only remaining UI, manifest, policy, or wording drift before PR-E starts.

## Common instructions for every PR

- Work on latest `main`.
- Read `AGENTS.md` first when present.
- Keep the PR small and focused.
- Reuse existing modules, tests, docs, and contracts before adding new ones.
- Do not duplicate roadmap or policy files.
- Do not broaden runtime semantics unless the PR explicitly says so.
- Backend workflow state remains authoritative.
- UI is supervision/display only unless explicitly changed by a later gated PR.
- Do not make Vue authoritative or default.
- Do not add arbitrary shell execution.
- Do not add unbounded automation.
- Do not fabricate verification results.
- Do not enable direct merge.
- Do not enable remote git push.
- Do not enable self-apply.
- Do not enable stable runtime mutation.
- Do not add raw source serving, fallback redirect, or startup npm/Vite/Vue build.
- Preserve profile/envelope/gate boundaries.
- Critical events must require user judgment.
- Clarification/revision/gate evidence must be real metadata, not implied.
- If CI is green and scope remains safe, auto-merge is allowed.

## Implementation order

0. PR-E-0-G: Align clarification UI blocking and automation truthfulness before PR-E.
1. PR-E: Formalize clarification-driven plan revision loop.
2. PR-F: Stabilize practical autonomous code-generation loop v1.
3. PR-G: Integrate candidate workspace and recovery evidence.
4. PR-H: Prepare evidence-backed draft PR artifacts.
5. PR-I: Improve Atlas Workbench practical automation UX.
6. PR-J: Add practical full automation end-to-end acceptance tests.
7. PR-K: Add CI failure evidence and bounded repair planning.
8. PR-L: Add self-platform candidate modification mode.
9. PR-M: Add self-platform review gate before draft PR readiness.
10. PR-N: Add supervised auto-merge readiness report.
11. PR-O: Reconcile practical full automation completion and level semantics.

Do not start PR-E until PR-E-0-G is merged and CI is green.

---

# PR-E-0-G: Align clarification UI blocking and automation truthfulness

## Task

Align clarification UI blocking and automation truthfulness before PR-E.

## Context

Recent PRs #1507-#1526 are merged. PR-E-0 behavior is mostly implemented:

- shared clarification execution blocker
- backend block before patch proposal / safe apply / autonomous codegen
- clarification replanning service
- clarification scope bounds
- autonomous preflight scope enforcement
- visual verification repair plan/detail surfacing
- acceptance safety tests

This PR must be narrow. It replaces the earlier PR-E-0-B final audit as the final PR-E-0 stabilization step.

Do not implement PR-E. Do not implement PR-F. Do not broaden autonomous execution.

## Read first

- `AGENTS.md`
- `docs/atlas_full_automation_codex_entrypoint.md`
- `docs/atlas_pr_e0_b_hardening_instruction.md`
- `docs/atlas_corrective_pr_split_plan_after_1510.md`
- `docs/atlas_practical_full_automation_experience_plan.md`
- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_autonomous_execution_readiness_policy.md`
- `app/api/atlas_pipeline.py`
- `app/api/atlas_autonomous_codegen.py`
- `agent/atlas_clarification_execution_blocker.py`
- `agent/atlas_clarification_replanning_service.py`
- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_plan_cancel_clarify_api.py`
- `tests/test_atlas_practical_full_automation_acceptance.py`

## Goal

Fix remaining UI/policy truthfulness gaps before PR-E.

## Required changes

### 1. Fix Claude panel approval prompt suppression

In `web/js/atlas_claude_panel.js`, `renderPlanPoolMarkdown()` must not show `appendPlanActionPrompt(poolId)` when any clarification execution block reason exists.

Before the `poolStatus === 'approval_required'` branch, compute:

```js
const clarificationBlocks = clarificationExecutionBlockReasons(poolMeta);
```

Behavior:

- show clarification prompt when required/pending questions exist
- show a short blocked status message when `clarificationBlocks.length > 0`
- do not show Approve and Run while any post-clarification blocker exists:
  - `plan_revision_required_after_clarification`
  - `gate_rerun_required_after_clarification`
  - `missing_revised_plan_snapshot_after_clarification`
  - `missing_gate_rerun_evidence_after_clarification`

### 2. Add or strengthen frontend contract tests

If the existing test style supports it, add tests for:

- pool status `approval_required` plus `gate_rerun_required_after_clarification=true` does not render approval/run prompt
- pool status `approval_required` without clarification blockers still renders approval prompt
- clarification prompt remains one-question-at-a-time

### 3. Clean manifest truthfulness wording

In `docs/atlas_automation_phase_manifest.json`, avoid wording that can be read as "complete fully autonomous code agent is generally enabled".

Preserve:

- `runtime_level_model: profile_dependent`
- `current_level_semantics: max_backend_runtime_milestone_not_single_active_runtime`
- `direct_merge: false`
- `remote_git_push: false`
- `self_apply: false`
- `stable_runtime_mutation: false`
- `vue_source_of_truth: false`
- `vue_execution_capability: none`
- `practical_full_automation_truthfulness_status: corrective_checkpoint_in_progress`
- `practical_full_automation_complete: false`

If `final_goal_backend_milestone_reached` remains true, clarify that it means backend milestone scaffolding exists, not end-to-end accepted completion.

### 4. Clean policy wording drift

In `docs/atlas_autonomous_execution_readiness_policy.md`, ensure active policy says:

- unbounded autonomous execution remains disabled
- bounded autonomous codegen is profile/envelope/gate controlled
- profile selection alone never starts a loop
- critical events always require user judgment
- direct merge, remote push, self-apply, stable runtime mutation, Vue authority, arbitrary unbounded command execution remain disabled

Move old disabled statements clearly under historical baseline, or qualify them as historical SCALE-152 state only.

### 5. Preserve current backend behavior

Do not change unless tests expose a bug:

- `agent/atlas_clarification_execution_blocker.py` semantics
- autonomous codegen preflight safety checks
- clarification replanning item mutation semantics
- visual verification repair plan behavior

## Tests

Run:

- `python -m pytest -q tests/test_atlas_plan_cancel_clarify_api.py`
- `python -m pytest -q tests/test_atlas_practical_full_automation_acceptance.py`
- `python -m pytest -q tests/test_atlas_clarification_service.py`
- `python -m pytest -q tests/test_atlas_post_scale160_current_status_alignment.py tests/test_atlas_post_scale160_practical_full_automation_manifest_contract.py tests/test_atlas_practical_full_automation_experience_plan.py`
- `python -m py_compile app/api/atlas_pipeline.py app/api/atlas_autonomous_codegen.py agent/atlas_clarification_execution_blocker.py agent/atlas_clarification_replanning_service.py agent/atlas_autonomous_codegen_orchestrator_service.py`
- `node --check web/js/atlas_claude_panel.js web/js/atlas_pipeline_api.js`

## PR title

`PR-E-0-G: Align clarification UI blocking and automation truthfulness`

---

# PR-E: Formalize clarification-driven plan revision loop

## Context

PR-E-0 and PR-E-0-B/G stabilize clarification UX/state and execution blocking. `AtlasClarificationReplanningService` already exists and mutates PlanPool/PlanItem metadata after clarification answers.

This PR must formalize the existing behavior into a clear, tested PR-E contract. Do not rewrite the service broadly.

## Read first

- `AGENTS.md`
- `docs/atlas_practical_full_automation_experience_plan.md`
- `docs/atlas_pr_e0_clarification_bugfix_plan.md`
- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_autonomous_execution_readiness_policy.md`
- `agent/atlas_clarification_service.py`
- `agent/atlas_clarification_execution_blocker.py`
- `agent/atlas_clarification_replanning_service.py`
- `app/api/atlas_pipeline.py`
- `app/api/atlas_autonomous_codegen.py`
- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_plan_cancel_clarify_api.py`
- `tests/test_atlas_clarification_service.py`
- `tests/test_atlas_practical_full_automation_acceptance.py`

## Goal

Make clarification answers produce a clearly auditable revised plan and gate rerun state, with UI/API behavior ready for PR-F.

## Expected final state

1. Clarification answers are converted into a revised plan snapshot.
2. Revised plan snapshot includes clear before/after metadata.
3. Gate rerun evidence is stored and visible.
4. If replanning succeeds, post-clarification blockers clear.
5. If replanning fails or gate rerun is inconclusive, execution remains blocked.
6. UI shows revised plan evidence rather than implying old plan is approved.
7. Tests prove that original unclarified plan cannot proceed.

## Required implementation

1. Strengthen `AtlasClarificationReplanningService.revise_after_answers()` to record:
   - `clarification_replanning.revision_id`
   - `clarification_replanning.decision_id`
   - `clarification_replanning.answered_question_count`
   - `clarification_replanning.revised_at`
   - `clarification_replanning.risk_raised`
   - `clarification_replanning.scope_reduced`
   - `clarification_replanning.allowed_paths_after_clarification`
   - `clarification_replanning.item_changed_fields`
   - `clarification_replanning.selected_option_impacts`
   - `original_plan_snapshot`
   - `revised_plan_snapshot`
   - `plan_revision_diff`
   - `rerun_critique_gate_after_clarification`
   - `rerun_safety_gate_after_clarification`
   - `gate_rerun_performed_after_clarification: true`
   - `plan_revision_required_after_clarification: false`
   - `gate_rerun_required_after_clarification: false`
2. Add explicit failure handling:
   - keep `plan_revision_required_after_clarification: true`
   - keep `gate_rerun_required_after_clarification: true`
   - set `clarification_replanning.status: failed`
   - store a bounded error summary, not a raw traceback
   - do not mark pool ready
   - do not allow patch proposal or safe apply
3. Add compact UI-facing summary metadata:
   - `revised_plan_summary`
   - `changed_scope_summary`
   - `gate_rerun_summary`
   - `next_required_user_action`
4. In `web/js/atlas_claude_panel.js`:
   - after final clarification answer, show "Plan revised and gates rerun" when successful
   - show changed fields and allowed paths if present
   - show blocked message if revision/gate evidence is missing
   - do not show old approval prompt during failed/incomplete replanning
5. `/api/atlas/plan-pools/{pool_id}/clarify` response should include:
   - `clarification_replanning`
   - `revised_plan_snapshot` or compact summary
   - `plan_revision_diff`
   - `gate_rerun_summary`
   - `blocked_reasons` if still blocked
6. Add or strengthen tests for:
   - all questions answered triggers revision
   - revised snapshot exists
   - old plan cannot proceed without revised snapshot
   - gate rerun evidence exists
   - blocker clears only after revision + gate evidence
   - failure path remains blocked
   - UI/API summary exposes changed fields

## Do NOT

- Do not implement broad autonomous loop changes.
- Do not add new execution capability.
- Do not add arbitrary shell execution.
- Do not enable direct merge, remote push, self-apply, stable runtime mutation, or Vue authority.
- Do not fabricate gate rerun results.
- Do not silently clear blockers.

## Tests

- `python -m pytest -q tests/test_atlas_clarification_service.py`
- `python -m pytest -q tests/test_atlas_plan_cancel_clarify_api.py`
- `python -m pytest -q tests/test_atlas_practical_full_automation_acceptance.py`
- `python -m py_compile agent/atlas_clarification_replanning_service.py app/api/atlas_pipeline.py`
- `node --check web/js/atlas_claude_panel.js`

## PR title

`PR-E: Formalize clarification-driven plan revision loop`

---

# PR-F: Stabilize practical autonomous code-generation loop v1

## Context

PR-E formalizes clarification-driven plan revision and gate rerun. Autonomous codegen and multi-item autopilot already exist, but this PR should make the practical loop contract explicit and reliable.

## Read first

- `AGENTS.md`
- `docs/atlas_practical_full_automation_experience_plan.md`
- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_autonomous_execution_readiness_policy.md`
- `app/api/atlas_autonomous_codegen.py`
- `app/api/atlas_multi_item_autopilot.py`
- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `agent/atlas_multi_item_autopilot_service.py`
- `agent/atlas_patch_proposal_service.py`
- `agent/atlas_auto_safe_apply_service.py`
- `agent/atlas_auto_verification_service.py`
- `agent/atlas_failure_stop_service.py`
- `tests/test_atlas_practical_full_automation_acceptance.py`

## Goal

Make the practical autonomous loop reliable for bounded development tasks:

Plan item -> patch proposal -> safe apply -> verification -> bounded repair decision -> final summary.

## Expected final state

1. Autonomous loop runs only with valid backend profile/envelope/gates.
2. It never starts from unresolved clarification or critical decision.
3. It respects allowed paths, blocked paths, max actions, max runtime, max changed files.
4. Patch generation failures are reported honestly.
5. Items without patch content are skipped, not counted as success.
6. Verification failure creates actionable failure/repair metadata.
7. Draft PR readiness is true only when results are verified or explicitly partial with evidence.
8. UI status never exposes execute controls directly.

## Required implementation

1. In `AtlasAutonomousCodegenOrchestratorService._preflight()`, keep blocking:
   - missing project path
   - inactive envelope for `autonomous_dev_agent`
   - self-improvement without strict gate
   - allowed path expansion
   - unsafe paths
   - blocked paths
   - outside allowed paths
   - unsupported verification commands
   - clarification scope violations
   - critical approval scope violations
2. Ensure `AtlasAutonomousCodegenResult` metadata includes:
   - `preflight`
   - `phase_order`
   - `processed_count`
   - `completed_count`
   - `failed_count`
   - `blocked_count`
   - `changed_files`
   - `verification_failure_summary`
   - `repair_plan`
   - `draft_pr_readiness`
   - `draft_pr_artifact`
   - `workspace_evidence`
   - `recovery_evidence`
3. Patch generation honesty:
   - proposal status with no patch content must be skipped/no_content
   - do not approve/apply no-content proposals
   - surface item id and reason in result metadata
4. Verification/repair behavior:
   - failed verification must not mark draft PR ready
   - create `verification_failure_summary`
   - create bounded `repair_plan` when applicable
   - limit repair files to changed files and allowed paths
   - set `post_repair_verification_required: true`
   - do not run unbounded repair in this PR
5. `_normalized_status()` must show:
   - current phase
   - active profile
   - evidence summary
   - decision targets
   - controls with `can_execute: false`
   - `execute_apply_visible: false`
   - raw JSON hidden by default
6. Add or strengthen tests for:
   - simple doc/code task completes with draft PR artifact
   - no active envelope blocks `autonomous_dev_agent`
   - clarification blocks before proposal
   - critical decision blocks before proposal
   - allowed path expansion blocks
   - blocked path blocks
   - unsupported verification commands block
   - no patch content does not count as success
   - visual verification failure creates repair plan and no PR readiness

## Do NOT

- Do not add arbitrary command execution.
- Do not execute non-allowlisted commands.
- Do not enable direct merge.
- Do not enable remote git push.
- Do not self-apply to stable runtime.
- Do not auto-create or auto-update remote PR unless already manually gated and existing code supports it.
- Do not broaden self-improvement behavior.
- Do not fabricate patch or verification success.

## Tests

- `python -m pytest -q tests/test_atlas_practical_full_automation_acceptance.py`
- `python -m pytest -q tests/test_atlas_plan_cancel_clarify_api.py`
- `python -m pytest -q tests/test_atlas_safe_apply_adapter.py`
- `python -m py_compile app/api/atlas_autonomous_codegen.py agent/atlas_autonomous_codegen_orchestrator_service.py`
- `node --check web/js/atlas_claude_panel.js`

## PR title

`PR-F: Stabilize practical autonomous code-generation loop v1`

---

# PR-G: Integrate candidate workspace and recovery evidence

## Goal

Make candidate workspace and recovery evidence first-class for practical automation, without mutating stable runtime.

## Read first

- `AGENTS.md`
- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_autonomous_execution_readiness_policy.md`
- `app/atlas/candidate_workspace_manager.py`
- `agent/atlas_recovery_service.py`
- `agent/atlas_change_snapshot_restore_service.py`
- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `app/api/atlas_autonomous_codegen.py`
- `app/api/atlas_pipeline.py`
- `tests/test_atlas_practical_full_automation_acceptance.py`

## Expected final state

1. Autonomous codegen requires effective project/workspace evidence.
2. Candidate workspace state is recorded in result metadata.
3. Recovery snapshot or recovery plan is recorded before/after apply phases.
4. Stable runtime mutation remains disabled.
5. Rollback/restore is visible but not automatically executed unless explicitly allowed by existing safe restore endpoint.
6. UI can show workspace and recovery evidence.

## Required implementation

1. Add/strengthen `workspace_evidence` metadata:
   - `status`
   - `effective_project_path`
   - `candidate_workspace_id` if available
   - `candidate_workspace_root` if available
   - `stable_runtime_mutation_enabled: false`
   - `self_apply_enabled: false`
2. Add/strengthen `recovery_evidence` metadata:
   - `status`
   - `snapshot_manifest_path`
   - `changed_files`
   - `restore_available`
   - `restore_executed: false`
   - `rollback_executed: false`
   - `recovery_execution_performed: false`
3. Preflight blocks:
   - missing project path
   - unresolved workspace/candidate evidence
   - self-improvement request without required strict gate/candidate boundary
   - stable runtime target without explicit future gate
4. UI status exposes workspace evidence, recovery evidence, restore availability, and no automatic rollback claim.
5. Tests cover candidate workspace evidence, missing workspace block, stable runtime block, recovery evidence, failed run no rollback claim, and no stable runtime mutation flags becoming true.

## Do NOT

- Do not mutate stable runtime.
- Do not implement automatic rollback.
- Do not implement automatic recovery execution.
- Do not create worktree/git branch unless already covered by existing safe local branch artifact policy.
- Do not push or merge.
- Do not self-apply.

## Tests

- `python -m pytest -q tests/test_atlas_practical_full_automation_acceptance.py`
- `python -m pytest -q tests/test_atlas_recovery_service.py tests/test_atlas_change_snapshot_restore_service.py`
- `python -m py_compile agent/atlas_autonomous_codegen_orchestrator_service.py agent/atlas_recovery_service.py app/api/atlas_autonomous_codegen.py`

## PR title

`PR-G: Integrate candidate workspace and recovery evidence`

---

# PR-H: Prepare evidence-backed draft PR artifacts

## Goal

Make the output of a successful autonomous run reviewable as a draft PR artifact.

## Read first

- `AGENTS.md`
- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_autonomous_execution_readiness_policy.md`
- `app/atlas/draft_pr_creation.py`
- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `app/api/atlas_autonomous_codegen.py`
- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_practical_full_automation_acceptance.py`

## Expected final state

1. Successful or partial verified run produces draft PR body artifact.
2. Draft PR artifact includes goal, files, tests, verification, safety constraints, recovery info.
3. `draft_pr_readiness.ready` is true only with sufficient evidence.
4. Direct merge remains false.
5. Remote git push remains false unless an existing dedicated backend helper is explicitly manually gated.
6. UI shows artifact path/body path, not fake remote PR if none exists.

## Required implementation

1. Draft PR artifact content includes:
   - title
   - requirement summary
   - changed files
   - verification summary
   - failed/skipped items
   - recovery snapshot references
   - safety constraints: no direct merge, no remote git push, no self-apply, no stable runtime mutation, no Vue authority
   - remaining manual review steps
2. `draft_pr_readiness.ready` only true when:
   - run status is completed or acceptable partial
   - changed files exist
   - verification evidence exists
   - no unresolved critical/clarification blockers
   - no repair plan requiring post-repair verification remains unresolved
3. UI shows Draft PR artifact section, body path/artifact path, and remote PR URL only if actual creation result exists.
4. Existing gated draft PR creation/update helpers must remain manually gated and must not add remote credential behavior.
5. Tests cover artifact content, failed verification not ready, repair pending not ready, changed files/test evidence, and forbidden flags false.

## Do NOT

- Do not enable direct merge.
- Do not enable automatic remote git push.
- Do not auto-create PR without explicit existing manual gate.
- Do not fake PR URL.
- Do not mark failed verification as PR-ready.
- Do not change CI behavior.

## Tests

- `python -m pytest -q tests/test_atlas_practical_full_automation_acceptance.py`
- `python -m py_compile app/atlas/draft_pr_creation.py agent/atlas_autonomous_codegen_orchestrator_service.py`
- `node --check web/js/atlas_claude_panel.js`

## PR title

`PR-H: Prepare evidence-backed draft PR artifacts`

---

# PR-I: Improve Atlas Workbench practical automation UX

## Goal

Make Atlas usable as a practical workbench:

Requirement input -> Start Atlas -> Plan Review -> Clarification/Critical Decision -> Execute Preview -> Verification/Repair -> Draft PR Artifact.

The UI must remain display/supervision only.

## Read first

- `AGENTS.md`
- `docs/atlas_practical_full_automation_experience_plan.md`
- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_autonomous_execution_readiness_policy.md`
- `web/js/atlas_claude_panel.js`
- `web/js/atlas_pipeline_api.js`
- `app/api/atlas_autonomous_codegen.py`
- `app/api/atlas_pipeline.py`
- `app/atlas/workflow_state_contract.py`

## Expected final state

1. Atlas has its own requirement input flow independent of general chat assumptions.
2. Chat can still exist, but Atlas workbench flow is clear.
3. Backend remains authoritative.
4. UI uses backend status and controls.
5. No UI-only approval/execution authority.
6. Minimal UI, no heavy redesign.

## Required implementation

1. Workbench flow in buildless ThinUX/FastUI/Claude panel:
   - requirement input
   - Start Atlas
   - plan card
   - clarification prompt
   - critical decision prompt
   - run status
   - verification summary
   - repair plan summary
   - draft PR artifact summary
2. Status-driven controls:
   - `can_answer_clarification`
   - `can_approve_critical_event`
   - `can_reject_critical_event`
   - `can_continue`
   - `can_execute: false`
   - `execute_apply_visible: false`
3. Avoid duplication:
   - plan cards upsert
   - clarification prompts upsert
   - stage blocks upsert
   - final summary upsert
   - reload/recover does not append duplicate stale cards
4. UX text makes clear backend gates decide execution, profile selection alone does not start loop, active envelope is required for autonomous profile, and direct merge/push/self-apply are disabled.
5. Tests cover one plan card per pool/revision, no Approve/Run during blockers, no execute controls for blocked status, draft PR artifact shown only when present, and no Vue authority/default claims.

## Do NOT

- Do not rewrite UI broadly.
- Do not introduce Vue default.
- Do not require npm/Vite build.
- Do not add execution authority to UI.
- Do not hide backend blockers.

## Tests

- `node --check web/js/atlas_claude_panel.js web/js/atlas_pipeline_api.js`
- `python -m pytest -q tests/test_atlas_practical_full_automation_acceptance.py`
- run existing UI contract tests if present

## PR title

`PR-I: Improve Atlas Workbench practical automation UX`

---

# PR-J: Add practical full automation end-to-end acceptance tests

## Goal

Add end-to-end acceptance coverage proving practical automation works safely.

This PR is primarily tests and contract validation.

## Read first

- `AGENTS.md`
- `docs/atlas_practical_full_automation_experience_plan.md`
- `docs/atlas_automation_phase_manifest.json`
- `tests/test_atlas_practical_full_automation_acceptance.py`
- relevant backend/UI modules touched by PR-E through PR-I

## Required E2E scenarios

1. Happy path: docs + code change.
2. Clarification path.
3. Critical event path.
4. Visual failure path.
5. Path policy path.
6. UI normalized status.
7. Manifest/policy truthfulness.

Each scenario must prove blockers are not loosened just to pass tests.

## Do NOT

- Do not add new runtime behavior unless needed only to expose existing testable state.
- Do not loosen blockers to make tests pass.
- Do not mark completion true unless all acceptance tests prove it and docs agree.

## Tests

- `python -m pytest -q tests/test_atlas_practical_full_automation_acceptance.py`
- `python -m pytest -q tests/test_atlas_plan_cancel_clarify_api.py`
- `python -m pytest -q tests/test_atlas_post_scale160_practical_full_automation_manifest_contract.py`
- `python -m pytest -q tests/test_atlas_practical_full_automation_experience_plan.py`

## PR title

`PR-J: Add practical full automation end-to-end acceptance tests`

---

# PR-K: Add CI failure evidence and bounded repair planning

## Goal

Let Atlas ingest CI/test failure evidence and prepare a bounded repair plan.

Do not add unbounded CI-triggered execution.

## Required implementation

1. Add CI failure evidence schema:
   - source
   - run id / job id if available
   - failing command
   - failing test names
   - log excerpt
   - affected files
   - confidence
   - bounded repair recommendation
2. Add repair planning service:
   - classify failure
   - map failure to plan items/files
   - propose bounded repair scope
   - require post-repair verification
3. Integrate metadata:
   - `ci_failure_evidence`
   - `ci_repair_plan`
   - `post_ci_repair_verification_required`
4. Tests cover pytest failure log mapping, unrelated log no fake confidence, allowed path respect, and no automatic execution.

## Do NOT

- Do not fetch remote CI unless an existing connector/helper safely exists.
- Do not run arbitrary commands.
- Do not auto-push repair.
- Do not auto-update PR.
- Do not fabricate CI status.

## PR title

`PR-K: Add CI failure evidence and bounded repair planning`

---

# PR-L: Add self-platform candidate modification mode

## Goal

Allow KasaneCore/Atlas itself to be a target only under strict candidate workspace and safety gates.

## Required implementation

1. Add self-platform target classifier for Atlas/KasaneCore runtime files, policy/manifest/docs/tests, and strict/high risk categories.
2. Require self-improvement gate:
   - `self_improvement=True`
   - active pre-authorized self-improvement envelope
   - strict gate approved
   - candidate workspace evidence present
   - stable runtime mutation false
3. Candidate-only behavior:
   - changes applied only to candidate workspace / artifact path
   - no stable runtime mutation
   - no self-apply
   - no pointer switch
   - no direct merge
4. Required safety grep covers direct merge, remote git push, self-apply, stable runtime mutation, Vue authority, arbitrary unbounded command execution, raw source serving, and startup npm build.
5. Tests cover no strict gate block, strict gate + candidate only, stable runtime block, and manifest/policy change requiring strict review metadata.

## Do NOT

- Do not mutate running app/stable runtime.
- Do not switch release pointer.
- Do not self-apply.
- Do not enable automatic self-modification.

## PR title

`PR-L: Add self-platform candidate modification mode`

---

# PR-M: Add self-platform review gate before draft PR readiness

## Goal

Self-platform changes require stronger review evidence before draft PR readiness.

## Required implementation

1. Add self-platform review gate checking touched files, risk classification, manifest/policy drift, UI default unchanged, Vue not authoritative, forbidden flags false, no raw source serving, no startup npm/Vite/Vue build, and no arbitrary command execution.
2. Add `self_platform_review_gate` metadata:
   - `status`
   - `findings`
   - `blocking_findings`
   - `required_manual_review`
   - `draft_pr_allowed`
3. Draft PR readiness false if self-platform target gate fails; artifact may be prepared only if gate passes, still without merge/push.
4. Tests cover runtime file strict gate, forbidden pattern block, docs-only safe change with manual review note, Vue default block, and forbidden flags false.

## Do NOT

- Do not enable merge.
- Do not enable push.
- Do not auto-approve self-platform changes.
- Do not weaken PR-L strict gate.

## PR title

`PR-M: Add self-platform review gate before draft PR readiness`

---

# PR-N: Add supervised auto-merge readiness report

## Goal

Produce an evidence-backed auto-merge readiness report without merging.

This PR does not enable direct merge.

## Required implementation

1. Add readiness evaluator using CI/test evidence, verification evidence, changed files, risk level, safety grep results, self-platform gate result, manifest/policy drift result, and user approval state.
2. Output:
   - `auto_merge_readiness.status`
   - `ready: true/false`
   - `blocking_reasons`
   - `required_manual_approvals`
   - `ci_green_required`
   - `direct_merge_enabled: false`
   - `merge_executed: false`
3. UI shows readiness report, never shows "merged", and says merge requires explicit future gate/manual action.
4. Tests cover CI missing, safety grep failure, missing self-platform gate, and all evidence present with readiness true but `merge_executed: false`.

## Do NOT

- Do not call merge API.
- Do not push.
- Do not enable direct merge.
- Do not auto-merge anything.
- Do not mark merged.

## PR title

`PR-N: Add supervised auto-merge readiness report`

---

# PR-O: Reconcile practical full automation completion and level semantics

## Goal

Only mark practical full automation complete if acceptance evidence is present. Otherwise keep corrective checkpoint status.

## Required implementation

1. Add completion evaluator requiring evidence from PR-E through PR-N, safety grep clean, and manifest/policy/docs alignment.
2. Manifest update:
   - If all criteria pass: `practical_full_automation_truthfulness_status: accepted_with_evidence` and `practical_full_automation_complete: true`.
   - If not all criteria pass: keep `corrective_checkpoint_in_progress` and list missing criteria.
   - Always keep runtime level semantics explicit and forbidden flags false unless separately gated.
3. Policy update must distinguish bounded practical automation, unbounded automation disabled, self-platform candidate mode, supervised merge readiness, and direct merge still disabled.
4. Update canonical docs only:
   - `docs/atlas_practical_full_automation_experience_plan.md`
   - `docs/atlas_automation_phase_manifest.json`
   - `docs/atlas_autonomous_execution_readiness_policy.md`
5. Tests prove complete true only with evidence, forbidden flags remain false, docs/manifest agree, runtime level semantics are unambiguous, and no stale Vue/default wording remains.

## Do NOT

- Do not mark complete without evidence.
- Do not enable direct merge.
- Do not enable remote push.
- Do not enable self-apply.
- Do not enable stable runtime mutation.
- Do not make Vue authoritative.
- Do not change runtime semantics by docs-only wording.
- Do not delete canonical docs.

## PR title

`PR-O: Reconcile practical full automation completion and level semantics`

---

# Immediate Codex instruction

Start with PR-E-0-G exactly as specified in this file.

Do not start PR-E until PR-E-0-G is merged and CI is green.

After PR-E-0-G, proceed one PR at a time:

PR-E -> PR-F -> PR-G -> PR-H -> PR-I -> PR-J -> PR-K -> PR-L -> PR-M -> PR-N -> PR-O.

For every PR:

- keep scope narrow
- preserve backend authority
- preserve UI display-only semantics
- preserve `direct_merge=false`
- preserve `remote_git_push=false`
- preserve `self_apply=false`
- preserve `stable_runtime_mutation=false`
- preserve Vue authority false
- run focused tests and safety grep
- enable auto-merge only if CI is green and safety invariants remain unchanged
