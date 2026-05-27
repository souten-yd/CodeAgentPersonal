# Atlas Practical Full Automation Experience Plan

## Purpose

This plan bridges the gap between:

- backend full-autonomy milestone completion (`PR-ATLAS-SCALE-160` and `final_goal_backend_milestone_reached = true`), and
- practical user-facing completion of Atlas as a usable autonomous development platform.

Backend milestone completion is necessary but not sufficient. Practical completion requires end-to-end usability through a conversational FastUI / ThinUX experience with visible safety gates, candidate isolation, verification, recovery, and draft-PR outcomes.

## 1) Current status

- Backend autonomous milestone has been reached.
- Backend workflow state is authoritative.
- Autonomous execution track is active in the post-SCALE-160 phase.
- Practical completion flags remain incomplete and must be completed through explicit post-SCALE-160 milestones.

## 2) What is already complete

- Canonical roadmap, policy, and manifest structure are established.
- Level progression through `PR-ATLAS-SCALE-160` is complete.
- Candidate workspace, recovery supervisor, and checkpoint foundations exist.
- Conversational shell contract/model foundations exist.
- UI default policy is guarded Atlas Next default with valid dist + fallback.
- Future FastUI default gate requirement exists.

## 3) What is still not complete

- Practical end-to-end developer experience is not yet complete.
- Stable runtime mutation apply must remain tightly gated and evidenced.
- Self-improvement practical loop must be usable while remaining candidate-first.
- Draft PR experience must be practical and user-visible in the normal flow.
- FastUI / ThinUX shell must be usable as a practical coding-agent interface.
- Direct merge gate is not part of the immediate practical completion path and remains a later, separately approved gate.

## 4) Practical completion criteria

Practical full automation is complete only when a user can:

1. Describe a development goal conversationally.
2. See Atlas produce a bounded plan.
3. See candidate workspace edits and changed-file summary.
4. See verification/check outcomes.
5. See recovery/fix loop behavior when checks fail.
6. Obtain draft PR preparation/update artifacts.
7. Track phase/progress/safety clearly in UI.

All of the above must occur with backend workflow state authoritative and safety gates enforceable.

## 5) UI / UX completion criteria

The practical FastUI / ThinUX shell must provide:

- conversation-first screen
- goal input
- current phase card
- next action card
- safety/profile badge
- work target selector (intent only; not authority)
- changed files summary
- verification/check summary
- recovery status
- one primary CTA
- settings drawer
- theme + accent-color continuity
- lightweight progress effects
- summary-first and lazy detail loading

The practical default shell direction must remain buildless:

- no required npm install
- no required Vite build
- no required Vue compilation

## 6) Stable runtime mutation completion criteria

Stable runtime mutation apply is complete only when all are true for each apply event:

- stable runtime mutation gate is ready
- candidate workspace is verified
- stable snapshot exists
- rollback evidence exists
- recovery evidence exists
- exact approval text or explicit backend-approved policy is present

And the following must remain false/unavailable unless separately approved later:

- direct merge
- remote push
- UI authority over backend workflow state

## 7) Self-improvement completion criteria

Self-improvement practical loop is complete only when:

- candidate workspace is mandatory
- stable runtime is not directly modified
- candidate verification is mandatory
- promotion gate is mandatory
- recovery plan exists before promotion
- failures preserve stable runtime integrity
- UI surfaces self-improvement scope, changed files, verification, and recovery state

## 8) End-to-end developer experience completion criteria

For normal development/repair tasks, Atlas must provide a bounded practical loop:

- goal → plan → candidate patch → verification gate → recovery/fix loop → draft PR artifact update

Required safety constraints:

- bounded iterations
- max iteration enforcement
- allowed action enforcement
- clear stop condition
- clear user-visible progress
- no arbitrary command execution
- no direct merge
- no remote push
- no stable runtime mutation unless separate stable-mutation gate is active

## 9) Post-SCALE-160 milestone sequence

1. `POST-SCALE-160-PRACTICAL-AUTOMATION-PLAN`
2. `POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY`
3. `POST-SCALE-160-FASTUI-SHELL-MVP`
4. `POST-SCALE-160-PRACTICAL-AUTONOMOUS-DEV-LOOP`
5. `POST-SCALE-160-SELF-IMPROVEMENT-PRACTICAL-LOOP`
6. `POST-SCALE-160-DRAFT-PR-EXPERIENCE`
7. `POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT`

