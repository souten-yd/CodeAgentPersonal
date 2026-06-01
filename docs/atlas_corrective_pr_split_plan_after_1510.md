# Atlas corrective PR split plan after #1510

This document is the current Codex implementation instruction for correcting the over-declared Atlas A-J/full-automation implementation after PR #1510.

Use this file together with:

- `docs/atlas_full_automation_codex_entrypoint.md`
- `docs/atlas_practical_full_automation_experience_plan.md`
- `docs/atlas_pr_e0_clarification_bugfix_plan.md`
- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_autonomous_execution_readiness_policy.md`

## Why this corrective plan exists

PR #1510 declared broad A-J practical full automation progress. Follow-up review found that the implementation must be converted into a truthful, safe, test-backed practical automation checkpoint before further autonomous expansion.

Do not add new broad features. Do not mark A-J complete. Keep PRs small and corrective.

## Global token-saving operating rules for Codex

- Read the entrypoint and this file first, then only the specific files listed in the current PR section.
- Do not restate long plans in PR comments or final summaries.
- Reuse existing services, helpers, schemas, and tests before creating new ones.
- Avoid broad repository scans once the relevant files are identified.
- Keep diffs small and scoped.
- Keep summaries evidence-based: changed files, tests run, syntax checks, remaining blockers.
- Do not paste large diffs or duplicate this plan in PR bodies.
- If CI passes and the PR is scope-contained and safe, enable auto-merge when available.

## Global hard constraints

Always preserve:

- backend `workflow_state` / PlanPool authoritative
- UI display/supervision only
- no Vue authority
- no direct merge
- no remote git push
- no self-apply
- no stable runtime mutation
- no arbitrary unbounded command execution
- no fabricated verification results
- critical events always require explicit user decision, including under `full_auto` / `autonomous_dev_agent`
- no execution while clarification is pending
- no execution while post-clarification plan revision or gate rerun is incomplete
- clarification answer must not equal execution approval
- bounded repair must remain bounded by allowed paths, profile, envelope, max retries, and verification command policy

## Corrective implementation order

Implement in this order:

1. PR-1 / P0: Clarification execution safety blocker.
2. PR-2 / P1: Clarification UX and concrete remediation options.
3. PR-3 / P1: Repairable verification failure bounded repair loop.
4. PR-4 / P0/P1: Manifest truthfulness, orchestrator preflight hardening, critical-event continuation scope, and acceptance/safety contract tests.

PR-1 is blocking before PR-2/PR-3/PR-4 execution work. PR-4 may be documentation/test-only first if needed, but do not claim A-J completion until all required acceptance and safety contracts are true.

---

# PR-1 / P0: Clarification execution safety blocker

## Goal

Fix Atlas clarification execution safety regression.

During clarification, stale UI buttons such as `承認して実行` must not start patch/proposal/apply/autonomous execution before all clarification questions are answered and before revised plan + critique/safety gate rerun evidence exists.

This must be backend-enforced, not UI-only.

## Read first for PR-1

- `app/api/atlas_pipeline.py`
- `app/api/atlas_autonomous_codegen.py`
- `agent/atlas_clarification_service.py`
- `agent/atlas_clarification_gate_service.py`
- `agent/atlas_clarification_replanning_service.py`
- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `web/js/atlas_claude_panel.js`
- `web/js/atlas_pipeline_api.js`
- `tests/test_atlas_plan_cancel_clarify_api.py`
- `tests/test_atlas_api_pipeline.py`
- `tests/test_atlas_practical_full_automation_acceptance.py`

## Required backend fixes

### 1. Add one shared authoritative blocker

Implement or strengthen a shared helper, for example:

```python
clarification_execution_block_reasons(pool) -> list[str]
```

It must block if any of these are true:

- `pool.metadata["clarification_required"]` is true
- `pending_question_count > 0`
- any item in `clarification_questions` has `status != "answered"`
- `plan_revision_required_after_clarification` is true and `revised_plan_snapshot` is missing
- `gate_rerun_required_after_clarification` is true and `gate_rerun_performed_after_clarification` is not true
- clarification answers are complete but `rerun_critique_gate_after_clarification` is missing
- clarification answers are complete but `rerun_safety_gate_after_clarification` is missing

Use explicit reason strings:

- `clarification_pending`
- `clarification_questions_unanswered`
- `clarification_revision_required`
- `clarification_gate_rerun_required`
- `clarification_rerun_critique_missing`
- `clarification_rerun_safety_missing`

### 2. Apply the blocker before every execution path

Block before:

- patch proposal
- patch generation
- autonomous codegen start
- multi-item autopilot run
- safe apply
- continuation / execute plan APIs
- approval-and-execute route

Blocked responses must include:

- `status: blocked_safety_review`
- `phase: needs_scope_confirmation` or `revising_plan_from_clarification`
- `stop_reason: clarification_pending` or `clarification_revision_gate_rerun_required`
- `metadata.blocked_reasons: [...]`
- `next_required_user_action: "Answer remaining clarification"` or `"Revised plan and gate rerun required before implementation"`

### 3. Fix `clarify_plan_pool` semantics

In `clarify_plan_pool`:

- recording an answer only records clarification
- do not approve execution
- do not start patch/proposal/apply
- if pending questions remain:
  - `pool.status = needs_scope_confirmation`
  - `clarification_required` remains true
- if all answers are complete:
  - run plan revision
  - rerun critique gate
  - rerun safety/automation gate
  - only then update `pool.status`
- if gates allow bounded execution, `pool.status` may become `ready`
- if gates require review, `pool.status` must be `approval_required` or `needs_revision`
- if clarification raises critical/safety scope, `pool.status` must be `waiting_for_critical_decision`

Persist:

- `clarification_answers`
- selected option impact if available
- `original_plan_snapshot`
- `revised_plan_snapshot`
- `plan_revision_diff`
- `rerun_critique_gate_after_clarification`
- `rerun_safety_gate_after_clarification`
- `gate_rerun_performed_after_clarification`
- `next_required_user_action`

### 4. Fix status/control contract

Backend status must expose:

- `controls.can_execute = false` during clarification
- `controls.can_continue = false` during clarification unless the next action is only answering clarification
- `controls.execute_apply_visible = false`
- `decision_targets.clarification.required = true` while pending questions or gate evidence is missing
- `next_action = "Answer remaining clarification"` or `"Revised plan and gate rerun required before implementation"`

### 5. Minimal UI safety fix

In `web/js/atlas_claude_panel.js`:

- do not show `承認して実行` in clarification context
- disable clicked clarification option buttons immediately
- remove stale clickable buttons after answering
- render at most one active clarification card per pool
- if backend says clarification/revision/gate-rerun is pending, show waiting/clarification state, not execution controls

## PR-1 tests

Add/update tests for:

- `pending_question_count > 0` blocks autonomous codegen
- `pending_question_count > 0` blocks patch generation
- `pending_question_count > 0` blocks safe apply
- one answer with remaining questions still blocks execution
- all answers complete but `revised_plan_snapshot` missing blocks execution
- all answers complete but gate rerun evidence missing blocks execution
- `clarify_plan_pool` does not mark answer as execution approval
- UI/status has no executable control during clarification
- clarification context does not render `承認して実行`

## PR-1 verification

Run:

- `pytest tests/test_atlas_plan_cancel_clarify_api.py`
- `pytest tests/test_atlas_api_pipeline.py`
- `pytest tests/test_atlas_practical_full_automation_acceptance.py`
- any new clarification safety tests
- `python -m py_compile` on changed Python files
- `node --check web/js/atlas_claude_panel.js`
- `node --check web/js/atlas_pipeline_api.js` if changed

---

# PR-2 / P1: Clarification UX and concrete remediation options

## Goal

Improve Atlas clarification UX so user confirmation is understandable and actionable.

The current prompt exposes internal labels such as `missing_steps` and presents vague options that do not meaningfully differ. Atlas must analyze the detected issue and present concrete remediation options before asking the user.

## Read first for PR-2

- `app/api/atlas_pipeline.py`
- `agent/atlas_clarification_service.py`
- `agent/atlas_clarification_gate_service.py`
- `agent/atlas_clarification_replanning_service.py`
- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_clarification_gate_service.py`
- `tests/test_atlas_plan_cancel_clarify_api.py`
- `tests/test_atlas_api_pipeline.py`

