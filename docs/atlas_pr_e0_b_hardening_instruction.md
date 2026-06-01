# PR-E-0-B: Harden Atlas clarification UX/state and execution blocking before PR-E

This document is the narrow implementation instruction for PR-E-0-B. It refines `docs/atlas_corrective_pr_split_plan_after_1510.md` PR-1 / P0 and must be completed before PR-E or PR-F work continues.

## Context

Continue KasaneCore / Atlas development on latest `main`.

PR-E-0 already has partial implementation on main:

- clarification question queue
- one-question-at-a-time UI
- clarification answer persistence
- clarification replanning service
- plan card upsert
- `visual_contract_failed` detail surfacing

Do not reimplement broadly. First inspect latest `main` and patch only gaps, regressions, or unsafe wording.

## Read first

- `AGENTS.md` when present
- `docs/atlas_full_automation_codex_entrypoint.md`
- `docs/atlas_practical_full_automation_experience_plan.md`
- `docs/atlas_pr_e0_clarification_bugfix_plan.md`
- `docs/atlas_corrective_pr_split_plan_after_1510.md`
- `docs/atlas_automation_phase_manifest.json`
- `docs/atlas_autonomous_execution_readiness_policy.md`
- `app/api/atlas_pipeline.py`
- `agent/atlas_clarification_schema.py`
- `agent/atlas_clarification_service.py`
- `agent/atlas_clarification_replanning_service.py`
- `web/js/atlas_claude_panel.js`
- `web/js/atlas_pipeline_api.js`
- `tests/test_atlas_clarification_service.py`
- `tests/test_atlas_plan_cancel_clarify_api.py`

## Goal

Make PR-E-0 behavior reliable and safe before moving to PR-E.

## Expected final state

1. Independent critique/ambiguity findings are represented as independent clarification questions.
2. UI renders exactly one pending clarification question at a time.
3. Answering one question marks only that question answered.
4. Pending questions remain visible and persisted.
5. `clarification_required` remains true while required questions remain.
6. After all questions are answered, Atlas must not continue using the original plan unless plan revision and gate rerun evidence exists.
7. Backend, not UI, must block unsafe continuation.
8. Plan cards and clarification prompts must be upserted, not duplicated.
9. `visual_contract_failed` must show actionable missing details and repair guidance.
10. Policy/UI wording must not imply preset selection alone enables autonomous execution.

## Required inspection

Verify whether `_clarification_execution_block_reasons(pool)` exists in `app/api/atlas_pipeline.py`.

- If missing, add it.
- If present, harden it.

## Required helper behavior

`_clarification_execution_block_reasons(pool)` must return a list of explicit reason tokens when any of the following is true:

- `pool.metadata.clarification_required is true`
- `pool.metadata.plan_revision_required_after_clarification is true`
- `pool.metadata.gate_rerun_required_after_clarification is true`
- clarification answers exist but `revised_plan_snapshot` is missing
- clarification answers exist but neither `gate_rerun_performed_after_clarification` nor `rerun_critique_gate_after_clarification` / `rerun_safety_gate_after_clarification` exists

Suggested warning tokens:

- `clarification_required`
- `plan_revision_required_after_clarification`
- `gate_rerun_required_after_clarification`
- `missing_revised_plan_snapshot_after_clarification`
- `missing_gate_rerun_evidence_after_clarification`

The helper must be pure:

- no execution
- no safe apply
- no verification
- no file mutation
- no git operations
- no network operations

## Backend enforcement

In `/api/atlas/automation/safe-apply-one`, ensure clarification block reasons are checked before creating or invoking any safe apply service.

If block reasons exist, return a blocked result with:

- `status: blocked`
- warnings containing the reason tokens
- metadata containing:
  - `clarification_execution_blocked: true`
  - `blocked_reasons: [...]`
- current `plan_pool` payload

Also check other execution-like routes if present and easy to cover. Do not broaden scope.

## Clarification queue requirements

Confirm and preserve:

- `AtlasClarificationService.build_question_queue()` creates one question per independent finding/ambiguity.
- each question has `question_id`, `index`, `total`, `title` or `prompt`, `reason`, `source_finding`, `options`, `status`.
- options include safe generic choices when domain-specific choices are unavailable:
  - safest/recommended
  - minimal scope
  - defer/change scope
  - custom/free text
- `apply_answer_to_question_queue()` updates only the target question.
- existing answers for other questions are preserved.
- pending/answered counts are correct.
- invalid or missing `question_id` falls back only to the first pending question, not all questions.

## Clarification API requirements

For `/api/atlas/plan-pools/{pool_id}/clarify`:

- accepts `question_id`, `option_id`, `answer_text`, `note`, `workspace_id`
- stores:
  - `clarification_questions`
  - `clarification_answers`
  - `current_question_index`
  - `pending_question_count`
  - `answered_question_count`
  - `latest_clarification_decision`
  - `plan_revision_required_after_clarification`
  - `gate_rerun_required_after_clarification`
- while pending questions remain:
  - keep `clarification_required: true`
  - do not clear remaining question state
  - do not mark pool ready
- after all questions are answered:
  - either run existing clarification replanning and gate rerun
  - or keep execution blocked with required flags
