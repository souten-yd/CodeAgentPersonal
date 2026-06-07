# Atlas Code Generation Completeness Current Status

> Mutable checkpoint for Codex goal mode.  
> Update this file after every work package.  
> Do not use older status or planning documents.

## Goal status

- Overall: Active
- Canonical goal: `docs/atlas_codegen_completeness_goal.md`
- Canonical plan: `docs/atlas_codegen_completeness_implementation_plan.md`
- Baseline commit: `3ac07375610d6de826199be07366f451adfbec63` (PR #1599)
- Current work package: WP-4
- Next action: Fail-close unresolved self-review findings, TODOs, placeholders, empty critical functions, incomplete multi-file output, and disconnected artifacts.

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
| WP-4 | Fail-closed generation quality | Not started | - | - |
| WP-5 | Remove skeleton/fail-open fallbacks | Not started | - | - |
| WP-6 | Requirement-complete final status | Not started | - | - |
| WP-7 | Task-aware verification contracts | Not started | - | - |
| WP-8 | E2E acceptance and final audit | Not started | - | - |

## Last completed work package

WP-3 - Interleaved orchestration.

## Current blockers

None recorded.

## Latest completed work package evidence

Completed work package:
WP-3 - Interleaved orchestration.

PR/commit:
Local WP-3 commit to be created after this status update. No PR, merge, or remote push.

Changed files:
- `agent/atlas_autonomous_codegen_orchestrator_service.py`
- `agent/atlas_patch_proposal_service.py`
- `tests/test_atlas_autonomous_codegen_orchestrator_service.py`
- `tests/test_atlas_codegen_completeness_baseline.py`
- `docs/atlas_codegen_completeness_current_status.md`

Behavior implemented:
- Replaced autonomous batch proposal generation plus batch apply with a per-item interleaved loop: dependency-ready item selection, latest pool reload, context/proposal generation as needed, safe apply/verification through the existing multi-item engine, evidence persistence, then next item.
- Same-file item N+1 now generates against file contents changed by item N because generation and apply/verify are interleaved.
- Existing proposal content with recorded `base_file_revisions` is checked against current file SHA/absent state; mismatch clears stale content and regenerates instead of applying stale output.
- Patch proposal metadata now persists `base_file_revisions` so autonomous apply has concrete preconditions.
- Completed item evidence is persisted back to PlanPool metadata/completed IDs after each sub-run so later proposal input can include completed item summaries.
- Progress metadata now records interleaved sub-runs and revision-triggered regenerations.

Tests passed:
- `python -m pytest -q tests/test_atlas_autonomous_codegen_orchestrator_service.py` -> 32 passed.
- `python -m pytest -q tests/test_atlas_codegen_completeness_baseline.py tests/test_atlas_patch_proposal_codegen_contract.py` -> 11 passed.
- `python -m pytest -q tests/test_atlas_autonomous_codegen_orchestrator_service.py tests/test_atlas_codegen_completeness_baseline.py tests/test_atlas_patch_proposal_codegen_contract.py` -> 43 passed.
- `python -m pytest -q tests/test_atlas_autonomous_codegen_orchestrator_service.py tests/test_atlas_multi_item_autopilot_service.py tests/test_atlas_file_safe_apply_executor.py tests/test_atlas_codegen_completeness_baseline.py tests/test_atlas_patch_proposal_codegen_contract.py` -> 75 passed.
- `python -m pytest -q tests/test_atlas_multi_item_autopilot_path_resolution.py` -> 2 passed.

Syntax checks:
- `python -m py_compile agent/atlas_autonomous_codegen_orchestrator_service.py agent/atlas_multi_item_autopilot_service.py agent/atlas_context_refresh_service.py agent/atlas_auto_safe_apply_service.py agent/atlas_file_safe_apply_executor.py agent/atlas_autonomous_codegen_orchestrator_schema.py agent/atlas_multi_item_autopilot_schema.py agent/atlas_auto_safe_apply_schema.py agent/atlas_patch_proposal_service.py tests/test_atlas_autonomous_codegen_orchestrator_service.py tests/test_atlas_multi_item_autopilot_service.py tests/test_atlas_auto_safe_apply_service.py tests/test_atlas_file_safe_apply_executor.py tests/test_atlas_codegen_completeness_baseline.py tests/test_atlas_patch_proposal_codegen_contract.py` -> passed.

Safety invariants:
- Production changes preserve existing preflight safety gates and continue delegating apply/verification to existing multi-item, safe-apply, rollback, and verification services.
- Clarification and critical-event gates, allowed/blocked paths, active envelope limits, profile bounds, retry bounds, and hard-blocked critical/delete/run_command items remain enforced.
- No direct merge, remote push, self-apply, stable runtime mutation, Vue authority, arbitrary unbounded command execution, or fabricated verification results introduced.
- Backend PlanPool remains authoritative for item state and persisted evidence.

Remaining gaps:
- WP-4 must make unresolved self-review findings and generation-quality defects non-applicable/fail-closed.
- Later WPs must remove fallback skeleton/fail-open paths, enforce requirement-complete final status, and add task-aware verification/E2E acceptance.
- The broader command `python -m pytest -q tests/test_atlas_autonomous_codegen_orchestrator_service.py tests/test_atlas_multi_item_autopilot_service.py tests/test_atlas_auto_safe_apply_service.py tests/test_atlas_file_safe_apply_executor.py tests/test_atlas_codegen_completeness_baseline.py tests/test_atlas_patch_proposal_codegen_contract.py` reported 75 passed and 2 failed. Both failures were in `tests/test_atlas_auto_safe_apply_service.py` because its API seed helper expects `/api/atlas/plan-pools` to return `plan_pool`, while current main returns the queued response shape before WP-3 code runs; this is the same pre-existing API test limitation noted in WP-2 evidence.

Next work package:
WP-4 - Fail-closed generation quality.

## Token-saving resume note

On resume:

1. Read `AGENTS.md`.
2. Read the canonical goal.
3. Read this status.
4. Read only WP-4 in the canonical plan.
5. Inspect only files listed by WP-4 and related tests.
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
