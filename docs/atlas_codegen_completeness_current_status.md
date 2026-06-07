# Atlas Code Generation Completeness Current Status

> Mutable checkpoint for Codex goal mode.  
> Update this file after every work package.  
> Do not use older status or planning documents.

## Goal status

- Overall: Active
- Canonical goal: `docs/atlas_codegen_completeness_goal.md`
- Canonical plan: `docs/atlas_codegen_completeness_implementation_plan.md`
- Baseline commit: `3ac07375610d6de826199be07366f451adfbec63` (PR #1599)
- Current work package: WP-2
- Next action: Build task-complete generation contracts for AtlasPatchProposalService.

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
| WP-2 | Task-complete generation contracts | In progress | - | - |
| WP-3 | Interleaved orchestration | Not started | - | - |
| WP-4 | Fail-closed generation quality | Not started | - | - |
| WP-5 | Remove skeleton/fail-open fallbacks | Not started | - | - |
| WP-6 | Requirement-complete final status | Not started | - | - |
| WP-7 | Task-aware verification contracts | Not started | - | - |
| WP-8 | E2E acceptance and final audit | Not started | - | - |

## Last completed work package

WP-1 - Preserve complete planning contract.

## Current blockers

None recorded.

## Latest completed work package evidence

Completed work package:
WP-1 - Preserve complete planning contract.

PR/commit:
Local WP-1 commit created after this status update. No PR, merge, or remote push.

Changed files:
- `agent/requirement_schema.py`
- `agent/requirement_analyzer.py`
- `agent/plan_schema.py`
- `agent/planner_phase1.py`
- `agent/atlas_planner_bridge.py`
- `agent/atlas_plan_pool_schema.py`
- `agent/atlas_plan_pool_builder.py`
- `agent/atlas_llm_schemas.py`
- `agent/atlas_llm_output_models.py`
- `agent/atlas_plan_depth_gate.py`
- `tests/test_atlas_planner_bridge.py`
- `tests/test_atlas_plan_pool_builder.py`
- `tests/test_atlas_plan_pool_schema.py`
- `tests/test_atlas_plan_depth_gate.py`
- `tests/test_requirement_analyzer_score_normalization.py`
- `docs/atlas_codegen_completeness_current_status.md`

Behavior implemented:
- Added backward-compatible stable contract fields for original request, selected architecture, requirements, acceptance criteria, verification contract, expected changes, preserve behaviors, and requirement IDs.
- Preserved those fields through requirement analysis, phase-1 planning, structured-output models, planner bridge conversion, PlanPool/PlanItem schema, and PlanPool builder.
- Added requirement-to-item mapping and plan quality metadata for unmapped mandatory requirements.
- Added full-autopilot plan-depth checks for missing acceptance criteria, verification contract, and requirement mapping.
- Changed failed requirement analysis to remain non-ready and not fabricate generic implementation-ready functional requirements or done definitions.

Tests passed:
- `python -m pytest -q tests/test_atlas_planner_bridge.py tests/test_atlas_plan_pool_builder.py tests/test_atlas_plan_pool_schema.py tests/test_atlas_plan_depth_gate.py tests/test_requirement_analyzer_score_normalization.py` -> 45 passed.
- `python -m pytest -q tests/test_atlas_planner_bridge.py tests/test_atlas_plan_pool_builder.py tests/test_atlas_plan_pool_schema.py tests/test_atlas_plan_depth_gate.py tests/test_requirement_analyzer_score_normalization.py tests/test_atlas_planner_fallback_skeleton.py tests/test_atlas_codegen_completeness_baseline.py` -> 54 passed.

Syntax checks:
- `python -m py_compile agent/requirement_schema.py agent/requirement_analyzer.py agent/plan_schema.py agent/planner_phase1.py agent/atlas_planner_bridge.py agent/atlas_plan_pool_schema.py agent/atlas_plan_pool_builder.py agent/atlas_llm_schemas.py agent/atlas_llm_output_models.py agent/atlas_plan_depth_gate.py tests/test_atlas_planner_bridge.py tests/test_atlas_plan_pool_builder.py tests/test_atlas_plan_pool_schema.py tests/test_atlas_plan_depth_gate.py tests/test_requirement_analyzer_score_normalization.py` -> passed.

Safety invariants:
- Production changes are limited to planning/contract preservation and pre-apply plan quality checks.
- No direct merge, remote push, self-apply, stable runtime mutation, Vue authority, arbitrary unbounded command execution, or fabricated verification results introduced.
- Existing backend workflow_state and PlanPool authority boundaries unchanged.

Remaining gaps:
- WP-2 must feed the preserved planning contract plus current target contents and base revisions into patch proposal generation and validate task-complete proposal evidence.
- Later WPs must replace batch autonomous generation, add revision preconditions, fail-close unresolved self-review, remove fallback skeleton/fail-open paths, enforce requirement-complete final status, and add task-aware verification/E2E acceptance.

Next work package:
WP-2 - Task-complete generation contracts.

## Token-saving resume note

On resume:

1. Read `AGENTS.md`.
2. Read the canonical goal.
3. Read this status.
4. Read only WP-2 in the canonical plan.
5. Inspect only files listed by WP-2 and related tests.
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
