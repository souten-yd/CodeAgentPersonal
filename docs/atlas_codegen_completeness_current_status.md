# Atlas Code Generation Completeness Current Status

> Mutable checkpoint for Codex goal mode.  
> Update this file after every work package.  
> Do not use older status or planning documents.

## Goal status

- Overall: Active
- Canonical goal: `docs/atlas_codegen_completeness_goal.md`
- Canonical plan: `docs/atlas_codegen_completeness_implementation_plan.md`
- Baseline commit: `3ac07375610d6de826199be07366f451adfbec63` (PR #1599)
- Current work package: WP-1
- Next action: Preserve the complete planning contract from requirement analysis through PlanPool/PlanItem.

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
| WP-1 | Preserve complete planning contract | In progress | - | - |
| WP-2 | Task-complete generation contracts | Not started | - | - |
| WP-3 | Interleaved orchestration | Not started | - | - |
| WP-4 | Fail-closed generation quality | Not started | - | - |
| WP-5 | Remove skeleton/fail-open fallbacks | Not started | - | - |
| WP-6 | Requirement-complete final status | Not started | - | - |
| WP-7 | Task-aware verification contracts | Not started | - | - |
| WP-8 | E2E acceptance and final audit | Not started | - | - |

## Last completed work package

WP-0 - Baseline and regression fixtures.

## Current blockers

None recorded.

## Latest completed work package evidence

Completed work package:
WP-0 - Baseline and regression fixtures.

PR/commit:
Local WP-0 commit created after this status update. No PR, merge, or remote push.

Changed files:
- `tests/test_atlas_codegen_completeness_baseline.py`
- `docs/atlas_codegen_completeness_current_status.md`

Behavior implemented:
- Added WP-0 fixture helpers for same-file multi-item updates, complete requirement contracts, partial/stub content, and verification-unavailable items.
- Added characterization coverage confirming current autonomous orchestration generates missing proposals before apply, so same-file later proposals can observe stale pre-apply content.
- Added characterization coverage confirming proposal input is still item-local and does not carry root goal, original request, all requirements, or completed item summaries.
- Added characterization coverage confirming multi-file proposal input does not ground all target file contents.
- Added characterization coverage confirming final self-review failure can still return applicable content with unresolved findings.
- Added characterization coverage confirming partial requirement coverage remains success-compatible in final rollup.
- Added characterization coverage confirming generic verification skipped can still complete a multi-item result.
- Recorded already-fixed behavior: `AtlasRequirementTracer.coverage_summary()` already rejects partial requirements as not success-eligible.

Tests passed:
- `python -m pytest -q tests/test_atlas_codegen_completeness_baseline.py` -> 7 passed.
- `python -m pytest -q tests/test_atlas_codegen_completeness_baseline.py tests/test_atlas_autonomous_codegen_orchestrator_service.py tests/test_atlas_multi_item_autopilot_service.py tests/test_atlas_plan_pool_builder.py tests/test_atlas_planner_bridge.py tests/test_atlas_auto_verification_service.py tests/test_atlas_planner_fallback_skeleton.py tests/test_atlas_placeholder_preapply.py` -> 88 passed.

Syntax checks:
- `python -m py_compile tests/test_atlas_codegen_completeness_baseline.py` -> passed.

Safety invariants:
- No production behavior changed in WP-0.
- No direct merge, remote push, self-apply, stable runtime mutation, Vue authority, arbitrary unbounded command execution, or fabricated verification results introduced.
- Existing backend workflow_state and PlanPool authority boundaries unchanged.

Remaining gaps:
- WP-1 must preserve complete planning contract fields through planner bridge and PlanPool/PlanItem.
- Later WPs must replace batch autonomous generation, add revision preconditions, fail-close unresolved self-review, remove fallback skeleton/fail-open paths, enforce requirement-complete final status, and add task-aware verification/E2E acceptance.

Next work package:
WP-1 - Preserve the complete planning contract.

## Token-saving resume note

On resume:

1. Read `AGENTS.md`.
2. Read the canonical goal.
3. Read this status.
4. Read only WP-1 in the canonical plan.
5. Inspect only files listed by WP-1 and related tests.
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
