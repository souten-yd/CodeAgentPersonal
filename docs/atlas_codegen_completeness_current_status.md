# Atlas Code Generation Completeness Current Status

> Mutable checkpoint for Codex goal mode.  
> Update this file after every work package.  
> Do not use older status or planning documents.

## Goal status

- Overall: Active
- Canonical goal: `docs/atlas_codegen_completeness_goal.md`
- Canonical plan: `docs/atlas_codegen_completeness_implementation_plan.md`
- Baseline commit: `3ac07375610d6de826199be07366f451adfbec63` (PR #1599)
- Current work package: WP-8
- Next action: Run E2E acceptance and final audit for the code generation completeness goal.

## Observed current-main capabilities

The baseline already contains meaningful progress and must not be reimplemented blindly:

- plan generation schema requires implementation steps, test plan and rollback plan
- PlanItem target files and acceptance/done definitions have partial propagation
- patch generation reads existing single-target content
- project symbols and related tests are partially supplied to patch generation
- proposal generation retries invalid or empty output
- proposal self-review exists
- HTML/JS/TS stub patterns are partially detected
- visual contracts and browser smoke verification exist
- bounded retry and self-correction exist
- requirement tracing and final quality rollup exist
- safe apply supports multi-file changes and rollback
- clarification and critical-event safety gates exist
- recent fixes cover invalid dependencies, item budget counting and partial-write rollback

These capabilities are building blocks, not proof that the completeness goal is achieved.

## Known gaps to verify in WP-0

- autonomous flow still generates multiple missing proposals before apply
- patch input may omit root goal, original request, all requirements and completed item context
- multi-target current content may not be fully grounded
- final self-review failure may still return applicable content
- stub detection remains ratio/pattern limited
- final rollup may allow partial or implemented requirements to remain success-compatible
- verification skipped/unavailable may still be too permissive
- planner/requirement skeleton fallbacks may remain reachable
- legacy executor TODO stub and append fallback may remain
- unknown action may still normalize to create
- reviewer exception may still fail open
- oversized proposed content may be truncated
- explicit base revision preconditions are absent or incomplete

WP-0 must convert these observations into current-code tests before broad production edits.

## Work package table

| WP | Title | Status | PR/Commit | Test evidence |
|---|---|---|---|---|
| WP-0 | Baseline and regression fixtures | Completed | local WP-0 commit | `python -m pytest -q tests/test_atlas_codegen_completeness_baseline.py`; affected slice 88 passed |
| WP-1 | Preserve complete planning contract | Completed | local WP-1 commit | focused slice 45 passed; affected slice 54 passed |
| WP-2 | Task-complete generation contracts | Completed | local WP-2 commit | focused 11 passed; service affected 56 passed |
| WP-3 | Interleaved orchestration | Completed | local WP-3 commit | focused 43 passed; service affected 75 passed; path resolution 2 passed |
| WP-4 | Fail-closed generation quality | Completed | local WP-4 commit | focused 44 passed; affected 106 passed |
| WP-5 | Remove skeleton/fail-open fallbacks | Completed | local WP-5 commit | focused 50 passed; affected 166 passed |
| WP-6 | Requirement-complete final status | Completed | local WP-6 commit | focused 42 passed; affected 211 passed |
| WP-7 | Task-aware verification contracts | Completed | local WP-7 commit | focused 6 passed; affected 217 passed |
| WP-8 | E2E acceptance and final audit | Not started | - | - |

## Last completed work package

WP-7 - Task-aware verification contracts.

## Current blockers

None recorded.

## Latest completed work package evidence

Completed work package:
WP-7 - Task-aware verification contracts.

PR/commit:
Local WP-7 commit to be created after this status update. No PR, merge, or remote push.

Changed files:
- `agent/atlas_auto_verification_service.py`
- `agent/atlas_task_verification_contracts.py`
- `tests/test_atlas_task_verification_contracts.py`
- `docs/atlas_codegen_completeness_current_status.md`

Behavior implemented:
- Added a task verification contract registry for Python module/service, API endpoint, browser/HTML/UI, canvas/game, persistence/state reload, multi-file integration, and unknown task fallback.
- PlanItems now persist the selected task verification contract and expected signals on item metadata and pool rollup metadata during auto verification.
- Command verification now evaluates expected response/runtime signals against command output and changed-file contents, failing with actionable repair instructions when signals are missing.
- Visual-only verification now stores task contract evidence alongside the existing static visual contract and browser smoke evidence.
- Contract inference is item-scoped so pool-level goals do not misclassify unrelated items, while multi-file integration tasks select the integration contract before API/Python fallbacks.
- Selected contracts are durably stored before blocked or skipped verification returns, without converting unavailable verification into completion.

Tests passed:
- `python -m pytest -q tests/test_atlas_task_verification_contracts.py` -> 6 passed.
- `python -m pytest -q tests/test_atlas_task_verification_contracts.py tests/test_atlas_auto_verification_service.py tests/test_atlas_pr9_visual_depth.py tests/test_visual_contract_matrix.py` -> 74 passed.
- `python -m pytest -q tests/test_atlas_codegen_completeness_baseline.py tests/test_atlas_multi_item_autopilot_service.py tests/test_atlas_pr9_integration_graph.py` -> 29 passed.
- `python -m pytest -q tests/test_atlas_task_verification_contracts.py tests/test_atlas_codegen_completeness_baseline.py tests/test_atlas_auto_verification_service.py tests/test_atlas_llm_evaluator_service.py tests/test_atlas_pr8_visual_verification_wiring.py tests/test_atlas_pr9_visual_depth.py tests/test_atlas_pr9_integration_graph.py tests/test_atlas_visual_artifact_verifier.py tests/test_visual_contract_matrix.py tests/test_atlas_multi_item_autopilot_service.py tests/test_atlas_patch_proposal_codegen_contract.py tests/test_atlas_file_safe_apply_executor.py tests/test_atlas_autonomous_codegen_orchestrator_service.py tests/test_atlas_plan_pool_schema.py tests/test_atlas_plan_pool_builder.py` -> 217 passed.

Syntax checks:
- `python -m py_compile agent/atlas_task_verification_contracts.py agent/atlas_auto_verification_service.py tests/test_atlas_task_verification_contracts.py` -> passed.
- `git diff --check` -> passed.

Safety invariants:
- Production changes are limited to task verification contract selection, expected-signal evaluation, and evidence persistence in the existing auto verification surface.
- Safe apply, approval, path, rollback, PlanPool authority, and bounded allowlisted verification command surfaces remain unchanged.
- No direct merge, remote push, self-apply, stable runtime mutation, Vue authority, arbitrary unbounded command execution, or fabricated verification results introduced.
- Backend PlanPool remains authoritative for item state and persisted verification evidence.

Remaining gaps:
- WP-8 must complete E2E acceptance and final audit.

Next work package:
WP-8 - E2E acceptance and final audit.

## Token-saving resume note

On resume:

1. Read `AGENTS.md`.
2. Read the canonical goal.
3. Read this status.
4. Read only WP-8 in the canonical plan.
5. Inspect only files listed by WP-8 and related tests.
6. Do not rescan old plans or roadmaps.

## Update template

After each work package, replace the relevant fields and add:

```text
Completed work package:
PR/commit:
Changed files:
Behavior implemented:
Tests passed:
Syntax checks:
Safety invariants:
Remaining gaps:
Next work package:
```