## Required behavior

### 1. Replace internal labels with human-readable issue cards

Do not show `missing_steps` as the primary visible title. Internal signals may remain in metadata only.

Clarification question structure should include:

- `question_id`
- `title`
- `user_facing_issue_summary`
- `why_it_matters`
- `detected_signal_metadata`
- `recommended_option_id`
- `remediation_options_generated_by`
- `options[]`

Each option must include:

- `option_id`
- `label`
- `description`
- `plan_change_summary`
- `implementation_scope`
- `risk_level`
- `gate_rerun_required`
- `can_continue_after_answer`
- `requires_text`

### 2. Generate concrete remediation options

Add/update a helper in `agent/atlas_clarification_service.py`, or a small focused helper if necessary.

Input should include:

- ambiguity signals
- plan summary / root goal
- affected plan items when available
- target files when available
- critique finding details when available

Output concrete, distinct options with impact preview.

If an LLM provider is available in this path, use it to generate remediation options. If no LLM provider is available, use deterministic templates and set:

- `remediation_options_generated_by: "template_fallback"`

Do not claim LLM usage unless it actually happened.

### 3. Game-over/restart/missing loop example

For missing game-over/restart/loop behavior, generate a card like:

Title:

`Game-over and restart behavior is missing`

Issue summary:

