# Atlas Code Generation Completeness Current Status

> Mutable checkpoint for Codex goal mode.  
> Update this file after every work package.  
> Do not use older status or planning documents.

## Goal status

- Overall: Active
- Canonical goal: `docs/atlas_codegen_completeness_goal.md`
- Canonical plan: `docs/atlas_codegen_completeness_implementation_plan.md`
- Baseline commit: `3ac07375610d6de826199be07366f451adfbec63` (PR #1599)
- Current work package: WP-3
- Next action: Interleave generation, apply, verification, and refresh with revision preconditions.

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
| WP-3 | Interleaved orchestration | In progress | - | - |
| WP-4 | Fail-closed generation quality | Not started | - | - |
| WP-5 | Remove skeleton/fail-open fallbacks | Not started | - | - |
| WP-6 | Requirement-complete final status | Not started | - | - |
| WP-7 | Task-aware verification contracts | Not started | - | - |
| WP-8 | E2E acceptance and final audit | Not started | - | - |

## Last completed work package

WP-2 - Task-complete generation contracts.

## Current blockers

None recorded.

## Latest completed work package evidence

Completed work package:
WP-2 - Task-complete generation contracts.

PR/commit:
Local WP-2 commit created after this status update. No PR, merge, or remote push.

Changed files:
- `agent/atlas_patch_proposal_service.py`
- `agent/atlas_llm_schemas.py`
- `tests/test_atlas_patch_proposal_codegen_contract.py`
- `tests/test_atlas_codegen_completeness_baseline.py`
- `docs/atlas_codegen_completeness_current_status.md`

Behavior implemented:
- Extended patch proposal input with root goal, original request, selected architecture, constraints, all/current/satisfied/remaining requirements, completed item summaries, preserve behaviors, current contents for every target file, and base file revisions.
- Multi-file PlanItems now ground every target file instead of only a single target.
- Added semantic proposal evidence fields to the shallow LLM schema.
- Added post-parse semantic validation for authorized target files, authorized requirement IDs, content-bearing multi-file output, required evidence, remaining TODOs, and known limitations.
- Added retry feedback for semantic validation failures and returns non-applicable/no-content proposals when validation remains failed.
- Updated WP-0 characterization for the proposal-input gap now fixed by WP-2.

Tests passed:
- `python -m pytest -q tests/test_atlas_patch_proposal_codegen_contract.py tests/test_atlas_codegen_completeness_baseline.py` -> 11 passed.
- `python -m pytest -q tests/test_atlas_patch_proposal_codegen_contract.py tests/test_atlas_codegen_completeness_baseline.py tests/test_atlas_patch_proposal_feedback.py tests/test_atlas_plan_pool_schema.py tests/test_atlas_plan_pool_builder.py tests/test_atlas_planner_bridge.py` -> 56 passed.

Syntax checks:
- `python -m py_compile agent/atlas_patch_proposal_service.py agent/atlas_patch_proposal_schema.py agent/atlas_llm_schemas.py agent/atlas_code_explorer.py agent/atlas_plan_pool_schema.py tests/test_atlas_patch_proposal_codegen_contract.py tests/test_atlas_codegen_completeness_baseline.py` -> passed.

Safety invariants:
- Production changes are limited to proposal-generation context and pre-apply semantic applicability checks.
- No direct merge, remote push, self-apply, stable runtime mutation, Vue authority, arbitrary unbounded command execution, or fabricated verification results introduced.
- Existing backend workflow_state and PlanPool authority boundaries unchanged.

Remaining gaps:
- WP-3 must replace autonomous batch generation with per-item generate/review/apply/verify/refresh and enforce base revision preconditions at apply time.
- Later WPs must fail-close unresolved self-review, remove fallback skeleton/fail-open paths, enforce requirement-complete final status, and add task-aware verification/E2E acceptance.
- Wider API patch-proposal tests `tests/test_atlas_patch_proposal_planitem_verification_flow.py tests/test_atlas_patch_proposal_to_safe_apply_e2e.py` were not used as WP-2 evidence because their seed helper currently expects `/api/atlas/plan-pools` to return `plan_pool`, while current main returns `{"status":"queued"}` before proposal code runs.

Next work package:
WP-3 - Interleaved orchestration.

## Token-saving resume note

On resume:

1. Read `AGENTS.md`.
2. Read the canonical goal.
3. Read this status.
4. Read only WP-3 in the canonical plan.
5. Inspect only files listed by WP-3 and related tests.
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
