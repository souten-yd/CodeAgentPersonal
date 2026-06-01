# Atlas PR-E-0 Clarification Bugfix Plan

## Status

This is a blocking pre-PR for the practical full automation track.

Implement this **before PR-E** in `docs/atlas_practical_full_automation_experience_plan.md`.

Reason: the current Claude-style Atlas panel can incorrectly render multiple independent critique findings as one single-choice clarification prompt, clear all clarification state after one selection, duplicate the same plan card, and hide the actionable details for `visual_contract_failed` verification failures. These issues make the later clarification-driven plan revision loop unsafe and confusing.

## Task

Fix Atlas clarification UX/state bugs and improve visual verification failure surfacing.

## Goal

Atlas must ask clarification questions as a queue of independent questions, one question at a time, with concrete choices plus custom input. Answering one question must not clear the remaining questions. The UI must not duplicate the same plan, and visual verification failures must show concrete missing contract details.

## Scope

- Fix clarification question modeling and rendering.
- Fix clarification state progression.
- Fix duplicate plan rendering.
- Improve `visual_contract_failed` UI/actionability.
- Add tests for the above.

## Hard constraints

- Do not implement broad autonomous loop changes in this PR.
- Do not enable direct merge.
- Do not enable remote git push.
- Do not enable self-apply.
- Do not enable stable runtime mutation.
- Do not make Vue authoritative.
- Do not add arbitrary shell execution.
- Do not add unbounded automation.
- Do not fabricate verification results.
- Backend `workflow_state` remains authoritative.
- UI remains display/supervision only.
- Buildless ThinUX/FastUI must remain usable.
- Do not require `npm install`, Vite build, Vue build, or Atlas Next dist at server startup.

## Files to inspect

- `app/api/atlas_pipeline.py`
- `agent/atlas_clarification_service.py`
- `agent/atlas_clarification_schema.py`
- `agent/atlas_plan_quality_gate.py`
- `agent/atlas_clarification_gate_service.py`
- `web/js/atlas_claude_panel.js`
- `web/js/atlas_dashboard.js`
- `web/js/atlas_pipeline_api.js`
- `agent/atlas_auto_verification_service.py`
- `agent/atlas_visual_artifact_verifier.py`
- `tests/test_atlas_clarification_service.py`
- `tests/test_atlas_api_pipeline.py`
- `tests/test_atlas_dashboard_ui_contract.py`
- Existing Claude panel / UI contract tests, if present.

## Observed bugs

### Bug 1: Independent findings are rendered as one option list

Current behavior can convert multiple critique findings such as `missing_steps`, `maintainability`, and `requirement_alignment` into one shared option list. These are not alternative answers to one question. They are independent clarification/revision issues.

Correct behavior:

```text
Question 1/3: clarify game loop timing
choices: requestAnimationFrame / fixed timestep + rAF / setInterval / custom input

Question 2/3: clarify file structure
choices: single index.html / split HTML-CSS-JS / start single and later split / custom input

Question 3/3: clarify test scope
choices: browser smoke + visual contract / JS unit + browser smoke / manual-only / custom input
```

### Bug 2: Selecting one clarification answer clears all questions

Current behavior can remove the entire clarification prompt in the UI and clear `clarification_required` in backend after one option is selected. Remaining independent questions disappear.

Correct behavior:

- Answering question 1 marks only question 1 answered.
- Pending questions remain.
- `clarification_required` remains true until all required questions are answered.
- Only after all required questions are answered may clarification state move to plan revision / gate rerun.

### Bug 3: Plan card is duplicated

The Claude panel can append the same plan card repeatedly for the same pool when `renderPlanPoolMarkdown()` is called after creation, reload, recover, or clarification.

Correct behavior:

- Plan cards must be upserted by stable key.
- The same pool must have only one active plan card unless a new revision id is created.

### Bug 4: `visual_contract_failed` is not actionable enough

Current summary can show only `verification_failed:visual_contract_failed`. The user also needs the concrete missing checks and repair guidance.

Correct behavior:

- Show `metadata.visual_contract.missing`.
- Show warnings such as `visual_missing:animation_signal`, `visual_missing:motion_signal`, and `visual_missing:color_mutation_signal`.
- Show browser smoke status/reason when available.
- Keep this as a real code-generation failure, not an environment failure.

## Required implementation

### 1. Normalize clarification into a question queue

Replace shared `critique_clarification_options.options` semantics with a backend-owned question queue.

Each independent finding or ambiguity must become one question object, not one option in a shared question.

Required question shape:

```json
{
  "question_id": "clar_q_1",
  "index": 1,
  "total": 3,
  "title": "Clarify game loop timing",
  "prompt": "How should Atlas implement the game loop timing?",
  "reason": "The plan mentions a game loop but does not specify requestAnimationFrame, fixed timestep, or interval timing.",
  "source_finding": {},
  "options": [
    {
      "option_id": "raf",
      "label": "requestAnimationFrame",
      "description": "Use browser-native frame scheduling and compute delta time.",
      "effect": {"timing_model": "requestAnimationFrame"}
    },
    {
      "option_id": "fixed_timestep_raf",
      "label": "Fixed timestep + requestAnimationFrame",
      "description": "Use rAF rendering with deterministic fixed-step updates.",
      "effect": {"timing_model": "fixed_timestep_raf"}
    },
    {
      "option_id": "set_interval",
      "label": "setInterval",
      "description": "Use a simple interval loop. Lower quality for games; only use when explicitly requested.",
      "effect": {"timing_model": "setInterval"}
    },
    {
      "option_id": "custom",
      "label": "自由入力 / Custom",
      "requires_text": true
    }
  ],
  "status": "pending"
}
```

The exact domain-specific options may be generated by existing heuristic logic. If robust domain-specific options are not available, create safe generic options:

- safest/recommended approach
- minimal-scope approach
- defer/change scope
- custom/free-text input

### 2. Show only one question at a time

In `web/js/atlas_claude_panel.js`, render the current pending question only.

UI must show:

- `確認が必要です: 1/3`
- current question prompt
- why Atlas is asking
- three concrete choices when available
- one custom/free-text input option

Do not show all independent questions as one button list.

After answering question 1, render question 2/3 if pending questions remain.

### 3. Do not clear all clarification state after one answer

Update `/api/atlas/plan-pools/{pool_id}/clarify` to accept:

- `question_id`
- `option_id`
- `answer_text` or `note`
- `workspace_id`

Backend behavior:

- Find the matching question.
- Mark only that question as answered.
- Store the selected option and free-text answer.
- Preserve remaining pending questions.
- Keep `pool.metadata.clarification_required = true` while pending questions remain.
- Clear `clarification_required` only when all required questions are answered.

### 4. Persist clarification progress

Persist at least:

- `clarification_questions`
- `clarification_answers`
- `current_question_index`
- `pending_question_count`
- `answered_question_count`
- `latest_clarification_decision`
- `plan_revision_required_after_clarification`
- `gate_rerun_required_after_clarification`

Each answer should preserve:

- `question_id`
- `option_id`
- `answer_text`
- selected option payload
- source finding / reason
- answered timestamp when available

### 5. Block execution until plan revision/gate rerun exists

For this PR-E-0 bugfix, a full plan revision service is not required. That belongs to PR-E.

However, once clarification answers exist, execution must not proceed as if the original plan is safe.

Minimum required guard:

- If clarification answers exist and there is no `revised_plan_snapshot` / gate rerun evidence, set or keep:
  - `plan_revision_required_after_clarification: true`
  - `gate_rerun_required_after_clarification: true`
- Disable or block `Approve and Run` while either:
  - `clarification_required == true`
  - `gate_rerun_required_after_clarification == true`
  - `plan_revision_required_after_clarification == true`

Backend must be authoritative. UI may hide/disable controls, but backend must also prevent unsafe continuation.

### 6. Fix duplicate plan rendering

In `web/js/atlas_claude_panel.js`:

- `renderPlanPoolMarkdown()` / `appendStrategicPlanCard()` must upsert instead of always append.
- Add stable DOM keys:
  - `data-atlas-plan-card="true"`
  - `data-pool-id="<pool_id>"`
  - optional `data-plan-revision-id="<revision_id>"`
- If a card for the same pool/revision already exists, replace/update it instead of appending another one.

Also apply dedupe/upsert to:

- clarification prompt: one active clarification prompt per pool
- stage block restore: avoid appending duplicate stage blocks for the same pool/run

### 7. Improve `visual_contract_failed` details

In the Claude panel and/or dashboard summary, when verification fails with `visual_contract_failed`:

Show:

- `metadata.visual_contract.status`
- `metadata.visual_contract.missing`
- warnings beginning with `visual_missing:`
- browser smoke status/reason when present

Recommended user-facing text:

```text
Visual contract failed: missing animation/motion/color signals. For a browser game, index.html must include a real game loop such as requestAnimationFrame, player/input update, collision/render loop, and visible HUD state.
```

Do not treat `visual_contract_failed` as an environment problem. It is a real code-generation failure.

### 8. Improve recovery guidance for visual failures

For `visual_contract_failed`, suggest:

- run Debug Review
- inspect `index.html`
- generate a repair patch that adds:
  - `requestAnimationFrame` game loop
  - input handling
  - update/render separation
  - collision handling
  - HUD state
  - visible motion/color/canvas signals required by the visual contract

Do not suggest only generic manual restore.

## Tests

### Backend clarification queue

- Given three blocking findings, backend creates three question objects.
- Each question has `index`, `total`, and its own `options`.
- First answer marks only question 1 answered.
- Pending questions remain.
- `clarification_required` remains true until all required questions are answered.

### Frontend clarification UI contract

- Claude panel renders `1/3`.
- It shows only the first question.
- It shows three choices plus custom input option.
- Selecting one answer does not remove remaining questions.
- Existing clarification prompt is replaced, not duplicated.

### Duplicate plan rendering

- Calling `renderPlanPoolMarkdown()` twice for the same pool results in one plan card.
- Reload/recover does not duplicate the same plan.
- Clarify response does not append a duplicate plan card unless a plan revision creates a new revision id.

### Execution block

- `Approve and Run` is disabled/blocked while `clarification_required` is true.
- `Approve and Run` is disabled/blocked when `gate_rerun_required_after_clarification` is true.
- Backend blocks unsafe continuation even if the UI is bypassed.

### Visual verification detail

- `visual_contract_failed` summary includes missing static checks.
- `visual_missing:*` warnings are visible.
- Browser smoke reason is visible when present.

## Commands to run

Run the smallest focused suite first:

```bash
pytest -q tests/test_atlas_clarification_service.py tests/test_atlas_api_pipeline.py tests/test_atlas_dashboard_ui_contract.py
```

Then add any new focused tests required by the implementation.

Also run:

```bash
python -m py_compile <changed-python-files>
node --check web/js/atlas_claude_panel.js web/js/atlas_dashboard.js web/js/atlas_pipeline_api.js
```

Only run broader suites after focused tests pass.

## Acceptance criteria

- Independent clarification findings are modeled as independent questions.
- UI shows one question at a time with `1/N` progress.
- Each question has its own options plus custom input.
- Answering one question does not clear pending questions.
- Backend preserves clarification state until all required questions are answered.
- Clarification answers require plan revision and gate rerun before implementation can proceed.
- The same plan is not duplicated in the transcript for the same pool/revision.
- `visual_contract_failed` shows actionable missing details and repair guidance.
- No direct merge, remote push, self-apply, stable runtime mutation, Vue authority, arbitrary unbounded command execution, or fabricated verification result is introduced.

## Follow-up

After PR-E-0 is merged, continue with PR-E from the practical full automation plan:

- user answer -> revise requirement / plan / PlanItem fields
- rerun adversarial critique
- rerun safety / automation gates
- continue only when safe, approved, and bounded