`Atlas detected that the plan does not yet define how the game ends, how the game-over screen appears, or how the player restarts after a collision.`

Why it matters:

`Without this, Atlas may implement collision detection but leave the game unable to transition into a clear game-over/restart state.`

Options:

- Recommended safe fix: add a simple game state model `playing -> game_over -> restart`; on collision, stop the loop, show a Game Over overlay, and allow Space/Click to restart.
- Minimal fix: add only collision-triggered game-over state and restart handling, without changing unrelated gameplay.
- Defer/remove: remove or defer the unclear game-over/restart requirement from this plan and continue with the rest.
- Custom: user specifies exactly how game-over and restart should work.

### 4. Use selected option metadata during replanning

`agent/atlas_clarification_replanning_service.py` must consume selected option impact, not only `option_id` or raw answer text.

Plan revision should reflect:

- selected `plan_change_summary`
- `implementation_scope`
- `risk_level`
- custom answer if present
- affected files/items if present

At minimum:

- update relevant item goal/description/expected_changes/done_definition/test intent
- store actual changed fields in `plan_revision_diff`
- rerun critique and safety gates after revision

### 5. UI rendering

In `web/js/atlas_claude_panel.js`:

- show title
- show issue summary
- show why it matters
- show recommended badge/label
- show option label/description
- show option impact preview
- do not show raw JSON
- do not show `missing_steps` as primary text
- keep UI minimal
- do not add new execution buttons

## PR-2 tests

Add/update tests for:

- `missing_steps` / game-over ambiguity creates human-readable title
- internal signal names remain metadata-only
- options are concrete and distinct
- each option has `plan_change_summary`, `implementation_scope`, `risk_level`, `gate_rerun_required`, `can_continue_after_answer`, `requires_text`
- selected option impact is persisted
- selected option impact is consumed by clarification replanning
- UI prompt can render title/summary/why/options without raw JSON
- UI prompt does not render `missing_steps` as primary visible title

## PR-2 verification

Run:

- `pytest tests/test_atlas_clarification_gate_service.py`
- `pytest tests/test_atlas_plan_cancel_clarify_api.py`
- `pytest tests/test_atlas_api_pipeline.py`
- any new clarification UX tests
- `python -m py_compile` on changed Python files
- `node --check web/js/atlas_claude_panel.js`
- `node --check web/js/atlas_pipeline_api.js` if changed

---

# PR-3 / P1: Repairable verification failure bounded repair loop

## Goal

Implement bounded repair and re-verification after repairable verification failures.

After Apply succeeds, Verify can fail with:

- `verification_failed:visual_contract_failed`
- missing `animation_signal`
- missing `motion_signal`
- missing `color_mutation_signal`
- `browser_smoke_failed: playwright_error`

Atlas currently stops at Summary. For a practical autonomous code-generation loop, repairable verification failures should enter:

`failure_analysis -> bounded_repair_plan -> repair_patch_generation -> repair_apply -> re_verify`

## Read first for PR-3

- `app/api/atlas_autonomous_codegen.py`
- `app/api/atlas_pipeline.py`
- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `agent/atlas_multi_item_autopilot_service.py`
- `agent/atlas_recovery_service.py`
- `agent/atlas_patch_proposal_schema.py`
- `agent/atlas_plan_pool_schema.py`
- `web/js/atlas_claude_panel.js`
- `tests/test_atlas_practical_full_automation_acceptance.py`
- any existing visual/browser verification tests

## Required behavior

### 1. Detect repairable verification failures

At minimum detect:

- `visual_contract_failed`
- `visual_missing:animation_signal`
- `visual_missing:motion_signal`
- `visual_missing:color_mutation_signal`
- browser smoke failure where app visual contract also failed or is unknown

