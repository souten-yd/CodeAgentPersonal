# Atlas Workbench Autopilot Goal Mode Plan

This document is the implementation brief for Codex Goal Mode.

It records the next Atlas Workbench improvements after the observed multi-item Autopilot failure around UI / HTML / game generation, patch proposal progress, verification handling, next-action controls, larger implementation scale, and PlanPool reuse.

Use this file as the first document to read when starting the related Codex goal.

---

## Codex Goal Mode entrypoint

Use this goal text:

```text
Goal:
Implement the selected slice from docs/atlas_workbench_autopilot_goal_mode_plan.md.

Objective:
Make Atlas Workbench reliable for UI, HTML, game, and visual app generation by adding MVP-first planning, bounded repair after ordinary verification failure, visible next-action controls, clearer progress display, PlanPool reuse, and staged large-development support.

Stopping condition:
Stop when the selected slice has focused code changes, regression tests, syntax checks, and a concise implementation summary. Do not continue into unrelated slices unless explicitly requested.

Read first:
- docs/atlas_workbench_autopilot_goal_mode_plan.md
- Atlas Workbench multi-item autopilot routes/services
- PlanPool storage/status/result code
- Atlas Claude panel JavaScript
- auto verification and requirement coverage tests

Hard constraints:
- Backend PlanPool remains authoritative.
- UI only displays state and requests actions; backend decides whether actions are allowed.
- Keep each PR focused and testable.
- Preserve existing Atlas safety gates.
- Do not broaden command permissions or repository write behavior as part of these slices.

Final response must include:
- changed files
- tests added or updated
- tests run
- behavior changed
- safety invariants preserved
- remaining blockers
```

---

## Current issue

Example request:

```text
インベーダーゲームを作って。スターフォックス風の3D奥行き表示でお願い。
```

Observed behavior:

- Atlas creates an 11-item PlanPool.
- Patch proposal progress appears to reach 11/11.
- Autopilot execution then shows item 1/11 and stops.
- Error: `verification_failed:requirement_coverage_incomplete`.
- UI says next action is retry, revise plan, cancel, but no usable buttons are shown.

Main problems:

1. The plan is waterfall-like and starts with setup/scaffolding, not a runnable MVP.
2. Item 1 is checked as if it must satisfy the whole user requirement.
3. Partial multi-item progress is treated as final requirement failure.
4. Verification failure stops immediately instead of trying a bounded repair.
5. UI shows next-action text without action controls.
6. Proposal-generation progress and execution progress are visually mixed.
7. Users cannot easily rerun the same PlanPool.
8. Larger development needs staged execution support instead of being limited to tiny patches.

---

## Target behavior

Atlas Workbench should:

1. Prefer MVP-first planning for UI / HTML / game / visual app tasks.
2. Generate patch proposals with trusted server-side coverage metadata.
3. Display patch proposal progress separately from Autopilot execution progress.
4. Verify the current PlanItem against its own acceptance criteria.
5. Treat pool-level requirement coverage as progress/warning until final rollup.
6. Try bounded repair for ordinary verification failures.
7. Render buttons for retry, repair, revise plan, cancel, and details when those actions are available.
8. Allow users to rerun an existing PlanPool without regenerating the plan.
9. Support larger work through staged milestones, checkpoints, and bounded verification.

---

## Implementation slices

### Slice A: item-level vs pool-level requirement coverage

Priority: Critical.

Goal:
Do not fail item 1/11 just because the whole pool requirement is not complete yet.

Required behavior:

- Item-level verification checks only the current PlanItem goal, done definition, acceptance criteria, changed files, and trusted coverage metadata.
- Pool-level requirement coverage is progress/warning during partial multi-item execution.
- Pool-level coverage becomes enforceable only at final rollup or when a patch explicitly covers all relevant PlanItems.

Acceptance criteria:

- A multi-item plan with scaffolding as item 1 can pass item 1 if item 1 criteria are met.
- Partial progress does not stop with `requirement_coverage_incomplete`.
- Final rollup still detects true missing requirement coverage.

Tests:

- Add a two-item Hello World + rainbow CSS regression.
- Item 1 should pass without requiring the full rainbow requirement.
- Final rollup should still validate the complete requirement.

---

### Slice B: bounded repair after ordinary verification failure

Priority: Critical.