## 10) Acceptance criteria for each milestone

### Milestone 1: POST-SCALE-160-PRACTICAL-AUTOMATION-PLAN

Purpose:

- Create this plan and wire it into manifest.
- No runtime behavior change.

Acceptance:

- New plan exists.
- Manifest points to it.
- Current active track remains safe.
- No stable mutation, self-apply, direct merge, remote push, or UI authority changes.

### Milestone 2: POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY

Purpose:

- Record stable-runtime-mutation apply readiness using existing gate evidence; this milestone may remain record-only.

Acceptance:

- Requires ready stable runtime mutation gate.
- Requires verified candidate workspace.
- Requires stable snapshot.
- Requires rollback evidence.
- Requires recovery evidence.
- Requires exact approval text or explicit backend-approved policy.
- If this milestone is record-only, `stable_runtime_mutation_apply_record_only = true` and runtime mutation remains not performed.
- Does not enable direct merge or remote push.
- Does not make UI authoritative.

### Milestone 3: POST-SCALE-160-FASTUI-SHELL-MVP

Purpose:

- Implement the first practical FastUI / ThinUX shell.

Acceptance:

- Conversation-first screen.
- Goal input.
- Current phase card.
- Next action card.
- Safety/profile badge.
- Work target selector.
- Changed files summary.
- Verification/check summary.
- Recovery status.
- One primary CTA.
- Settings drawer.
- Theme and accent-color continuity.
- Lightweight progress effects.
- No required npm install, Vite build, or Vue compile for the default FastUI shell.
- Browser uses summary-first and lazy detail loading.

### Milestone 4: POST-SCALE-160-PRACTICAL-AUTONOMOUS-DEV-LOOP

Purpose:

- Make the autonomous loop useful for real development tasks.

Acceptance:

- Goal → plan → candidate patch → verification gate → recovery/fix loop → draft PR/update artifact.
- Bounded loop only.
- Max iterations enforced.
- Allowed actions enforced.
- Clear stop condition.
- Clear user-visible progress.
- No arbitrary command execution.
- No direct merge.
- No remote push.
- No stable runtime mutation unless the separate stable mutation gate is active.

### Milestone 5: POST-SCALE-160-SELF-IMPROVEMENT-PRACTICAL-LOOP

Purpose:

- Make self-improvement usable without mutating stable runtime directly.

Acceptance:

- Candidate workspace required.
- Stable repo must not be modified directly.
- Candidate verification required.
- Promotion gate required.
- Recovery plan required before promotion.
- Failure leaves stable runtime intact.
- UI shows self-improvement scope, changed files, verification, and recovery state.

### Milestone 6: POST-SCALE-160-DRAFT-PR-EXPERIENCE

Purpose:

- Make draft PR preparation/update usable as part of the agent flow.

Acceptance:

- Draft PR summary artifact.
- Changed files summary.
- Verification summary.
- Risk summary.
- Recovery summary.
- User-visible "ready for review" state.
- No direct merge.
- No remote push unless a future explicit policy allows it.

### Milestone 7: POST-SCALE-160-PRACTICAL-FULL-AUTOMATION-CHECKPOINT

Purpose:

- Mark practical full automation complete.

Acceptance:

- Backend autonomous milestone remains true.
- FastUI shell is usable.
- User can run a bounded development task end-to-end through UI.
- Candidate workspace flow works.
- Verification/recovery gates are visible.
- Self-improvement remains candidate-first.
- Stable runtime mutation has gate evidence.
- Direct merge remains forbidden.
- Remote push remains disabled unless later explicitly planned.
- UI is not source of truth.
- Backend workflow state remains authoritative.

## 11) Anti-drift rules

- Do not treat backend milestone completion as practical completion.
- Do not flip practical completion flags to true before milestone acceptance evidence exists.
- Do not let UI become workflow authority.
- Do not enable direct merge by implication.
- Do not enable remote push by implication.
- Do not bypass candidate workspace for self-improvement.
- Do not allow stable runtime mutation without snapshot, rollback, and recovery evidence.
- Do not require npm/Vite/Vue build chain for default practical FastUI shell.
- Do not change default route or UI authority as part of planning-only milestones.
- Manifest and policy remain authoritative over stale roadmap pointers when conflicts exist.