Convert failure into a structured failure summary:

- `user_facing_title`
- `user_facing_summary`
- `failed_contracts`
- `likely_cause`
- `recommended_repair_steps`
- `affected_files`
- `repair_scope`
- `can_attempt_bounded_repair`
- `retry_count_remaining`
- `verification_tool_error` if browser smoke failed with Playwright error
- `app_visual_contract_failed` when known

For this case:

Title:

`Visual verification failed: game does not show required motion/animation evidence`

Summary:

`Atlas changed index.html and style.css, but verification could not detect visible animation, motion, or color/state changes. Browser smoke also failed under Playwright, so Atlas should inspect the generated HTML/CSS and repair the runtime loop or visible signals.`

Recommended repair steps:

- inspect `index.html` and `style.css`
- add or fix `requestAnimationFrame` loop
- ensure visible object position changes over time
- ensure canvas/DOM visual state changes are observable
- add visible color/state mutation where appropriate
- preserve existing game requirements
- rerun focused visual verification

### 2. Add bounded repair plan

When verification fails and repair is allowed by profile/envelope/policy:

- transition to `failure_analysis`
- create bounded repair plan
- limit repair files to allowed changed files unless explicitly allowed
- generate repair patch only for allowed files
- apply repair only if safe gates allow it
- rerun focused verification
- stop only after:
  - verification passes
  - max retries exhausted
  - repair blocked by policy/envelope
  - clarification/critical gate blocks continuation

Repair task must include:

- `failure_summary`
- `affected_files`
- `allowed_repair_files`
- `concrete_repair_steps`
- `retry_index`
- `max_retries`
- `post_repair_verification_required: true`

### 3. Persist evidence

Persist:

- `verification_failure_summary`
- `repair_plan`
- `repair_attempts`
- `files_allowed_for_repair`
- `retry_count`
- `post_repair_verification_result`
- `final_status`

### 4. Draft PR readiness

If verification remains failed:

- `draft_pr_readiness.ready = false`
- `draft_pr_artifact.ready = false`
- final summary must say verification failed
- no evidence-backed success summary

Only set ready true after post-repair verification passes.

### 5. UI/status display

Replace raw wall-of-text as primary display with:

- error title
- what failed
- why it matters
- changed files
- recommended repair steps
- retry remaining
- whether bounded repair is available
- tool/browser error details in secondary/collapsed details

Keep raw diagnostics available but not primary.

If backend supports bounded repair and retries remain, UI may show:

- `修復案を作成`
- `安全な範囲で再修復`

Only show these when backend status says bounded repair is allowed. Do not show repair action while clarification/safety gate blocks execution.

## PR-3 tests

Add/update tests for:

- `visual_contract_failed` creates structured failure summary
- missing animation/motion/color signals map to concrete repair steps
- Playwright error is represented as `verification_tool_error`, not hidden
- visual failure creates bounded repair task when allowed
- repair patch is limited to allowed files
- re-verification is required after repair
- post-repair verification result is persisted
- `draft_pr_readiness` remains false until verification passes
- terminal stop occurs only after max retries exhausted or repair blocked
- no visual failure is marked passed without post-repair evidence
- UI/status exposes structured failure summary without raw wall-of-text as primary content

## PR-3 verification

Run:

- `pytest tests/test_atlas_practical_full_automation_acceptance.py`
- any existing visual/browser verification tests
- any new visual verification repair tests
- `python -m py_compile` on changed Python files
- `node --check web/js/atlas_claude_panel.js`
- `node --check web/js/atlas_pipeline_api.js` if changed

---

# PR-4 / P0/P1: Truthful checkpoint, orchestrator preflight, critical scope, and acceptance contracts

## Goal

Fix the over-declared Atlas A-J full automation implementation after PR #1510. Convert the current implementation into a truthful, safe, test-backed practical automation checkpoint.

This PR must not add new broad features. It should tighten truthfulness and contracts around the implementation produced by PR #1510 and the corrective PRs above.

## Read first for PR-4

- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_full_automation_codex_entrypoint.md`
- `docs/atlas_practical_full_automation_experience_plan.md`
- `docs/atlas_pr_e0_clarification_bugfix_plan.md`
- `docs/atlas_autonomous_execution_readiness_policy.md`
- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `agent/atlas_critical_replanning_service.py`
- `agent/atlas_approval_service.py`
- `app/api/atlas_autonomous_codegen.py`
- `web/js/atlas_claude_panel.js`
- `web/js/atlas_pipeline_api.js`
- `tests/test_atlas_practical_full_automation_acceptance.py`

## Required fixes

### 1. Correct manifest truthfulness

In `docs/atlas_automation_phase_manifest.json`, do not mark A-J/full practical automation as fully complete unless the implementation is truly end-to-end verified.

Review and correct:

- `practical_full_automation_complete`
- `ui_practical_experience_complete`
- `stable_runtime_mutation_apply_complete`
- `self_improvement_practical_loop_complete`
- `draft_pr_experience_complete`
- `current_automation_track`
- `next_automation_track`
- `current_level`
- `current_level_note`

Keep max runtime milestone language if needed, but make clear the active runtime remains bounded/profile/envelope-gated and not always-on fully autonomous.

### 2. Tighten autonomous orchestrator preflight

In `agent/atlas_autonomous_codegen_orchestrator_service.py`:

- enforce `allowed_paths` / `blocked_paths` against all target files before patch generation and before autopilot run
- ensure `max_actions`, `max_items`, `max_changed_files_total`, `max_changed_files_per_item` are bounded by selected profile/envelope
- use envelope bounds as the upper bound; request values must not expand envelope limits
- if `allowed_verification_commands` is present, pass it into verification/autopilot only as an allow-list, or block execution when unsupported
- do not rely on metadata-only safety claims
- before continuing after critical-event approval, verify the approval decision exists and restrict continuation to explicitly approved bounded scope

### 3. Make critical-event continuation explicit

In `agent/atlas_approval_service.py` and the autonomous orchestrator:

- pool-level critical approved path must not simply become generic `approval_required` with ambiguous continuation
- persist `approved_scope`, `approved_paths`, `approved_item_ids`, or equivalent bounded scope evidence
- autonomous continuation must check this evidence
- rejected/NG critical events must keep original path non-executable and only allow lower-impact revised candidate after gate rerun

Add regression tests for:

- full_auto/autonomous profile still blocks critical event before user decision
- approved critical event proceeds only inside approved scope
- rejected critical event creates lower-impact candidate and original item cannot execute
- lower-impact candidate that triggers another critical event returns to `waiting_for_critical_decision`

### 4. Make acceptance tests real enough to justify status

Current acceptance tests are too mock-heavy. Add focused tests that exercise actual service boundaries without broad integration flakiness:

- clarification queue -> final answer -> revised PlanPool -> gate rerun evidence -> safe apply blocked/unblocked appropriately
- autonomous codegen preflight blocks missing active envelope for `autonomous_dev_agent`
- `allowed_paths` / `blocked_paths` are enforced
- `allowed_verification_commands` is honored or safely rejected if unsupported
- failed verification creates bounded repair evidence and does not mark draft PR ready
- completed verification creates final summary and draft PR artifact, but no direct merge/push/self-apply flags
- UI normalized status never exposes execute/apply controls

### 5. Fix UI status/control semantics

In `app/api/atlas_autonomous_codegen.py` and `web/js/atlas_claude_panel.js`:

- keep UI display-only
- do not show `backend action available` wording for actions that are not actually implemented or allowed
- stop/cancel/continue controls must reflect backend-authoritative state
- for `blocked_safety_review` caused by clarification or critical event, the only next action must be answer clarification or make critical decision
- raw JSON remains hidden by default

### 6. Add safety grep/contract tests

Add or extend a test that asserts:

- no direct merge enabled
- no remote git push enabled
- no self-apply enabled
- no stable runtime mutation enabled
- no `execute_apply_visible` in autonomous UI status
- critical events require user decision under `autonomous_dev_agent`
- manifest does not claim full completion unless the required acceptance tests exist and pass

## PR-4 verification

Run:

- `pytest tests/test_atlas_practical_full_automation_acceptance.py`
- `pytest tests/test_atlas_plan_cancel_clarify_api.py`
- `pytest tests/test_atlas_clarification_gate_service.py`
- `pytest tests/test_atlas_api_pipeline.py`
- any new tests added for this fix
- `python -m py_compile` on changed Python files
- `node --check` on changed JS files

## PR-4 policy

Make this a small corrective PR. If too large, split into:

- PR-4a: manifest truthfulness + safety contract tests
- PR-4b: orchestrator preflight hardening
- PR-4c: critical-event continuation scope
- PR-4d: acceptance test strengthening

Do not implement unrelated features. Do not rewrite the full roadmap. Do not change runtime semantics beyond tightening safety and truthfulness.
