# Atlas Code Generation Completeness Implementation Plan

> Canonical execution plan for `docs/atlas_codegen_completeness_goal.md`.  
> Do not consult older plans.  
> Execute one work package at a time and update `docs/atlas_codegen_completeness_current_status.md` after each package.

## Common rules

- Start from latest `main`.
- Keep each work package independently testable.
- Reuse existing services and tests.
- Preserve all safety invariants in the goal document.
- Do not combine unrelated UI work.
- Do not introduce direct merge, remote push, self-apply, stable runtime mutation, or unbounded commands.
- Never mark a work package complete without test evidence.
- When current code already implements part of a requirement, verify it and patch only the remaining gap.

---

# WP-0: Baseline and regression fixtures

## Goal

現在の挙動を固定し、今後の修正が骨格生成問題を再発させないテスト基盤を作る。

## Inspect

- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `agent/atlas_multi_item_autopilot_service.py`
- `agent/atlas_patch_proposal_service.py`
- `agent/atlas_plan_pool_builder.py`
- `agent/atlas_planner_bridge.py`
- `agent/atlas_run_quality_rollup.py`
- `agent/atlas_auto_verification_service.py`
- existing related tests only

## Required changes

1. Add fixtures/helpers for:
   - two or more PlanItems updating the same file
   - PlanItem with complete requirement contract
   - PlanItem with partial/stub content
   - verification unavailable
2. Add failing/characterization tests showing:
   - batch proposals can be based on stale content
   - final self-review failure remains applicable, if still true
   - partial requirement coverage can still reach success, if still true
   - skeleton fallback can enter an implementation path, if still true
3. Do not change production behavior except minimal test seams.

## Acceptance

- Tests clearly identify each still-active root cause.
- Already-fixed issues are documented in current status and do not get redundant production changes.
- Focused tests run.

## Likely tests

- new `tests/test_atlas_codegen_completeness_baseline.py`
- existing orchestrator, patch proposal, rollup tests

---

# WP-1: Preserve the complete planning contract

## Goal

Requirement analysisからPlanItemまで、コード生成に必要な情報を欠落させない。

## Inspect

- `agent/requirement_schema.py`
- `agent/requirement_analyzer.py`
- `agent/plan_schema.py`
- `agent/planner_phase1.py`
- `agent/atlas_planner_bridge.py`
- `agent/atlas_plan_pool_schema.py`
- `agent/atlas_plan_pool_builder.py`
- `agent/atlas_llm_schemas.py`
- related tests

## Required changes

1. Define stable fields for:
   - requirement IDs and descriptions
   - acceptance criteria
   - verification contract
   - expected changes
   - preserve behaviors
   - selected architecture
   - original user request
2. Ensure `AtlasPlannerBridge.planner_result_to_plan_payload()` preserves:
   - step acceptance criteria
   - step verification
   - step expected changes
   - requirement linkage
   - plan/global constraints
3. Ensure PlanPool/PlanItem persist these fields without hiding critical data only in compact summaries.
4. Add a plan-to-item requirement trace:
   - each required requirement maps to at least one implementation or verification item
   - unmapped requirement makes plan quality fail
5. Keep new fields backward compatible with defaults.
6. Do not fabricate implementation-ready defaults when requirement analysis failed.

## Acceptance

- Planner output round-trips through PlanPool without losing the fields above.
- Each required requirement has mapped PlanItem IDs.
- Missing acceptance/verification/requirement mapping blocks full-autopilot plan quality.
- Existing stored PlanPools remain loadable.

## Tests

- planner bridge propagation
- PlanPool serialization/backward compatibility
- requirement-to-item mapping
- plan depth/quality gate

---

# WP-2: Build task-complete generation contracts

## Goal

`AtlasPatchProposalService`へ局所stepだけでなく、全体ゴールと現在の実装状態を渡す。

## Inspect

- `agent/atlas_patch_proposal_service.py`
- `agent/atlas_patch_proposal_schema.py`
- `agent/atlas_llm_schemas.py`
- `agent/atlas_code_explorer.py`
- PlanPool/PlanItem schemas
- related tests

## Required changes

1. Extend proposal input with:
   - root goal
   - original request
   - selected architecture
   - constraints
   - all requirements
   - requirements for current item
   - satisfied and remaining requirements
   - completed item summaries
   - current target contents for all target files
   - base revisions
   - preserve behaviors
2. For multi-file items, read every target file, not only a single target.
3. Replace one generic permissive proposal contract with task-aware validation:
   - new file
   - existing file localized edits
   - multi-file unit
   - test artifact
   - visual/browser artifact
4. Require semantic evidence fields:
   - satisfied requirement IDs
   - implemented symbols
   - behavioral cases
   - verification cases
   - remaining todos
   - known limitations