Goal:
Verification failure should usually lead to repair, not immediate terminal stop.

Repairable failures include:

- syntax/check failure
- missing file
- missing acceptance evidence
- smoke test failure
- visual evidence gap
- current-item requirement coverage gap

Must-stop failures include:

- safety block
- clarification required
- missing approval
- invalid active execution context
- unauthorized file scope
- denied command
- policy gate violation

Required behavior:

- Capture verification evidence.
- Generate a repair proposal scoped to the failed item.
- Recheck according to the existing approval and safety model.
- Retry verification up to a bounded maximum.
- If repair attempts are exhausted, stop with visible user actions.

Acceptance criteria:

- Repairable failure enters repair flow.
- Repair attempts are bounded.
- Safety failures do not auto-repair.
- Stopped state includes usable actions.

---

### Slice C: visible next-action buttons

Priority: Critical.

Goal:
If the result says retry, revise plan, or cancel, the UI must show matching buttons.

Buttons:

- 修復して続行
- 再試行
- Planを修正
- キャンセル
- 詳細を見る

Rules:

- Backend exposes `can_retry`, `can_repair`, `can_revise_plan`, `can_cancel`, `can_rerun_pool`, `can_execute`, and `can_continue`.
- UI renders buttons from backend-authorized state.
- Disabled buttons must show a reason.
- Do not show next-action text without controls.

Acceptance criteria:

- Failed Autopilot result renders action buttons at the bottom of the Workbench result card.
- Buttons call existing or newly added action endpoints.
- UI does not become the execution authority.

---

### Slice D: MVP-first planning for UI / HTML / game generation

Priority: High.

Goal:
Make generated plans suitable for Autopilot execution.

Trigger task types:

- UI generation
- HTML page generation
- games
- canvas or WebGL demos
- visual interactive apps

Planner behavior:

- First executable PlanItem should produce a visible runnable artifact.
- Avoid setup-only, research-only, library-choice-only, and skeleton-only first items unless the user explicitly asks for architecture-only planning.
- Later items may improve architecture, tests, performance, and polish.

For the Space Invaders + Star Fox-style request, item 1 should include:

- `index.html`
- visible canvas or game area
- player movement
- visible enemies
- bullets
- collision or minimal hit detection
- score display
- pseudo-3D / Z-axis / depth perspective
- restart or game-over path, even if minimal

Acceptance criteria:

- The first item is runnable and visible.
- The first item contains user-visible evidence of the requested feature.
- Game requests include a minimal gameplay loop in item 1.

---

### Slice E: separate proposal progress and execution progress

Priority: High.

Goal:
Avoid confusing 11/11 proposal generation followed by 1/11 execution as a regression.

Expose and render separate fields:

- `plan_items_total`
- `patch_proposals_generated`
- `patch_proposals_total`
- `autopilot_current_item_index`
- `autopilot_completed_items`
- `autopilot_total_items`
- `current_phase`
- `repair_attempt`
- `max_repair_attempts`

Preferred UI example:

```text
Plan: 11 items
Patch proposals: 11/11 generated
Autopilot: verifying item 1/11
Completed: 0/11
Repair: attempt 1/3
```

Acceptance criteria:

- Proposal generation and execution counters are visually distinct.
- The UI no longer appears to rewind from 11/11 to 1/11.

---

### Slice F: PlanPool reuse and rerun controls

Priority: High.

Goal:
Allow users to reuse an existing PlanPool instead of recreating the plan every time.

UI labels:

- このPlanで再実行
- Planを再利用
- Plan参照をコピー

Avoid using `引用` as the main action label because it is ambiguous.

Required behavior:

- Add a control next to `PlanPool 作成: pool_xxx`.
- Rerun uses the existing plan and creates a new run id.
- Preserve original requirement, PlanItems, acceptance criteria, workspace id, and still-valid approvals/proposals.
- If the workspace or active context is invalid, show a clear reason and offer a new run from the plan.

Metadata:

- `parent_pool_id`
- `reused_from_pool_id`
- `rerun_count`
- `previous_run_ids`
- `latest_autopilot_run_id`

Acceptance criteria:

- The user can rerun from the same PlanPool.
- The plan is not regenerated.
- Rerun metadata links the new run to the original pool.

---

### Slice G: Large / Project mode for staged development

Priority: Medium to High.