- never allow a clarified original plan to proceed without revision/gate evidence.

## UI requirements

In `web/js/atlas_claude_panel.js`:

- render one pending question only
- show progress like `確認が必要です: 1/3`
- show prompt, reason, choices, and custom/free-text input
- submitting one answer must refresh the pool and show the next pending question when present
- upsert clarification prompt by pool id
- upsert plan card by `pool_id` + `revision_id`
- do not append duplicate plan cards on reload/recover/clarify
- disable or block Approve and Run when clarification or post-clarification revision/gate rerun is pending
- do not rely only on UI blocking; backend must remain authoritative

## Visual verification UI

For `visual_contract_failed`, ensure the summary/recovery UI shows:

- `metadata.visual_contract.status`
- `metadata.visual_contract.missing`
- warnings beginning with `visual_missing:`
- browser smoke status/reason if present
- repair guidance for browser games:
  - inspect `index.html`
  - add `requestAnimationFrame` loop
  - add input handling
  - separate update/render
  - collision handling if applicable
  - HUD state if applicable
  - visible motion/color/canvas signals

Do not describe `visual_contract_failed` as an environment-only issue. It is a real code-generation failure unless evidence says otherwise.

## Policy/UI wording hardening

Inspect `web/js/atlas_claude_panel.js`, manifest, and policy docs for wording that implies:

- preset selection alone starts autonomous execution
- UI pre-authorises execution
- Vue is authoritative
- unbounded automation is active by default
- fully autonomous execution is generally enabled without backend profile/envelope/gates

Fix wording so it says:

- backend workflow state is authoritative
- profile selection alone never starts an autonomous loop
- autonomous execution requires backend profile + active bounded envelope + gates
- direct merge, remote git push, self-apply, stable runtime mutation, Vue authority, and arbitrary unbounded command execution remain disabled
- current level is a max backend milestone / profile-dependent model, not one always-on unbounded runtime

Consider changing the Claude panel default preset from `autonomous_bounded_dev` to a safer default such as `review_only` or `supervised_auto`, unless backend-persisted profile explicitly selects otherwise. If changing the default creates broad UI churn, leave behavior unchanged but fix comments and add a TODO in the narrowest safe way.

## Tests required

Add or strengthen focused tests.

### Backend tests

- `_clarification_execution_block_reasons` returns expected tokens for:
  - `clarification_required`
  - `plan_revision_required_after_clarification`
  - `gate_rerun_required_after_clarification`
  - answers exist but no `revised_plan_snapshot`
  - answers exist but no gate rerun evidence
- `/api/atlas/automation/safe-apply-one` returns blocked, not 500, when clarification block reasons exist.
- blocked response includes `clarification_execution_blocked: true`.
- after all answers and replanning/gate rerun evidence exists, the helper does not block only because historical `clarification_answers` exist.
- answering one question preserves pending questions.
- all questions answered produces either replanning/gate evidence or keeps execution blocked.

### Frontend/UI tests, if existing pattern allows

- rendering same pool/revision twice produces one plan card.
- clarification prompt is upserted by pool id.
- only current pending clarification question is shown.
- `visual_contract_failed` details include missing checks and `visual_missing` warnings.

### Docs/manifest tests

- existing safety/policy drift tests still pass.
- no active wording says profile selection alone starts a loop.
- no active wording says Vue is authoritative.
- no active wording says direct merge / remote push / self-apply / stable runtime mutation are enabled.

## Commands

Run focused tests first:

```bash
pytest -q tests/test_atlas_clarification_service.py tests/test_atlas_plan_cancel_clarify_api.py
```

Run any new focused tests added by this PR.

Then run:

```bash
python -m py_compile app/api/atlas_pipeline.py agent/atlas_clarification_schema.py agent/atlas_clarification_service.py agent/atlas_clarification_replanning_service.py
node --check web/js/atlas_claude_panel.js web/js/atlas_pipeline_api.js
```

Also run safety grep manually:

- `direct_merge`
- `remote_git_push`
- `self_apply`
- `stable_runtime_mutation`
- `vue_authority`
- `arbitrary command execution`
- `run_command`
- `shell`
- `npm install`
- `Vite`
- `Vue build`
- `raw source serving`
- `fallback redirect`

## Do NOT

- Do not implement broad PR-F autonomous loop changes.
- Do not add new execution capability.
- Do not add arbitrary shell execution.
- Do not enable direct merge.
- Do not enable remote git push.
- Do not enable self-apply.
- Do not enable stable runtime mutation.
- Do not make Vue authoritative.
- Do not add unbounded automation.
- Do not fabricate verification results.
- Do not require npm install, Vite build, Vue build, or Atlas Next dist at server startup.
- Do not refactor unrelated UI or planner code.
- Do not rewrite the roadmap broadly.

## PR scope

Small PR only.

Title suggestion:

`PR-E-0-B: Harden clarification execution blocking and policy wording`

PR body must include:

- Summary
- Files changed
- Tests run
- Safety invariants preserved
- Remaining follow-up for PR-E

## Auto-merge

If CI is green, tests pass, and scope remains limited to PR-E-0-B hardening, auto-merge is allowed.