5. Keep structured decoding compatible with weaker local models:
   - shallow JSON where necessary
   - strict semantic validation after parsing
   - precise retry feedback
6. Reject target files or requirement IDs not authorized by the PlanItem contract.

## Acceptance

- Generator sees current full task context.
- Multi-file generation carries one content-bearing entry per target file.
- Empty evidence, unknown requirement IDs, remaining todos, or unresolved limitations are not applicable.
- Existing-file edits preserve unrelated code.

## Tests

- proposal input contract
- multi-file context
- semantic response validation
- weak-model retry behavior
- unauthorized path/requirement rejection

---

# WP-3: Interleave generation, apply, verification, and refresh

## Goal

generate-all-then-applyを廃止し、PlanItem単位で最新状態に基づいて実行する。

## Inspect

- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `agent/atlas_multi_item_autopilot_service.py`
- `agent/atlas_context_refresh_service.py`
- `agent/atlas_auto_safe_apply_service.py`
- `agent/atlas_file_safe_apply_executor.py`
- progress/result schemas
- related tests

## Required changes

1. Introduce one authoritative item loop:
   - dependency-ready selection
   - latest pool reload
   - context refresh
   - proposal generation if needed
   - proposal hard review
   - safe apply
   - verification
   - bounded repair
   - evidence persistence
   - next item
2. Remove or bypass Phase 2 batch pre-generation for autonomous full codegen.
3. Preserve manual proposal-only flows where explicitly requested, but do not use stale batch proposals for autonomous apply.
4. Add base revision preconditions:
   - SHA/content revision per file
   - absent marker for creates
   - mismatch triggers regeneration, not apply
5. When two items target the same file:
   - item N+1 reads item N's applied content
   - completed item evidence is included
6. Keep progress reporting truthful:
   - current item
   - generation/review/apply/verify/repair phase
   - regeneration due to revision mismatch
7. Preserve stop requests, max items, max runtime, max changed files, risk and gate boundaries.

## Acceptance

- Same-file sequential test proves no stale overwrite.
- Existing proposal with stale base revision is rejected/regenerated.
- No item is marked completed before its verification result is persisted.
- Stop/budget/safety behavior remains bounded.

## Tests

- orchestrator same-file sequence
- dependency order
- revision mismatch
- stop/budget behavior
- partial failure and resume

---

# WP-4: Make generation quality gates fail-closed

## Goal

不完全proposalを警告付きで適用可能にする経路を除去する。

## Inspect

- `agent/atlas_patch_proposal_service.py`
- `agent/atlas_placeholder_detector.py`
- `agent/atlas_file_safe_apply_executor.py`
- `agent/atlas_plan_item_file_changes.py`
- related tests

## Required changes

1. If final self-review fails:
   - return failed/no-content result
   - clear all applicable content fields
   - persist unresolved findings
   - block safe apply
2. Expand semantic checks:
   - empty or trivial function bodies
   - critical method returning constant only
   - TODO/FIXME/placeholder variants
   - disconnected imports/exports/scripts/styles
   - incomplete multi-file response
   - requirement evidence mismatch
3. Apply structural checks by task type, not placeholder ratio alone.
4. Enforce quality block for autonomous profiles regardless of legacy default.
5. Do not truncate `proposed_content`.
   - content too large -> fail and request split/replan
6. Do not treat warnings such as `self_review_findings_unresolved` as success-compatible.
7. Ensure safe apply independently rejects a proposal whose review contract is not passed.

## Acceptance

- One critical empty method is sufficient to block, even when stub ratio is low.
- Final failed proposal cannot reach safe apply.
- Oversized content is never written partially.
- Valid small files do not get false-positive blocked.

## Tests

- Python/JS/HTML structural stub cases
- final-attempt rejection
- oversized content
- safe-apply review precondition
- multi-file incomplete response

---

# WP-5: Remove skeleton and fail-open fallback paths

## Goal

失敗を骨格コード作成へ変換するすべての実行経路を除去する。

## Inspect

- `agent/planner_phase1.py`
- `agent/requirement_analyzer.py`
- `agent/atlas_plan_pool_builder.py`
- `agent/implementation_executor.py`
- `agent/atlas_action_type.py`
- `agent/plan_reviewer.py`
- direct callers and related tests

## Required changes

1. Planner failure:
   - no implementation-ready skeleton plan
   - status is needs_replan/failed/blocked
   - no patch generation allowed
2. Requirement analysis failure:
   - do not create generic implementation-ready functional requirements
   - persist analysis failure evidence
3. Legacy executor:
   - delete/disable `_create_stub()` success path
   - create uses real full-content generation or fails
   - remove append fallback after LLM failure
4. Action normalization:
   - unknown action type is validation failure
   - only explicit compatible legacy values may map
5. Plan review exception:
   - fail-closed
   - approved_for_execution false
   - retry/review-required evidence