Goal:
Support larger implementation work while keeping Atlas safety boundaries intact.

Modes:

- Small: one file or small localized patch
- Medium: multiple files, bounded scope
- Large: staged multi-item implementation
- Project: multi-phase project generation with checkpoints

Large / Project behavior:

- Split work into milestones.
- Each milestone contains PlanItems.
- Each PlanItem has acceptance criteria.
- Each patch records changed files and evidence.
- Verification runs after each item or milestone.
- Repair loops remain bounded.
- Risky or destructive operations still require explicit approval.

Acceptance criteria:

- Large mode can plan and execute multi-file work in stages.
- Project mode can manage milestones and checkpoints.
- Safety gates remain intact.
- Larger work is not blocked merely because it touches multiple files.

---

## Patch proposal metadata contract

Patch proposals should include trusted server-derived metadata:

```json
{
  "proposal_id": "prop_xxx",
  "covered_plan_item_ids": ["item_1"],
  "covered_requirements": ["visible runnable MVP", "pseudo-3D depth"],
  "changed_files": ["index.html"],
  "evidence": ["canvas exists", "player movement implemented"],
  "checks": ["syntax check", "static smoke check"],
  "pool_id": "pool_xxx",
  "workspace_id": "workspace_xxx",
  "active_envelope_id": "env_xxx",
  "generated_at": "...",
  "proposal_status": "generated"
}
```

Rules:

- Do not trust coverage metadata directly from LLM output.
- Derive or validate metadata server-side using PlanPool, PlanItem, normalized file changes, verification plan, and server-side evidence.

---

## Recommended search terms for Codex

```text
multi-item-autopilot
latest_autopilot_run_id
requirement_coverage_incomplete
AtlasPlanPoolStorage
atlas_claude_panel.js
approveAndRunPipeline
PlanPool 作成
next_action
can_execute
workflow_state
covered_plan_item_ids
```

---

## Focused checks

Run focused checks for the selected slice. Suggested checks:

```text
python -m pytest tests/test_atlas_multi_item_autopilot_api.py tests/test_atlas_auto_verification_service.py tests/test_atlas_pr9_requirement_mapping.py tests/test_atlas_runtime_status_panel_contract.py -q
node --check web/js/atlas_claude_panel.js
node --check web/js/atlas_pipeline_api.js
```

If a new regression test file is added, include it in the focused check list.

---

## Recommended implementation order

1. Slice A: item-level vs pool-level coverage separation.
2. Slice C: next-action buttons.
3. Slice B: bounded repair loop.
4. Slice E: progress semantics separation.
5. Slice F: PlanPool reuse/rerun.
6. Slice D: MVP-first planning.
7. Slice G: Large / Project mode.

Rationale:

- Slice A fixes the current hard failure.
- Slice C makes stopped states actionable.
- Slice B makes ordinary verification failures self-healing.
- Slice E fixes confusing progress display.
- Slice F improves iteration speed.
- Slice D improves future UI/game/HTML generation quality.
- Slice G scales Atlas to larger work while preserving safety.

---

## Overall definition of done

The initiative is done when:

- UI/game/HTML tasks start with a runnable MVP-oriented first item.
- Partial multi-item execution no longer fails because the full pool requirement is incomplete.
- Repairable verification failures enter bounded repair.
- Stopped states always show actionable buttons.
- Patch proposal progress and execution progress are displayed separately.
- PlanPool reuse is available from the Workbench UI.
- Large / Project mode can safely stage larger implementation work.
- Focused regression tests cover the new behavior.
- Existing Atlas safety gates remain intact.

---

## Example follow-up Codex prompts

Slice A only:

```text
Use docs/atlas_workbench_autopilot_goal_mode_plan.md.
Implement Slice A only.
Do not start the other slices.
Keep the PR focused and run the focused tests for Slice A.
```

Slice C only:

```text
Use docs/atlas_workbench_autopilot_goal_mode_plan.md.
Implement Slice C only: visible next-action buttons.
Keep backend PlanPool authoritative and render buttons only from backend-authorized can_* fields.
```

Slice D only:

```text
Use docs/atlas_workbench_autopilot_goal_mode_plan.md.
Implement Slice D only: MVP-first planning for UI / HTML / game / visual app tasks.
Add planner tests for the Space Invaders + Star Fox-style prompt.
```