6. Ensure all API/orchestrator callers honor these statuses.

## Acceptance

- No TODO stub file is generated by any reachable execution path.
- Planner/reviewer failure cannot become approved execution.
- Unknown action never silently becomes create.
- Existing explicit create/update behavior remains compatible.

## Tests

- planner failure
- requirement failure
- legacy executor create failure
- unknown action
- reviewer exception
- API/orchestrator blocking

---

# WP-6: Requirement-complete verification and final status

## Goal

最終statusを実装量ではなくrequirement evidenceで決定する。

## Inspect

- `agent/atlas_requirement_tracer.py`
- `agent/atlas_run_quality_rollup.py`
- `agent/atlas_auto_verification_service.py`
- `agent/atlas_llm_evaluator_service.py`
- visual/browser/integration verifiers
- related tests

## Required changes

1. Define requirement states:
   - planned
   - implemented
   - verified
   - partial
   - missing
   - unverified
2. Define final success:
   - all mandatory requirements verified
   - narrowly defined static-only requirement may use explicit `verified_static`
   - no partial/missing/planned/unverified
3. Map evidence by explicit requirement IDs first.
   - keyword heuristics are fallback/advisory only
4. Persist per-requirement:
   - planned files/items
   - changed files
   - implemented symbols/signals
   - verification method
   - result/evidence path
5. Verification unavailable:
   - never completed
   - applied_unverified or blocked
6. `verification_skipped` is not completed for implementation items.
7. Integration/placeholder failure always degrades completed.
8. Autonomous profiles default to enforced requirement and quality gates.

## Acceptance

- One intentionally omitted requirement prevents completed.
- Verification unavailable prevents completed.
- Passing test with missing runtime behavior does not verify that requirement.
- Visual/browser evidence can satisfy a visual requirement without false failure.
- Explicit evidence mapping is stable for Japanese requirements.

## Tests

- per-requirement explicit mapping
- missing/partial/unverified status
- skipped verification
- visual evidence
- Japanese requirement IDs/signals
- final rollup

---

# WP-7: Task-aware verification contracts

## Goal

タスクごとに「何が動けば完成か」を検証できるようにする。

## Inspect

Only verifier modules needed for the selected contracts and their direct tests.

## Required changes

1. Define verification contract registry or equivalent for:
   - Python module/service
   - API endpoint
   - browser/HTML/UI
   - canvas/game
   - persistence/state reload
   - multi-file integration
2. Each PlanItem carries selected contract and expected signals.
3. Verification runs the narrowest reliable checks:
   - syntax/import
   - focused unit/integration
   - browser smoke
   - DOM/state interaction
   - console error check
   - static integration graph
4. Failed signals feed actionable repair instructions.
5. Test-only repair is rejected when implementation is defective.
6. Store evidence in item and pool rollup.

## Acceptance

- Generated browser game verifies core behaviors, not only file existence.
- API verifies actual response behavior.
- Persistence task verifies reload.
- Repair loop targets implementation artifact.

## Tests

- one test suite per contract type
- failure-to-repair routing
- evidence persistence

---

# WP-8: End-to-end acceptance and migration audit

## Goal

全変更を統合し、旧経路を含めて骨格生成を再発させない。

## Required tests

1. Same-file sequential implementation.
2. Complete browser game.
3. Existing repository feature update.
4. Final self-review rejection.
5. Missing requirement prevents success.
6. Verification unavailable prevents success.
7. Legacy path cannot create TODO stub.
8. Multi-file integration.
9. Resume after bounded failure without stale proposal.
10. Safety invariants.

## Audit

Search reachable production code for:

- `_create_stub`
- `planner_fallback_skeleton_generated`
- TODO-generating fallback
- append fallback
- unknown-to-create normalization
- self-review unresolved but applicable
- verification skipped -> completed
- partial requirement -> success eligible
- content truncation before apply
- batch proposal generation used by autonomous apply

Every remaining occurrence must be:

- unreachable in production, or
- explicitly non-applicable/manual advisory, or
- covered by a blocking test.

## Final acceptance

- All global acceptance scenarios pass.
- Focused and affected suites pass.
- Syntax checks pass.
- Current status is `Completed`.
- Remaining work is optional improvement only.
- Safety invariants are unchanged or stronger.

---

# Recommended PR sequence

- PR-CGQ-0: baseline regression fixtures
- PR-CGQ-1: complete planning contract
- PR-CGQ-2: task-complete generation contract
- PR-CGQ-3: interleaved item orchestration and revision preconditions
- PR-CGQ-4: fail-closed generation quality
- PR-CGQ-5: remove skeleton/fail-open fallbacks
- PR-CGQ-6: requirement-complete rollup
- PR-CGQ-7: task-aware verification
- PR-CGQ-8: E2E acceptance and final audit

Do not mix multiple PR-CGQ work packages into one broad change.
