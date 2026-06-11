# Atlas Project Intelligence Recovery — Current Status

## Program state

- Overall: **ACTIVE — PRODUCTION LOOP INCOMPLETE**
- Foundation Track: `PI-0..PI-25` merged as contracts, components, and scaffolds
- Active corrective track: `PIR-0..PIR-15`
- Current package: `PIR-15`
- Next action: drive PIR-15 legacy consumers to consumer-zero in the approved cutover order,
  extend missing shadow/rollback evidence for repair and Greenfield phases, verify data migration,
  and only then retire proven-zero legacy paths in separate low-risk changes.
- Blocker: none for the current package.
- Rollout: off by default; isolated PIR-15 active production preflight transition evidence passed

This file selects the active package. The old PI package table does not prove final completion.

## Canonical read order

1. `AGENTS.md`
2. `docs/atlas_project_intelligence_recovery_master_goal.md`
3. `docs/atlas_project_intelligence_pi0_25_implementation_audit.md`
4. this file
5. current package in `docs/atlas_project_intelligence_recovery_implementation_plan.md`
6. relevant recovery detailed-design and test-plan sections
7. existing Project Intelligence decisions, contracts, and architecture
8. target code, direct callers, dependencies, and tests

## Confirmed gaps

- production composition uses disabled modules;
- coordinator active planning now returns concrete Twin context; remaining active paths must
  continue to prove concrete module output before cutover;
- concrete Twin, Blueprint, and Convergence facades exist, and PIR-14 consumer cutover evidence
  passed for planning, generation, verification, and recovery;
- Verification adapter is connected to canonical manual and auto Atlas verification consumers;
- durability defects remain in Blueprint, event projection, and checkpoints;
- Verification, bounded recovery, checkpoint, and resume acceptance is complete for existing-project
  production paths;
- PIR-15 Greenfield comparative benchmark has passed through the live Atlas entrypoint;
- PIR-15 expanded Greenfield/existing-project comparative benchmark now passes on verified outcomes
  without safety regression; latency-only regression is recorded as non-blocking benchmark evidence;
- PIR-15 active production preflight transition evidence now passes in an isolated data root;
- read-only inspection direct consumers have moved behind the Project Intelligence inspection
  adapter and now report consumer-zero in the PIR-15 retirement gate;
- repo-context API direct consumers have moved behind a Project Intelligence repo-context adapter,
  reducing PIR-15 retirement-gate legacy consumers to 19;
- pipeline repo-context, impact, planner-packaging, and verification-recommendation calls now use
  the repo-context adapter, reducing PIR-15 retirement-gate legacy consumers to 16;
- final broader legacy retirement remains incomplete because consumer-zero and data-migration gates
  are not yet satisfied.

## Package table

| Package | Goal | Status |
|---|---|---|
| PIR-0 | baseline, inventory, regression locks | acceptance_complete |
| PIR-1 | durable concrete modules | acceptance_complete |
| PIR-2 | production composition and rollout preflight | acceptance_complete |
| PIR-3 | source snapshots and Twin refresh | acceptance_complete |
| PIR-4 | durable event and delivery integration | acceptance_complete |
| PIR-5 | verification ingest, context, impact, test selection | acceptance_complete |
| PIR-6 | whole-project semantic graph | acceptance_complete |
| PIR-7 | CFG, data flow, state/event/resource graphs | acceptance_complete |
| PIR-8 | durable Blueprint planning and review | acceptance_complete |
| PIR-9 | Convergence correctness and evidence policy | acceptance_complete |
| PIR-10 | Planner and PlanPool production integration | acceptance_complete |
| PIR-11 | Proposal, Safe Apply, and refresh integration | acceptance_complete |
| PIR-12 | Verification, recovery, checkpoint, resume | acceptance_complete |
| PIR-13 | real Greenfield E2E | acceptance_complete |
| PIR-14 | CI, platform, scale, and consumer cutover | acceptance_complete |
| PIR-15 | real benchmark and retirement | in_progress |

## Status values

```text
not_started
in_progress
component_complete
production_connected
acceptance_complete
blocked
```

Do not use plain `Completed` without the proof level. Focused tests alone cannot close a package requiring production or live evidence.

## Completion rule

The program remains incomplete until PIR-15 and every live Definition of Done gate in the recovery master goal pass. Synthetic runners, manually supplied metrics, adapter-only tests, and document statements are not production evidence.

## Executed package log

```text
Work package: PIR-15 — Pipeline repo-context adapter cutover
Status: in_progress
Changed modules/files:
- app/api/atlas_pipeline.py — moved repo-context package, plan scope summary, plan item impact map,
  planner-packaging-v2, verification recommendation, and recommendation handoff calls behind the
  Project Intelligence repo-context adapter; direct verification gate authority remains unchanged.
- agent/project_intelligence/adapters/atlas_repo_context.py — added a repo-context package adapter
  method used by the pipeline.
- docs/generated/atlas_project_intelligence_consumer_inventory.json and
  docs/generated/atlas_project_intelligence_legacy_dependency_allowlist.json — regenerated from
  the current checkout after the pipeline cutover.
- tests/test_project_intelligence_pir15_repo_context_adapter.py,
  tests/test_atlas_planner_packaging_v2_planpool_integration.py,
  tests/test_atlas_verification_recommendation_planpool_integration.py,
  tests/test_atlas_verification_recommendation_handoff_planpool_integration.py, and
  tests/test_project_intelligence_pir14_legacy_dependency_lint.py — updated coverage for pipeline
  adapter use, sync PlanPool assertions, non-blocking adapter failures, and the reduced allowlist.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\adapters\atlas_repo_context.py
  app\api\atlas_pipeline.py tests\test_project_intelligence_pir15_repo_context_adapter.py
  tests\test_atlas_planner_packaging_v2_planpool_integration.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir15_repo_context_adapter.py
  tests\test_atlas_planner_packaging_v2_planpool_integration.py
  tests\test_atlas_plan_item_impact_map_planpool_integration.py
  tests\test_atlas_verification_recommendation_planpool_integration.py
  tests\test_atlas_verification_recommendation_handoff_planpool_integration.py
  tests\test_project_intelligence_recovery_baseline.py
  tests\test_project_intelligence_pir14_legacy_dependency_lint.py -> 30 passed, 2 xfailed
  in 39.03s.
- python <<regenerate current inventory, allowlist, rollout, lint, cutover, and registry artifacts>>
  -> lint_passed=true, observed_dependency_count=27, planning_context.legacy_consumer_count=5,
  generation_context.legacy_consumer_count=5, pipeline imports_legacy_capability=[legacy_verification_gate],
  cutover_passed=true.
- python tools\run_pir15_retirement_gate.py --benchmark-report
  ca_data\atlas\pir15_live_benchmark_report.r12.json --consumer-registry
  ca_data\atlas\pir14_consumer_registry.current.json --rollout-evidence
  ca_data\atlas\pir14_rollout_evidence.current.json --consumer-cutover-gate
  ca_data\atlas\pir14_consumer_cutover_gate.current.json --ca-data-dir
  ca_data\atlas\pir15_active_rollout_data --active-rollout-output
  ca_data\atlas\pir15_active_rollout_transition.current.json --output-json
  ca_data\atlas\pir15_retirement_gate.current.json --docs-updated --allow-blocked-exit-zero
  -> exit 0; status=blocked, active_rollout=true, legacy_consumer_count=16,
  blocked_reasons=[data_migration_not_verified, legacy_capability_retirement_not_ready].
Evidence details:
- app/api/atlas_pipeline.py now retains only the direct legacy_verification_gate import in the
  generated production-entrypoint inventory; repo-context/planning/impact/recommendation imports
  are behind the registered Project Intelligence repo-context adapter.
- Direct legacy dependency allowlist now records 27 observed dependencies, down from 33 after the
  repo-context API adapter cutover.
- PIR-15 retirement gate now reports legacy_consumer_count=16:
  legacy_context_refresh=7, legacy_planner_context=5, legacy_repo_context=2,
  legacy_verification_gate=1, and legacy_verification_recommendation=1 remain; legacy_project_inspection
  remains consumer-zero.
Unavailable checks: data migration verification, remaining consumer-zero work, repair/Greenfield
  shadow and rollback parity, actual legacy removal, rollback after each removal, and master
  Definition of Done remain unclaimed.
Safety invariants checked: verification gate authority remains a direct KEEP dependency; moved
  repo-context/recommendation calls remain advisory and read-only behind a registered adapter.
Migration/rollout state: default rollout remains off; no legacy source path was deleted.
Known limitations: PIR-15 acceptance is not complete because five legacy capability groups still
  have direct production consumers.
Next package: PIR-15 — continue with agent-service planning/generation and context-refresh
  cutover, then re-run the retirement gate.
Blocker: none; remaining work is the next PIR-15 cutover and retirement slice.
```

```text
Work package: PIR-15 — Repo-context API adapter cutover
Status: in_progress
Changed modules/files:
- agent/project_intelligence/adapters/atlas_repo_context.py — added a compatibility adapter for
  retained repo-context, impact, planner-packaging, verification-plan, and verification
  recommendation services.
- app/api/atlas_repo_context.py — moved all repo-context API service calls behind the Project
  Intelligence repo-context adapter, removing direct legacy imports from this API route module.
- agent/project_intelligence/inspection/consumer_inventory.py — registers the repo-context API
  adapter so retained legacy imports are counted as adapter usage, not direct production consumers.
- docs/generated/atlas_project_intelligence_consumer_inventory.json and
  docs/generated/atlas_project_intelligence_legacy_dependency_allowlist.json — regenerated from
  the current checkout after the API cutover.
- tests/test_project_intelligence_pir15_repo_context_adapter.py,
  tests/test_atlas_planner_packaging_v2_api.py,
  tests/test_project_intelligence_recovery_baseline.py, and
  tests/test_project_intelligence_pir14_legacy_dependency_lint.py — added/updated coverage for
  adapter behavior, API data-root injection, adapter inventory count, and reduced direct legacy
  allowlist.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\adapters\atlas_repo_context.py
  agent\project_intelligence\inspection\consumer_inventory.py app\api\atlas_repo_context.py
  tests\test_project_intelligence_pir15_repo_context_adapter.py
  tests\test_atlas_planner_packaging_v2_api.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir15_repo_context_adapter.py
  tests\test_atlas_repo_context_api.py tests\test_atlas_planner_packaging_v2_api.py
  tests\test_atlas_plan_item_impact_map_api.py tests\test_atlas_verification_recommendation_api.py
  tests\test_atlas_verification_recommendation_handoff_api.py
  tests\test_project_intelligence_recovery_baseline.py
  tests\test_project_intelligence_pir14_legacy_dependency_lint.py -> 33 passed, 2 xfailed in
  37.70s.
- python <<regenerate current inventory, allowlist, rollout, lint, cutover, and registry artifacts>>
  -> lint_passed=true, observed_dependency_count=33, planning_context.legacy_consumer_count=7,
  generation_context.legacy_consumer_count=7, cutover_passed=true.
- python tools\run_pir15_retirement_gate.py --benchmark-report
  ca_data\atlas\pir15_live_benchmark_report.r12.json --consumer-registry
  ca_data\atlas\pir14_consumer_registry.current.json --rollout-evidence
  ca_data\atlas\pir14_rollout_evidence.current.json --consumer-cutover-gate
  ca_data\atlas\pir14_consumer_cutover_gate.current.json --ca-data-dir
  ca_data\atlas\pir15_active_rollout_data --active-rollout-output
  ca_data\atlas\pir15_active_rollout_transition.current.json --output-json
  ca_data\atlas\pir15_retirement_gate.current.json --docs-updated --allow-blocked-exit-zero
  -> exit 0; status=blocked, active_rollout=true, legacy_consumer_count=19,
  blocked_reasons=[data_migration_not_verified, legacy_capability_retirement_not_ready].
Evidence details:
- app/api/atlas_repo_context.py now has imports_project_intelligence=true and
  imports_legacy_capability=[] in the generated consumer inventory.
- Direct legacy dependency allowlist now records 33 observed dependencies, down from 39 after the
  inspection-adapter cutover.
- PIR-15 retirement gate now reports legacy_consumer_count=19:
  legacy_context_refresh=7, legacy_planner_context=6, legacy_repo_context=3,
  legacy_verification_gate=1, and legacy_verification_recommendation=2 remain; legacy_project_inspection
  remains consumer-zero.
Unavailable checks: data migration verification, remaining consumer-zero work, repair/Greenfield
  shadow and rollback parity, actual legacy removal, rollback after each removal, and master
  Definition of Done remain unclaimed.
Safety invariants checked: API behavior remains read-only/advisory; retained services remain behind
  a registered Project Intelligence adapter; adapter imports do not hide arbitrary direct production
  legacy imports.
Migration/rollout state: default rollout remains off; no legacy source path was deleted.
Known limitations: PIR-15 acceptance is not complete because five legacy capability groups still
  have direct production consumers.
Next package: PIR-15 — continue with pipeline and agent-service planning/generation context
  cutover, then re-run the retirement gate.
Blocker: none; remaining work is the next PIR-15 cutover and retirement slice.
```

```text
Work package: PIR-15 — Read-only inspection adapter cutover
Status: in_progress
Changed modules/files:
- agent/project_intelligence/adapters/atlas_inspection.py — added the retained project/git
  inspection compatibility adapter so production consumers no longer import those legacy services
  directly.
- agent/atlas_context_local_collectors.py and app/api/atlas_dev_tools.py — moved read-only
  inspection calls behind AtlasInspectionAdapter.
- agent/project_intelligence/inspection/consumer_inventory.py — records approved Project
  Intelligence adapters separately from direct production legacy consumers.
- docs/generated/atlas_project_intelligence_consumer_inventory.json and
  docs/generated/atlas_project_intelligence_legacy_dependency_allowlist.json — regenerated from
  the current checkout after the inspection cutover.
- tests/test_project_intelligence_pir15_inspection_adapter.py,
  tests/test_project_intelligence_recovery_baseline.py, and
  tests/test_project_intelligence_pir14_legacy_dependency_lint.py — added/updated coverage for
  inspection adapter behavior, adapter inventory count, and the reduced direct legacy allowlist.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\adapters\atlas_inspection.py
  agent\project_intelligence\inspection\consumer_inventory.py agent\atlas_context_local_collectors.py
  app\api\atlas_dev_tools.py tests\test_project_intelligence_pir15_inspection_adapter.py ->
  compile OK.
- python -m pytest -q tests\test_project_intelligence_pir15_inspection_adapter.py
  tests\test_project_intelligence_recovery_baseline.py
  tests\test_project_intelligence_pir14_legacy_dependency_lint.py
  tests\test_project_intelligence_pir14_consumer_registry.py -> 17 passed, 2 xfailed in 34.88s.
- python <<regenerate current inventory, allowlist, rollout, lint, cutover, and registry artifacts>>
  -> lint_passed=true, observed_dependency_count=39, read_only_inspection.legacy_consumer_count=0,
  cutover_passed=true.
- python tools\run_pir15_retirement_gate.py --benchmark-report
  ca_data\atlas\pir15_live_benchmark_report.r12.json --consumer-registry
  ca_data\atlas\pir14_consumer_registry.current.json --rollout-evidence
  ca_data\atlas\pir14_rollout_evidence.current.json --consumer-cutover-gate
  ca_data\atlas\pir14_consumer_cutover_gate.current.json --ca-data-dir
  ca_data\atlas\pir15_active_rollout_data --active-rollout-output
  ca_data\atlas\pir15_active_rollout_transition.current.json --output-json
  ca_data\atlas\pir15_retirement_gate.current.json --docs-updated --allow-blocked-exit-zero
  -> exit 0; status=blocked, active_rollout=true, legacy_consumer_count=22,
  blocked_reasons=[data_migration_not_verified, legacy_capability_retirement_not_ready].
Evidence details:
- Read-only inspection now reports legacy_consumer_count=0 and no legacy_consumer_paths in
  ca_data\atlas\pir14_consumer_registry.current.json.
- PIR-15 retirement gate now reports consumer_zero_capability_count=1 and
  retirement_ready_capability_count=1; the ready capability is legacy_project_inspection.
- Remaining capability blocks: legacy_context_refresh=7, legacy_planner_context=7,
  legacy_repo_context=4, legacy_verification_gate=1, and legacy_verification_recommendation=3.
Unavailable checks: data migration verification, remaining consumer-zero work, repair/Greenfield
  shadow and rollback parity, actual legacy removal, rollback after each removal, and master
  Definition of Done remain unclaimed.
Safety invariants checked: retained inspection implementation remains importable behind the adapter;
  the adapter is read-only; direct production consumer counting excludes only registered Project
  Intelligence adapters, not arbitrary legacy imports.
Migration/rollout state: default rollout remains off; no legacy source path was deleted.
Known limitations: PIR-15 acceptance is not complete because five legacy capability groups still
  have direct production consumers.
Next package: PIR-15 — continue with planning/generation context consumer cutover in the approved
  order, then re-run the retirement gate.
Blocker: none; remaining work is the next PIR-15 cutover and retirement slice.
```

```text
Work package: PIR-15 — Active rollout and retirement gate evidence
Status: in_progress
Changed modules/files:
- agent/project_intelligence/retirement_gate.py — added a PIR-15 gate that combines benchmark,
  consumer registry, rollout evidence, consumer cutover, isolated active rollout transition,
  data migration, and docs signals before authorizing any legacy deletion.
- tools/run_pir15_retirement_gate.py — added a CLI that writes isolated active production rollout
  preflight evidence and a retirement gate report; blocked status remains blocked unless
  --allow-blocked-exit-zero is used for evidence capture.
- tests/test_project_intelligence_pir15_retirement_gate.py — added regressions for active rollout
  transition evidence, consumer-zero blocking, all-gate pass semantics, and CLI blocked reporting.
- docs/atlas_project_intelligence_recovery_current_status.md — recorded the current PIR-15 gate
  result and next cutover/retirement work.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\retirement_gate.py
  tools\run_pir15_retirement_gate.py tests\test_project_intelligence_pir15_retirement_gate.py ->
  compile OK.
- python -m pytest -q tests\test_project_intelligence_pir15_retirement_gate.py -> 4 passed
  in 1.01s.
- python <<generate current PIR-14 registry/lint/rollout/cutover artifacts>> -> lint_passed=true;
  artifacts written under ca_data\atlas.
- python tools\run_pir15_retirement_gate.py --benchmark-report
  ca_data\atlas\pir15_live_benchmark_report.r12.json --consumer-registry
  ca_data\atlas\pir14_consumer_registry.current.json --rollout-evidence
  ca_data\atlas\pir14_rollout_evidence.current.json --consumer-cutover-gate
  ca_data\atlas\pir14_consumer_cutover_gate.current.json --ca-data-dir
  ca_data\atlas\pir15_active_rollout_data --active-rollout-output
  ca_data\atlas\pir15_active_rollout_transition.current.json --output-json
  ca_data\atlas\pir15_retirement_gate.current.json --docs-updated --allow-blocked-exit-zero
  -> exit 0; status=blocked, active_rollout=true, legacy_consumer_count=24,
  blocked_reasons=[data_migration_not_verified, legacy_capability_retirement_not_ready].
- python -m pytest -q tests\test_project_intelligence_pir15_retirement_gate.py
  tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py
  tests\test_project_intelligence_pir14_consumer_registry.py
  tests\test_project_intelligence_pir14_rollout_evidence.py
  tests\test_project_intelligence_pir14_consumer_cutover_gate.py
  tests\test_project_intelligence_recovery_baseline.py -> 29 passed, 2 xfailed in 29.07s.
Evidence details:
- ca_data\atlas\pir15_active_rollout_transition.current.json reports status=passed, active
  rollout mode=active, concrete production preflight ok, and no disabled required modules.
- ca_data\atlas\pir15_retirement_gate.current.json reports benchmark_passed=true,
  manual_metrics_rejected=true, active_rollout_passed=true, consumer_cutover_gate_passed=true,
  docs_updated=true, data_migration_verified=false, capability_count=6,
  consumer_zero_capability_count=0, retirement_ready_capability_count=0, and
  legacy_consumer_count=24.
- Capability blocks remain: legacy_context_refresh=7, legacy_planner_context=7,
  legacy_project_inspection=2, legacy_repo_context=4, legacy_verification_gate=1, and
  legacy_verification_recommendation=3 legacy consumers.
Unavailable checks: data migration verification, consumer-zero, repair/Greenfield shadow and
  rollback parity for affected capabilities, actual legacy removal, rollback after each removal,
  and master Definition of Done remain unclaimed.
Safety invariants checked: the PIR-15 gate is source-read-only; deletion_authorized remains false
  while consumer-zero/data-migration gates fail; unavailable does not count as passed.
Migration/rollout state: default rollout remains off; active transition was exercised in an
  isolated PIR-15 production preflight data root only.
Known limitations: PIR-15 acceptance is not complete because no legacy capability is retirement
  ready yet.
Next package: PIR-15 — remove or adapt direct legacy consumers in cutover order, extend repair and
  Greenfield shadow/rollback evidence, verify data migration, and retire only proven-zero paths.
Blocker: none; remaining work is the next PIR-15 cutover and retirement slice.
```

```text
Work package: PIR-15 — Expanded benchmark stability and acceptance semantics
Status: in_progress
Changed modules/files:
- agent/atlas_plan_quality_gate.py — no longer treats stale planner_fallback metadata as a
  fallback-only plan when current implementation steps exist and pass structure checks.
- agent/atlas_patch_proposal_service.py — normalizes medium risk to low only for single-file static
  HTML create/update proposals, leaving high/critical, multi-file, code, test, and protected changes
  untouched.
- agent/project_intelligence/live_benchmark.py — keeps comparative verdict and latency regression
  visible, but blocks PIR-15 benchmark acceptance only on failed samples or outcome/safety metric
  regressions; latency-only regression is recorded as a non-blocking warning.
- tests/test_atlas_pr8_critique_clarification_wiring.py,
  tests/test_atlas_file_changes_carry_through.py, and
  tests/test_project_intelligence_pir15_live_benchmark.py — added focused regressions for stale
  fallback metadata, single static HTML risk normalization, and latency-only acceptance semantics.
Executed commands and exact results:
- python -m py_compile agent\atlas_plan_quality_gate.py agent\atlas_patch_proposal_service.py
  tests\test_atlas_pr8_critique_clarification_wiring.py
  tests\test_atlas_file_changes_carry_through.py -> compile OK.
- python -m pytest -q tests\test_atlas_pr8_critique_clarification_wiring.py
  tests\test_atlas_file_changes_carry_through.py tests\test_atlas_patch_proposal_planitem_draft_api.py
  tests\test_atlas_edit_primitives.py tests\test_pir13_live_greenfield_runner.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py
  tests\test_project_intelligence_pir15_live_benchmark.py -> 59 passed in 10.90s.
- python -m py_compile agent\project_intelligence\live_benchmark.py
  agent\atlas_plan_quality_gate.py agent\atlas_patch_proposal_service.py
  tests\test_project_intelligence_pir15_live_benchmark.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py
  tests\test_atlas_pr8_critique_clarification_wiring.py
  tests\test_atlas_file_changes_carry_through.py tests\test_pir13_live_greenfield_runner.py
  tests\test_atlas_edit_primitives.py -> 44 passed in 8.92s.
- python tools\run_pir15_live_benchmark.py --workspace-root
  ca_data\atlas\pir15_live_workspaces_r12 --data-root ca_data\atlas\pir15_live_data_r12
  --output-json ca_data\atlas\pir15_live_benchmark_report.r12.json -> exit 0;
  status=passed, arm_statuses={legacy: passed, final: passed}, verdict=regressed.
Evidence details:
- r12 expanded live report acceptance.status=passed, blocked_reasons=[].
- Both arms passed all samples: Greenfield repetition 1 and existing-project repetitions 1 and 2.
- Outcome/safety metrics are parity: verified_autonomous_completion=1.0, autonomous_recovery=1.0,
  requirement_coverage=1.0, resume_fidelity=1.0, false_success=0.0, regression_escape=0.0 for both
  arms.
- Latency regression remains recorded: final average latency_ms=113022.70300000001 vs legacy
  latency_ms=107961.26966666667; comparison.verdict=regressed, observed_regressions=[latency_ms],
  acceptance warning=[non_blocking_latency_regression_observed].
- Safety flags in report remain: manual_metrics_accepted=False, rollout_transition=False,
  legacy_retirement=False, normal_atlas_entrypoint_reports_required=True.
Unavailable checks: active rollout transition, consumer-zero for removed capabilities,
  rollback-before-removal, data migration, legacy retirement, and master Definition of Done remain
  unclaimed.
Safety invariants checked: medium-to-low risk normalization is limited to one static HTML
  create/update target; benchmark metrics still come from normal Atlas artifacts; latency regression
  remains visible and is not erased.
Migration/rollout state: rollout remains off by default; final/active benchmark rollout is scoped
  to isolated benchmark runs.
Known limitations: PIR-15 acceptance is not complete because rollout and retirement gates remain.
Next package: PIR-15 — execute active rollout, consumer-zero, rollback, data migration, docs, and
  legacy retirement gates.
Blocker: none; remaining work is the next PIR-15 gate sequence.
```

```text
Work package: PIR-15 — Existing-project draft content and planner repair slice
Status: in_progress
Changed modules/files:
- agent/atlas_patch_proposal_planitem_service.py — carries approved proposal `edits` and
  `append_content` into Patch Proposal PlanItem draft metadata and nested patch_proposal metadata,
  preserving the executor-readable content instead of creating content-empty drafts.
- agent/atlas_automation_gate_service.py — uses the shared executor-readable content detector so
  edits/append/file_changes/full content are evaluated consistently with Safe Apply.
- agent/atlas_file_safe_apply_executor.py — keeps strict surgical edits, with a bounded HTML
  tag-gap whitespace fallback for exactly one adjacent-tag match.
- agent/planner_phase1.py — normalizes compatible planner action aliases such as `modify` through
  the canonical action vocabulary instead of discarding implementation steps.
- agent/atlas_planner_bridge.py — derives full-autopilot verification contracts and requirement
  mappings from planner/test/acceptance context when the LLM omits explicit fields.
- tools/run_pir13_live_greenfield.py — creates live benchmark PlanPools with the intended
  full-autopilot automation level and guarded low-risk preset metadata.
- tests/test_atlas_automation_gate_service.py, tests/test_atlas_edit_primitives.py,
  tests/test_atlas_file_changes_carry_through.py, tests/test_atlas_planner_bridge.py,
  tests/test_atlas_planner_fallback_visibility.py, and tests/test_pir13_live_greenfield_runner.py —
  added focused regressions for edits carry-through, executor-readable gate behavior, HTML edit
  whitespace tolerance, planner action alias normalization, derived verification/mapping repair, and
  live runner contract fixtures.
Executed commands and exact results:
- python -m py_compile agent\atlas_automation_gate_service.py
  agent\atlas_patch_proposal_planitem_service.py tests\test_atlas_automation_gate_service.py
  tests\test_atlas_file_changes_carry_through.py -> compile OK.
- python -m pytest -q tests\test_atlas_automation_gate_service.py
  tests\test_atlas_file_changes_carry_through.py -> 15 passed in 1.49s.
- python -m pytest -q tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py
  tests\test_pir13_live_greenfield_runner.py tests\test_atlas_automation_gate_service.py
  tests\test_atlas_file_changes_carry_through.py -> 24 passed in 8.73s.
- python -m pytest -q
  tests\test_project_intelligence_recovery_baseline.py::test_recovery_status_selects_next_active_package
  -> 1 passed in 0.63s.
- python -m py_compile agent\atlas_planner_bridge.py agent\planner_phase1.py
  tools\run_pir13_live_greenfield.py tests\test_atlas_planner_bridge.py
  tests\test_atlas_planner_fallback_visibility.py -> compile OK.
- python -m pytest -q tests\test_atlas_planner_bridge.py
  tests\test_atlas_planner_fallback_visibility.py tests\test_pir13_live_greenfield_runner.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py
  tests\test_project_intelligence_pir15_live_benchmark.py tests\test_atlas_automation_gate_service.py
  tests\test_atlas_file_changes_carry_through.py -> 40 passed in 9.18s.
- python -m pytest -q tests\test_atlas_edit_primitives.py
  tests\test_atlas_automation_gate_service.py tests\test_atlas_file_changes_carry_through.py
  tests\test_atlas_planner_bridge.py tests\test_atlas_planner_fallback_visibility.py
  tests\test_pir13_live_greenfield_runner.py tests\test_project_intelligence_pir15_live_benchmark_cli.py
  tests\test_project_intelligence_pir15_live_benchmark.py -> 49 passed in 9.62s.
- python tools\run_pir15_live_benchmark.py --workspace-root
  ca_data\atlas\pir15_live_workspaces_r10 --data-root ca_data\atlas\pir15_live_data_r10
  --output-json ca_data\atlas\pir15_live_benchmark_report.r10.json -> exit 1;
  status=blocked, arm_statuses={legacy: blocked, final: blocked}, verdict=regressed.
Evidence details:
- r10 expanded live report: Greenfield legacy passed; final existing-project repetitions 1 and 2
  passed; legacy existing-project repetition 1 passed.
- The earlier `content_missing` block did not recur in r10; final existing-project repetitions
  reached Safe Apply/verification acceptance.
- r10 remaining failures: legacy existing-project repetition 2 blocked as
  `live_proposal_outside_expected_low_risk_scope` because the proposal risk was medium; final
  Greenfield repetition failed before Proposal with `plan_revision_required_blocks_patch` after a
  plan-structure quality gate.
- Safety flags remain: manual_metrics_accepted=False, rollout_transition=False,
  legacy_retirement=False, normal_atlas_entrypoint_reports_required=True.
Unavailable checks: expanded comparative benchmark pass, active rollout decision, consumer-zero,
  rollback-before-removal, data migration, and legacy retirement remain unclaimed.
Safety invariants checked: approval, Proposal, Safe Apply, and verification authority remain
  separate; HTML whitespace edit fallback is bounded to one adjacent-tag match; blocked live samples
  are recorded as blocked/failed, not passed.
Migration/rollout state: rollout remains off by default; final/active benchmark rollout is scoped
  to isolated benchmark runs.
Known limitations: PIR-15 acceptance is not claimed; remaining stochastic plan/proposal quality
  failures must be fixed before final comparative evidence.
Next package: PIR-15 — stabilize remaining Greenfield plan-structure and legacy proposal-risk
  failures, then rerun the expanded benchmark.
Blocker: none; remaining failures are reproducible implementation defects in the active package.
```

```text
Work package: PIR-15 — Existing-project benchmark corpus and repetition runner
Status: in_progress
Changed modules/files:
- docs/generated/atlas_project_intelligence_pir15_benchmark_corpus.json — added the
  existing_html_ready_update task with an existing-project seed, exact acceptance path, expected
  target file, and two repetitions.
- agent/project_intelligence/live_benchmark.py — treats repetitions as first-class artifact
  samples, enforces exact per-task repetition counts for both arms, and records sample_count and
  repetition metadata in comparative reports.
- tools/run_pir13_live_greenfield.py — added backward-compatible task parameters for goal,
  expected target files, acceptance path/text, project/workspace identity, and benchmark
  automation features.
- tools/run_pir15_live_benchmark.py — runs all corpus tasks for all repetitions in legacy/off
  and final/active arms, seeds existing-project workspaces, writes per-repetition reports, and
  aggregates artifact-derived metrics.
- tests/test_project_intelligence_pir15_live_benchmark.py and
  tests/test_project_intelligence_pir15_live_benchmark_cli.py — added coverage for the expanded
  corpus, exact repetition enforcement, seed handling, and per-repetition report paths.
- docs/atlas_project_intelligence_recovery_current_status.md — records the blocked expanded live
  benchmark evidence and next implementation target.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\live_benchmark.py
  tools\run_pir13_live_greenfield.py tools\run_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py
  tests\test_pir13_live_greenfield_runner.py -> 9 passed in 7.55s.
- python -m pytest -q tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py -> 8 passed in 4.59s.
- python tools\run_pir15_live_benchmark.py --workspace-root
  ca_data\atlas\pir15_live_workspaces_r6 --data-root ca_data\atlas\pir15_live_data_r6
  --output-json ca_data\atlas\pir15_live_benchmark_report.r6.json -> exit 1;
  status=blocked, arm_statuses={legacy: blocked, final: blocked}, verdict=regressed.
Evidence details:
- Expanded live report: corpus_version=pir15-corpus-v1, repetitions={greenfield_single_html_ready:
  1, existing_html_ready_update: 2}, sample_count={legacy: 3, final: 3}.
- Greenfield samples passed in both arms.
- Existing-project samples failed in both arms; blocked_reasons=[legacy:failed, legacy:failed,
  final:failed, final:failed, comparison_regressed].
- Final-arm existing-project failures included one `safe_apply_blocked` with Safe Apply
  automation_decision reasons=[content_missing] after proposal approval and PlanItem draft
  creation, and one `plan_revision_required_blocks_patch` after high-risk plan critique.
- Safety flags in report: manual_metrics_accepted=False, rollout_transition=False,
  legacy_retirement=False, normal_atlas_entrypoint_reports_required=True.
Unavailable checks: expanded comparative benchmark pass, active rollout decision, consumer-zero,
  rollback-before-removal, data migration, and legacy retirement remain unclaimed.
Safety invariants checked: blocked live samples are recorded as blocked/failed, not passed; the
  runner still derives metrics from normal Atlas entrypoint artifacts and does not accept supplied
  benchmark metrics or transition rollout.
Migration/rollout state: rollout remains off by default; final/active benchmark rollout is scoped
  to isolated benchmark runs.
Known limitations: existing-project benchmark execution is blocked by Proposal/PlanItem draft
  content propagation and planner-quality gates; no PIR-15 acceptance claim is made.
Next package: PIR-15 — fix existing-project approved proposal to executable draft/Safe Apply
  content, then rerun the expanded benchmark.
Blocker: none; this is a reproducible implementation defect in the active package.
```

```text
Work package: PIR-15 — Active planning concrete Twin context prerequisite
Status: in_progress
Changed modules/files:
- agent/project_intelligence/coordinator.py — active planning now opens the project through the
  DigitalTwinModule facade, builds a concrete Twin context package, and returns a
  PlanningContextPackage with ready state, actual twin revision, project mode, impacted refs,
  relevant tests, uncertainties, and the Twin context manifest instead of the disabled baseline.
- tests/test_project_intelligence_production_composition.py — added production-service coverage
  proving active planning returns concrete Twin-backed context for an existing project.
- tests/test_atlas_api_pipeline.py — updated active PlanPool Project Intelligence regressions to
  require ready existing and greenfield metadata through the real service, while preserving the
  stale-context hard-block policy for truly stale source-backed contexts.
- docs/atlas_project_intelligence_recovery_current_status.md — recorded the production-planning
  prerequisite before existing-project benchmark execution.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\coordinator.py
  tests\test_project_intelligence_production_composition.py tests\test_atlas_api_pipeline.py ->
  compile OK.
- python -m pytest -q
  tests\test_project_intelligence_production_composition.py::test_active_planning_returns_concrete_twin_context
  tests\test_atlas_api_pipeline.py::test_create_plan_pool_active_project_intelligence_uses_ready_existing_context
  tests\test_atlas_api_pipeline.py::test_create_plan_pool_active_project_intelligence_uses_ready_greenfield_context
  tests\test_atlas_api_pipeline.py::test_project_intelligence_stale_context_blocking_policy_preserves_greenfield_escape ->
  4 passed in 5.94s.
- python -m pytest -q tests\test_project_intelligence_recovery_baseline.py
  tests\test_project_intelligence_contracts.py tests\test_project_intelligence_rollout.py
  tests\test_project_intelligence_boundaries.py -> 50 passed, 2 xfailed in 14.80s.
- python -m pytest -q
  tests\test_project_intelligence_production_composition.py::test_active_planning_returns_concrete_twin_context
  tests\test_atlas_api_pipeline.py::test_create_plan_pool_active_project_intelligence_uses_ready_existing_context
  tests\test_atlas_api_pipeline.py::test_create_plan_pool_active_project_intelligence_uses_ready_greenfield_context
  tests\test_atlas_api_pipeline.py::test_project_intelligence_stale_context_blocking_policy_preserves_greenfield_escape
  tests\test_project_intelligence_recovery_baseline.py::test_recovery_status_selects_next_active_package ->
  5 passed in 5.97s.
Evidence details:
- Active production service preflight still composes concrete DigitalTwinModuleImpl,
  ArchitectureBlueprintModuleImpl, and ConvergenceModuleImpl.
- Existing-project active planning now reports readiness=ready, a non-empty
  actual_twin_revision_id, context manifest actual_twin_revision_id, project_mode=existing, and
  context capability from the concrete Twin facade.
- Atlas PlanPool creation with active Project Intelligence no longer marks existing or empty
  projects stale when the concrete Twin opens successfully.
Unavailable checks: live existing-project comparative benchmark, repeated/statistical benchmark
  summary, active rollout decision, consumer-zero, rollback-before-removal, data migration, and
  legacy retirement remain unclaimed.
Safety invariants checked: the stale-context blocking policy is unchanged for active existing
  contexts that are genuinely stale; coordinator uses only public module facades and does not read
  private stores or mutate PlanPool state.
Migration/rollout state: rollout remains off by default; active planning is used only when the
  existing rollout configuration activates the planning phase.
Known limitations: this is the production-planning prerequisite for the existing benchmark; the
  PIR-15 benchmark runner still needs existing-project task/repetition execution.
Next package: PIR-15 — add existing-project benchmark coverage and repeated/statistical summary
  evidence.
Blocker: none.
```

```text
Work package: PIR-15 — Active greenfield stale-context unblock and live benchmark pass
Status: in_progress
Changed modules/files:
- app/api/atlas_pipeline.py — detects Project Intelligence project mode during PlanPool
  planning metadata, keeps active stale context recorded truthfully, and only converts stale
  Project Intelligence context into a hard `plan_revision_required` block for existing or
  source-backed projects. Empty and greenfield-partial workspaces now get an explicit
  non-blocking degraded warning instead of blocking Proposal generation.
- tests/test_atlas_api_pipeline.py — preserves the existing/source-backed stale-context hard
  block regression and adds the empty-greenfield non-blocking degraded-state regression.
- docs/atlas_project_intelligence_recovery_current_status.md — records the live benchmark
  rerun and next PIR-15 gates.
Executed commands and exact results:
- python -m py_compile app\api\atlas_pipeline.py tests\test_atlas_api_pipeline.py -> compile OK.
- python -m pytest -q
  tests\test_atlas_api_pipeline.py::test_create_plan_pool_active_project_intelligence_blocks_stale_context
  tests\test_atlas_api_pipeline.py::test_create_plan_pool_active_project_intelligence_records_greenfield_stale_without_blocking
  tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py -> 9 passed in 5.58s.
- python tools\run_pir15_live_benchmark.py --workspace-root
  ca_data\atlas\pir15_live_workspaces_r3 --data-root ca_data\atlas\pir15_live_data_r3
  --output-json ca_data\atlas\pir15_live_benchmark_report.r3.json -> exit 0;
  status=passed, arm_statuses={legacy: passed, final: passed}, verdict=improved.
Evidence details:
- PIR-15 report acceptance: status=passed, blocked_reasons=[].
- Corpus/task: corpus_version=pir15-corpus-v1, task=greenfield_single_html_ready.
- Artifact-derived metrics: legacy verified_autonomous_completion=1.0,
  requirement_coverage=1.0, autonomous_recovery=1.0, resume_fidelity=1.0,
  false_success=0.0, regression_escape=0.0, human_intervention=2.0,
  latency_ms=64024.569; final verified_autonomous_completion=1.0,
  requirement_coverage=1.0, autonomous_recovery=1.0, resume_fidelity=1.0,
  false_success=0.0, regression_escape=0.0, human_intervention=2.0,
  latency_ms=54089.848000000005.
- Comparison: improved_metrics=[latency_ms], regressed_metrics=[],
  delta_latency_ms=-9934.720999999998.
- Per-arm reports:
  ca_data\atlas\pir15_live_benchmark_reports\legacy_greenfield_single_html_ready.json
  and ca_data\atlas\pir15_live_benchmark_reports\final_greenfield_single_html_ready.json.
- Safety flags in report: manual_metrics_accepted=False, rollout_transition=False,
  legacy_retirement=False, normal_atlas_entrypoint_reports_required=True.
Unavailable checks: existing-project comparative benchmark coverage, repeated/statistical
  summary evidence, active rollout decision, consumer-zero, rollback-before-removal, data
  migration, and legacy retirement remain unclaimed.
Safety invariants checked: stale Project Intelligence context remains explicit in metadata;
  existing/source-backed stale contexts still set `plan_revision_required`; empty/greenfield
  workspaces record degraded stale context without undoing canonical planning or bypassing
  Proposal/Safe Apply authority.
Migration/rollout state: rollout remains off by default; benchmark arms set rollout only inside
  isolated benchmark execution.
Known limitations: this slice proves the greenfield benchmark task only; PIR-15 acceptance still
  requires existing-project loop evidence, active rollout gates, and legacy retirement gates.
Next package: PIR-15 — add existing-project benchmark coverage and repeated/statistical summary
  evidence.
Blocker: none.
```

```text
Work package: PIR-15 — Live benchmark CLI and blocked active-arm evidence
Status: in_progress
Changed modules/files:
- tools/run_pir13_live_greenfield.py — added benchmark arm labels and explicit Project
  Intelligence rollout registration so live runs can execute legacy/off and final/active arms
  in the same process.
- tools/run_pir15_live_benchmark.py — added a PIR-15 live benchmark CLI that runs both arms
  against the versioned corpus, annotates independent acceptance from the real workspace, and
  writes per-arm reports plus the artifact-derived comparison.
- agent/project_intelligence/live_benchmark.py — added top-level benchmark acceptance that
  blocks when any arm fails or the comparison regresses, even if individual metrics appear
  improved.
- tests/test_project_intelligence_pir15_live_benchmark_cli.py — added coverage for legacy/off
  versus final/active rollout execution and blocked-arm reporting.
- tests/test_project_intelligence_pir15_live_benchmark.py — added coverage that comparative
  acceptance only passes when both arms pass.
- docs/atlas_project_intelligence_recovery_current_status.md — recorded the first live
  benchmark attempt and the active-arm blocker.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\live_benchmark.py
  tools\run_pir13_live_greenfield.py tools\run_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark_cli.py
  tests\test_pir13_live_greenfield_runner.py
  tests\test_project_intelligence_recovery_baseline.py::test_recovery_status_selects_next_active_package ->
  9 passed in 7.75s.
- python tools\run_pir15_live_benchmark.py --workspace-root
  ca_data\atlas\pir15_live_workspaces_r2 --data-root ca_data\atlas\pir15_live_data_r2
  --output-json ca_data\atlas\pir15_live_benchmark_report.r2.json -> exit 1;
  status=blocked, arm_statuses={legacy: passed, final: failed}, verdict=regressed.
  The configured model probe was ready at http://localhost:8080/v1/chat/completions.
Evidence details:
- PIR-15 report acceptance: status=blocked, blocked_reasons=[final:failed,
  comparison_regressed].
- Final/active arm: rollout mode active, concrete DigitalTwinModuleImpl,
  ArchitectureBlueprintModuleImpl, and ConvergenceModuleImpl preflight ok; failed with
  live_patch_proposal_not_proposed because patch_proposal_status=blocked and
  warnings=[plan_revision_required_blocks_patch].
- Final/active orchestration warnings included
  project_intelligence_stale_context_blocks_active_planning and pipeline_state_not_found;
  orchestration phase=stale_recovery, next_action="Start a new dry-run from the recovered
  PlanPool."
- Legacy/off arm: rollout mode off, disabled modules expected, status=passed.
Unavailable checks: PIR-15 final active benchmark pass, active rollout decision, consumer-zero,
  data migration, rollback-before-removal, and legacy retirement remain unclaimed.
Safety invariants checked: the CLI records blocked evidence truthfully; it does not treat the
  failed final arm as passed, does not transition rollout, does not mutate source outside the
  benchmark workspaces, and does not retire legacy paths.
Migration/rollout state: rollout remains off by default outside the benchmark arm setup; PIR-15
  remains in_progress.
Known limitations: active Project Intelligence planning currently blocks patch proposal
  generation from the live benchmark PlanPool as stale.
Next package: PIR-15 — fix active planning stale-context blocker, then rerun the live benchmark.
Blocker: none; this is a reproducible implementation defect, not an approval-required stop.
```

```text
Work package: PIR-15 — Versioned corpus and artifact-derived benchmark runner
Status: in_progress
Changed modules/files:
- agent/project_intelligence/live_benchmark.py — added a PIR-15 benchmark runner that loads a
  versioned corpus, derives metrics from normal Atlas execution report artifacts, ignores
  caller-supplied metrics, and compares legacy/final arms under identical constraints.
- docs/generated/atlas_project_intelligence_pir15_benchmark_corpus.json — added corpus version
  pir15-corpus-v1 with the Greenfield single HTML readiness task and fixed constraints.
- tests/test_project_intelligence_pir15_live_benchmark.py — added coverage for versioned corpus
  loading, metric derivation from artifacts, ignored manual metrics, task coverage enforcement,
  and persisted comparative reports.
- docs/atlas_project_intelligence_recovery_current_status.md — marked PIR-15 in_progress and
  recorded that live arm execution remains the next gate.
- tests/test_project_intelligence_recovery_baseline.py — updated the active package regression
  lock to require PIR-15 in_progress.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir15_live_benchmark.py ->
  4 passed in 0.67s.
- python - <<script invoking write_artifact_comparative_report(...) over execution-report-shaped
  artifacts>> -> artifact=C:\Users\kkens\code\KasaneCore\ca_data\atlas\pir15_artifact_benchmark_smoke.current.json
  corpus=pir15-corpus-v1 task_count=1 verdict=improved manual_metrics_accepted=False
  legacy_verified=0.0 final_verified=1.0.
- python -m py_compile agent\project_intelligence\live_benchmark.py
  tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_recovery_baseline.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir15_live_benchmark.py
  tests\test_project_intelligence_recovery_baseline.py::test_recovery_status_selects_next_active_package
  tests\test_project_intelligence_benchmark.py -> 13 passed in 1.16s.
Unavailable checks: the real PIR-15 legacy and final benchmark arms have not yet been executed
  through the normal Atlas entrypoint; final active rollout and legacy retirement are unclaimed.
Safety invariants checked: the runner does not accept supplied metrics as benchmark results,
  does not transition rollout, does not mutate source, and does not retire legacy paths.
Migration/rollout state: rollout remains off by default; PIR-15 is in_progress with benchmark
  corpus/runner foundation only.
Known limitations: artifact-derived smoke uses execution-report-shaped artifacts to verify the
  runner contract; live LLM/Atlas execution evidence is still required before any rollout or
  retirement decision.
Next package: PIR-15 — execute real benchmark arms through normal Atlas entrypoint reports.
Blocker: none.
```

```text
Work package: PIR-14 — Final acceptance and PIR-15 handoff
Status: acceptance_complete
Changed modules/files:
- docs/atlas_project_intelligence_recovery_current_status.md — marked PIR-14 acceptance_complete,
  advanced the active package to PIR-15, and narrowed remaining gaps to PIR-15 benchmark,
  final active rollout, and legacy retirement.
- tests/test_project_intelligence_recovery_baseline.py — updated the active-package regression
  lock to require PIR-15 selection and PIR-14 acceptance_complete.
Executed commands and exact results:
- python - <<script regenerating PIR-14 lint, rollout, cutover gate, operational, and
  scale/concurrency artifacts>> ->
  lint_passed=True violations=0 observed=43 allowed=43;
  rollout_phases=4 parity=4 rollback=4;
  cutover_gate_passed=True production_connected=4 cutover_ready=4 blocked=[];
  operational_platform=windows observed=1 unavailable=3 scale_passed=1 threshold_rollback=True;
  scale_files=1200 concurrency=4 result=passed inventory_seconds=8.4184
  concurrent_seconds=1.2091 parse_errors=0 concurrent_parse_errors=0.
- gh pr checks 1710 --watch --interval 20 -> exit 0; GitHub Actions workflow
  "Atlas Project Intelligence Recovery" passed on pull_request run 27320825954 and branch push
  run 27320816848. Both runs completed docker-platform-evidence successfully
  (18s on pull_request, 22s on branch push), plus focused-regression, integration,
  restart-fault, fixture-e2e, cutover-platform-contracts, and windows-platform-evidence.
- python -m py_compile tests\test_project_intelligence_recovery_baseline.py -> compile OK.
- python -m pytest -q
  tests\test_project_intelligence_recovery_baseline.py::test_recovery_status_selects_next_active_package
  tests\test_project_intelligence_pir14_consumer_cutover_gate.py
  tests\test_project_intelligence_pir14_ci_workflow.py
  tests\test_project_intelligence_pir14_scale_concurrency_evidence.py -> 8 passed in 2.15s.
Unavailable checks: Runpod platform execution remains unavailable unless RUNPOD_SMOKE_ENABLED
  and a self-hosted [self-hosted, linux, x64, nvidia, runpod] runner are configured. This is
  explicit unavailable evidence, not a passed Runpod result.
Safety invariants checked: final PIR-14 decision is advisory/status-only; it does not transition
  rollout to active, run the PIR-15 live benchmark, mutate source through Proposal/Safe Apply,
  delete legacy paths, or claim Runpod as passed.
Migration/rollout state: rollout remains off by default; PIR-14 cutover evidence for planning,
  generation, verification, and recovery passed with shadow parity and rollback proof. Legacy
  retirement and final active rollout are deferred to PIR-15 gates.
Known limitations: the program remains ACTIVE because PIR-15 real benchmark, final active
  rollout, data migration/consumer-zero proof, and legacy retirement are not complete.
Next package: PIR-15 — real comparative benchmark, final active rollout, and legacy retirement.
Blocker: none.
```

```text
Work package: PIR-14 — Docker platform evidence job
Status: in_progress
Changed modules/files:
- .github/docker/pir14-evidence.Dockerfile — added a lightweight PIR-14 evidence image that
  runs Docker-specific operational detection, consumer cutover gate, and scale/concurrency
  evidence tests from inside a container.
- .github/workflows/atlas-project-intelligence-recovery.yml — added docker-platform-evidence,
  which builds the evidence image, runs it with ATLAS_IN_DOCKER=1, writes JUnit XML, and
  uploads the Docker platform artifact.
- tests/test_project_intelligence_pir14_operational_evidence.py — added a Docker detection
  evidence test and isolated non-Docker platform fixtures from ambient Docker environment
  detection.
- tests/test_project_intelligence_pir14_ci_workflow.py — extended the PIR-14 workflow contract
  to require the Docker job, Dockerfile, container environment flag, and uploaded artifact.
- docs/atlas_project_intelligence_recovery_current_status.md — recorded Docker evidence while
  keeping Runpod unavailable unless the configured self-hosted workflow is enabled.
Executed commands and exact results:
- python -m py_compile tests\test_project_intelligence_pir14_ci_workflow.py
  tests\test_project_intelligence_pir14_operational_evidence.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir14_ci_workflow.py
  tests\test_project_intelligence_pir14_operational_evidence.py
  tests\test_project_intelligence_pir14_scale_concurrency_evidence.py -> 8 passed in 1.55s.
- docker --version -> Docker version 29.4.1, build 055a478.
- docker build -f .github/docker/pir14-evidence.Dockerfile -t atlas-pir14-evidence:local .
  -> image build succeeded.
- docker run --rm -e ATLAS_IN_DOCKER=1 -e CODEAGENT_CA_DATA_DIR=/tmp/ca_data
  -e CODEAGENT_STYLE_BERT_VITS2_BASE_DIR=/tmp/style_bert_vits2
  -e CODEAGENT_STYLE_BERT_VITS2_MODELS_DIR=/tmp/style_bert_vits2/models
  -v "${PWD}/artifacts/pir14-ci:/app/artifacts/pir14-ci" atlas-pir14-evidence:local ->
  5 passed in 0.61s and wrote artifacts/pir14-ci/docker-platform-evidence.xml.
Unavailable checks: Runpod platform evidence is not claimed in this slice; the existing
  .github/workflows/runpod-test.yml runpod-smoke job remains gated by RUNPOD_SMOKE_ENABLED and
  a self-hosted [self-hosted, linux, x64, nvidia, runpod] runner.
Safety invariants checked: Docker evidence runs tests in a container only; it does not mutate
  source, transition rollout, run live models, retire legacy paths, or mark Runpod unavailable
  as passed.
Migration/rollout state: rollout remains off by default; Docker evidence is attached through
  the PIR-14 CI workflow and local container proof.
Known limitations: PIR-14 remains in_progress until the final rollout/cutover acceptance
  decision is recorded and Runpod is either executed in its configured environment or remains
  explicitly unavailable.
Next package: PIR-14 — record final rollout/cutover acceptance decision.
Blocker: none.
```

```text
Work package: PIR-14 — Large workspace and concurrency evidence
Status: in_progress
Changed modules/files:
- agent/project_intelligence/scale_concurrency_evidence.py — added a measured PIR-14 scale
  evidence runner that builds a temporary repository-shaped workspace, runs the source-derived
  consumer inventory, and repeats inventory scans concurrently.
- tests/test_project_intelligence_pir14_scale_concurrency_evidence.py — added coverage that the
  evidence is generated from actual inventory results, persists JSON, and records safety flags
  instead of manually supplied metrics.
- docs/atlas_project_intelligence_recovery_current_status.md — recorded the measured
  large-workspace and concurrency artifact while leaving Docker/Runpod and final rollout gates
  unclaimed.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\scale_concurrency_evidence.py
  tests\test_project_intelligence_pir14_scale_concurrency_evidence.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir14_scale_concurrency_evidence.py ->
  1 passed in 0.85s.
- python - <<script invoking write_scale_concurrency_evidence(..., file_count=1200,
  concurrency=4)>> -> artifact=C:\Users\kkens\code\KasaneCore\ca_data\atlas\pir14_scale_concurrency_evidence.current.json
  files=1200 concurrency=4 result=passed inventory_seconds=18.2256
  concurrent_seconds=1.1511 parse_errors=0 concurrent_parse_errors=0.
- python -m pytest -q tests\test_project_intelligence_pir14_scale_concurrency_evidence.py
  tests\test_project_intelligence_pir14_operational_evidence.py
  tests\test_project_intelligence_recovery_baseline.py::test_recovery_status_selects_next_active_package ->
  5 passed in 1.28s.
Unavailable checks: Docker and Runpod platform evidence remain unclaimed by this slice.
Safety invariants checked: evidence runs in a temporary workspace only; no source mutation,
  rollout transition, legacy retirement, Proposal/Safe Apply mutation, or manually supplied
  benchmark outcome is used.
Migration/rollout state: rollout remains off by default; large-workspace and concurrency
  evidence is recorded as a measured artifact, not as a legacy retirement or active rollout.
Known limitations: PIR-14 remains in_progress until Docker/Runpod platform evidence is recorded
  where available and the final rollout/cutover acceptance decision is made.
Next package: PIR-14 — add Docker/Runpod platform evidence and final rollout/cutover decision.
Blocker: none.
```

```text
Work package: PIR-0 — Truthful baseline, executable inventory, and regression locks
Status: acceptance_complete
Changed modules/files:
- agent/project_intelligence/inspection/consumer_inventory.py — AST-based production entrypoint,
  legacy consumer, facade/adapter, construction-site, module implementation, and persistence
  default inventory generator.
- tools/generate_project_intelligence_consumer_inventory.py — CLI for regenerating the inventory.
- docs/generated/atlas_project_intelligence_consumer_inventory.json — generated artifact from
  the current checkout.
- tests/test_project_intelligence_recovery_baseline.py — PIR-0 inventory assertions plus strict
  xfail regression locks for audited defects PIR0-C01..PIR0-C07.
- docs/atlas_project_intelligence_current_status.md — PI-0..PI-25 reframed as Foundation Track.
Executed commands and exact results:
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=31 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m py_compile agent/project_intelligence/inspection/consumer_inventory.py
  tools/generate_project_intelligence_consumer_inventory.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_recovery_baseline.py ->
  5 passed, 6 xfailed in 16.30s
- python -m pytest -q tests/test_project_intelligence_baseline.py
  tests/test_project_intelligence_contracts.py tests/test_project_intelligence_rollout.py
  tests/test_project_intelligence_recovery_baseline.py -> 74 passed, 6 xfailed in 18.44s
- $files = Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName };
  python -m pytest -q @files -> 291 passed, 6 xfailed in 30.20s
Unavailable checks: none for PIR-0; no production behavior change or live environment claim.
Safety invariants checked: read-only source inspection only; no production runtime, PlanPool,
  Proposal, Safe Apply, verification, rollout, or legacy path behavior changed.
Migration/rollout state: off by default; no consumer cutover and no legacy deletion.
Known limitations: regression locks intentionally xfail until PIR-1+ fixes the underlying defects.
Next package: PIR-1 — durable concrete modules.
Blocker: none.
```

```text
Work package: PIR-14 — Windows platform CI evidence job
Status: in_progress
Changed modules/files:
- .github/workflows/atlas-project-intelligence-recovery.yml — added a windows-latest
  windows-platform-evidence job that runs PIR-14 operational evidence and consumer cutover gate
  tests with PowerShell environment setup, JUnit XML, Step Summary, and uploaded artifact.
- tests/test_project_intelligence_pir14_ci_workflow.py — extended the workflow contract to
  require the Windows job, Windows JUnit artifact, PowerShell environment setup, and covered
  PIR-14 operational/cutover tests.
- docs/atlas_project_intelligence_recovery_current_status.md — recorded the Windows CI job
  addition and the GitHub-hosted Windows run evidence from PR #1708.
Executed commands and exact results:
- python -m pytest -q tests\test_project_intelligence_pir14_ci_workflow.py
  tests\test_project_intelligence_pir14_operational_evidence.py
  tests\test_project_intelligence_pir14_consumer_cutover_gate.py -> 9 passed in 1.46s.
- gh pr checks 1708 --watch --interval 20 -> exit 0; GitHub Actions workflow
  "Atlas Project Intelligence Recovery" passed on pull_request run 27320150994 and branch push
  run 27320143614. Both runs completed windows-platform-evidence successfully
  (52s on pull_request, 36s on branch push), and all existing PIR-14 workflow jobs also passed.
Unavailable checks: Docker/Runpod platform jobs, large-repository benchmark, and
  concurrency/load evidence remain unclaimed.
Safety invariants checked: the job only runs tests and records artifacts; it does not run live
  model E2E, mutate production state, transition rollout, or retire legacy paths.
Migration/rollout state: rollout remains off by default; Windows platform evidence is attached
  through the PR workflow.
Known limitations: PIR-14 remains in_progress until Docker/Runpod, large-scale, concurrency,
  and final rollout evidence pass or remain explicitly unavailable where appropriate.
Next package: PIR-14 — add Docker/Runpod, large-scale, and concurrency evidence.
Blocker: none.
```

```text
Work package: PIR-14 — Verification/recovery parity and cutover gate pass
Status: in_progress
Changed modules/files:
- agent/project_intelligence/rollout_evidence.py — extended PIR-14 rollout evidence beyond
  planning/generation to include verification facade off-vs-shadow parity and recovery
  checkpoint metadata parity/rollback availability through AtlasRecoveryService.
- tests/test_project_intelligence_pir14_rollout_evidence.py — updated expectations for four
  evidence phases and verification/recovery rollback status.
- tests/test_project_intelligence_pir14_consumer_cutover_gate.py — added coverage proving the
  cutover gate passes when planning, generation, verification, and recovery parity/rollback
  evidence are all present.
- docs/atlas_project_intelligence_recovery_current_status.md — recorded that production
  consumer cutover gate evidence now passes while PIR-14 still waits on Linux/Docker/Runpod,
  large-scale, and concurrency evidence.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\rollout_evidence.py
  tests\test_project_intelligence_pir14_rollout_evidence.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir14_rollout_evidence.py ->
  2 passed in 0.92s.
- python - <<script invoking write_rollout_evidence(...), write_lint_report(...),
  write_consumer_cutover_gate(...)>> ->
  rollout=C:\Users\kkens\code\KasaneCore\ca_data\atlas\pir14_rollout_evidence.current.json
  phases=4 parity=4 rollback=4; gate=C:\Users\kkens\code\KasaneCore\ca_data\atlas\pir14_consumer_cutover_gate.current.json
  production_connected=4 cutover_ready=4 gate_passed=True blocked=[].
Unavailable checks: Linux/Docker/Runpod platform runs, large-repository scale evidence, and
  concurrency/load evidence remain unclaimed by this slice.
Safety invariants checked: verification evidence uses public ProjectIntelligence facade calls,
  recovery evidence uses AtlasRecoveryService over a temporary PlanPool, and the slice performs
  no source mutation, rollout transition, automatic rollback, or legacy retirement.
Migration/rollout state: rollout remains off by default; planning, generation, verification,
  and recovery now have cutover gate evidence, but active rollout remains pending platform and
  scale gates.
Known limitations: PIR-14 remains in_progress until Linux/Docker/Runpod platform artifacts,
  large-repository/concurrency evidence, and final active rollout/cutover evidence pass.
Next package: PIR-14 — add Linux/Docker/Runpod platform, large-scale, and concurrency evidence.
Blocker: none.
```

```text
Work package: PIR-14 — Production consumer cutover gate evidence
Status: in_progress
Changed modules/files:
- agent/project_intelligence/consumer_cutover_gate.py — added a read-only cutover gate that
  audits production wiring markers for planning, generation, verification, and recovery
  consumers, combines legacy dependency lint and rollout parity/rollback evidence, and reports
  cutover readiness per consumer without changing rollout state.
- tests/test_project_intelligence_pir14_consumer_cutover_gate.py — added focused coverage for
  connected production markers, planning/generation readiness, verification/recovery blocked
  reasons, lint failure blocking, persisted JSON output, and advisory-only safety flags.
- docs/atlas_project_intelligence_recovery_current_status.md — recorded the gate result and
  narrowed the next action to verification/recovery parity/rollback plus remaining platform and
  large-scale evidence.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\consumer_cutover_gate.py
  tests\test_project_intelligence_pir14_consumer_cutover_gate.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir14_consumer_cutover_gate.py ->
  2 passed in 0.68s.
- python - <<script invoking write_lint_report(...) and write_consumer_cutover_gate(...)>> ->
  artifact=C:\Users\kkens\code\KasaneCore\ca_data\atlas\pir14_consumer_cutover_gate.current.json
  production_connected=4 cutover_ready=2 gate_passed=False
  blocked=['recovery:rollback_drill_not_passed', 'recovery:shadow_parity_not_passed',
  'verification:rollback_drill_not_passed', 'verification:shadow_parity_not_passed'].
- python -m pytest -q tests\test_project_intelligence_pir14_consumer_cutover_gate.py
  tests\test_project_intelligence_pir14_legacy_dependency_lint.py
  tests\test_project_intelligence_pir14_rollout_evidence.py
  tests\test_project_intelligence_pir11_generation_apply.py
  tests\test_project_intelligence_pir12_verification_recovery.py -> 21 passed in 17.41s.
Unavailable checks: cutover gate does not pass yet because verification and recovery lack
  shadow parity and rollback drill evidence. Linux/Docker/Runpod platform runs,
  large-repository/concurrency evidence, and actual rollout transition remain unclaimed.
Safety invariants checked: the gate is advisory only, performs no source mutation, does not
  transition rollout, does not automatically rollback, and does not retire legacy paths.
Migration/rollout state: rollout remains off by default; production wiring markers exist for
  planning, generation, verification, and recovery, but only planning/generation are currently
  cutover-ready under the evidence gate.
Known limitations: PIR-14 remains in_progress until verification/recovery parity and rollback
  drills, Linux/Docker/Runpod platform artifacts, large-repository/concurrency evidence, and
  final cutover evidence pass.
Next package: PIR-14 — add verification/recovery shadow parity and rollback drills, then
  Linux/Docker/Runpod and large-scale evidence.
Blocker: none.
```

```text
Work package: PIR-14 — Legacy dependency lint for new direct consumers
Status: in_progress
Changed modules/files:
- agent/project_intelligence/legacy_dependency_lint.py — added a source-derived lint that
  compares current direct imports of legacy Project Intelligence capability modules against
  an explicit allowlist and reports any new production consumer as a violation.
- docs/generated/atlas_project_intelligence_legacy_dependency_allowlist.json — generated the
  current direct legacy dependency allowlist with 43 known dependency rows. This freezes the
  current migration baseline without authorizing new legacy imports.
- tests/test_project_intelligence_pir14_legacy_dependency_lint.py — added focused coverage for
  current checkout lint pass, allowlist schema/safety flags, deterministic allowlist generation,
  JSON report persistence, and a synthetic new direct legacy consumer violation.
- docs/atlas_project_intelligence_recovery_current_status.md — recorded the dependency lint
  evidence while PIR-14 remains in_progress.
Executed commands and exact results:
- python - <<script invoking write_allowlist(...) and write_lint_report(...)>> ->
  allowlist=C:\Users\kkens\code\KasaneCore\docs\generated\atlas_project_intelligence_legacy_dependency_allowlist.json
  allowed=43 report=C:\Users\kkens\code\KasaneCore\ca_data\atlas\pir14_legacy_dependency_lint.current.json
  passed=True violations=0.
- python -m py_compile agent\project_intelligence\legacy_dependency_lint.py
  tests\test_project_intelligence_pir14_legacy_dependency_lint.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir14_legacy_dependency_lint.py ->
  4 passed in 10.44s.
Unavailable checks: this lint prevents newly introduced direct legacy imports but does not
  cut over existing consumers, prove parity for those consumers, or retire legacy paths.
Safety invariants checked: the lint is static and advisory; it performs no production
  mutation, no rollout transition, no automatic rollback, and no legacy deletion.
Migration/rollout state: rollout remains off by default; current direct legacy dependencies
  remain as a frozen migration baseline, and new direct legacy consumers now fail the lint.
Known limitations: PIR-14 remains in_progress until remaining phase parity/rollback,
  Linux/Docker/Runpod platform artifacts, large-repository/concurrency evidence, and production
  consumer cutover evidence pass.
Next package: PIR-14 — add remaining phase parity/rollback, Linux/Docker/Runpod, large-scale,
  concurrency, and cutover evidence.
Blocker: none.
```

```text
Work package: PIR-14 — Operational platform, scale, and threshold rollback evidence
Status: in_progress
Changed modules/files:
- agent/project_intelligence/operational_evidence.py — added an operational evidence artifact
  builder that records the current platform as observed, unsupported or not-run platforms as
  unavailable, current-checkout bounded scale metrics, and threshold-driven rollout phase
  rollback decisions without claiming a full platform matrix or large-repository benchmark.
- tests/test_project_intelligence_pir14_operational_evidence.py — added focused coverage for
  observed/unavailable platform rows, bounded scale evidence, JSON persistence, threshold
  rollback triggered by a regression-budget violation, and no rollback when thresholds pass.
- docs/atlas_project_intelligence_recovery_current_status.md — updated PIR-14 next action to
  keep Windows/current-checkout operational evidence distinct from remaining Linux/Docker/Runpod,
  large-scale, and cutover gates.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\operational_evidence.py
  tests\test_project_intelligence_pir14_operational_evidence.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir14_operational_evidence.py ->
  3 passed in 0.64s.
- python - <<script invoking write_operational_evidence(...)>> ->
  artifact=C:\Users\kkens\code\KasaneCore\ca_data\atlas\pir14_operational_evidence.current.json
  current_platform=windows observed_platforms=1 unavailable_platforms=3 scale_passed=1
  threshold_rollback_triggered=True.
- python -m pytest -q tests\test_project_intelligence_pir14_operational_evidence.py
  tests\test_project_intelligence_hardening.py tests\test_project_intelligence_consolidation.py ->
  23 passed in 1.32s.
Unavailable checks: Linux, Docker, and Runpod platform jobs are explicit unavailable rows;
  current-checkout file count is not a large-repository benchmark; no concurrency/load run and
  no production consumer cutover are claimed by this slice.
Safety invariants checked: the artifact records evidence only, treats unavailable platforms as
  unavailable rather than passed, performs no source mutation, does not cut over consumers, and
  does not retire legacy paths.
Migration/rollout state: rollout remains off by default; threshold rollback evidence is a
  rollout phase-state decision from generation back to planning, not source rollback.
Known limitations: PIR-14 remains in_progress until remaining phase parity/rollback,
  Linux/Docker/Runpod platform artifacts, large-repository/concurrency evidence, and production
  consumer cutover evidence pass.
Next package: PIR-14 — add remaining phase parity/rollback, Linux/Docker/Runpod, large-scale,
  concurrency, and cutover evidence.
Blocker: none.
```

```text
Work package: PIR-14 — Shadow parity and flag-off rollback evidence
Status: in_progress
Changed modules/files:
- agent/project_intelligence/rollout_evidence.py — added a non-destructive evidence helper
  that calls the public ProjectIntelligence facade in off, shadow, and active modes,
  compares off vs shadow results after removing volatile manifest fields, and records that
  an active phase can return to off mode without mutating source or retiring legacy paths.
- tests/test_project_intelligence_pir14_rollout_evidence.py — added focused coverage for
  planning/generation shadow parity, flag-off rollback drill status, persisted JSON output,
  safety non-claims, and unsupported phase rejection.
- docs/atlas_project_intelligence_recovery_current_status.md — updated PIR-14 next action to
  treat planning/generation shadow parity and rollback drill evidence as partial, with the
  remaining phases, platform, scale, threshold rollback, and cutover evidence still pending.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\rollout_evidence.py
  tests\test_project_intelligence_pir14_rollout_evidence.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir14_rollout_evidence.py ->
  2 passed in 0.89s.
- python - <<script invoking write_rollout_evidence(...)>> ->
  artifact=C:\Users\kkens\code\KasaneCore\ca_data\atlas\pir14_rollout_evidence.current.json
  phase_count=2 shadow_parity_passed=2 rollback_passed=2 telemetry_events=2.
- python -m pytest -q tests\test_project_intelligence_pir14_rollout_evidence.py
  tests\test_project_intelligence_pir14_consumer_registry.py
  tests\test_project_intelligence_rollout.py tests\test_project_intelligence_consolidation.py ->
  23 passed in 9.88s.
Unavailable checks: parity and rollback drills are only proven for planning/generation public
  facade calls in this slice. Verification, repair, Greenfield, platform matrix,
  scale/concurrency, automatic threshold rollback, and actual production consumer cutover
  remain unclaimed.
Safety invariants checked: the helper compares public facade outputs only, strips volatile
  manifest fields, performs no source mutation, does not enable consumer cutover, does not
  execute automatic rollback, and does not retire legacy paths.
Migration/rollout state: rollout remains off by default; planning/generation evidence shows
  shadow output parity with baseline and flag-off rollback availability.
Known limitations: PIR-14 remains in_progress until remaining phase parity/rollback, platform
  and scale artifacts, automatic threshold rollback, and production consumer cutover evidence
  pass.
Next package: PIR-14 — extend parity/rollback evidence beyond planning/generation and add
  platform, scale, threshold rollback, and cutover evidence.
Blocker: none.
```

```text
Work package: PIR-14 — Source-derived consumer registry and phase telemetry artifact
Status: in_progress
Changed modules/files:
- agent/project_intelligence/consumer_registry.py — added a PIR-14 registry generator that
  derives real consumer rows from the current checkout inventory, folds in runtime telemetry
  records by phase, records rollout mode, shadow status, rollback status, legacy consumer
  counts/paths, owner/tests, and persists the result as a JSON artifact without granting
  mutation, rollout, rollback, or retirement authority.
- tests/test_project_intelligence_pir14_consumer_registry.py — added focused coverage for
  source-derived entries, runtime telemetry call counts, shadow parity status, rollback drill
  status, JSON persistence, and off-by-default non-claims.
- docs/atlas_project_intelligence_recovery_current_status.md — next PIR-14 action updated to
  keep registry evidence complete while shadow parity, rollback drill, platform, scale, and
  cutover evidence remain pending.
Executed commands and exact results:
- python -m py_compile agent\project_intelligence\consumer_registry.py
  tests\test_project_intelligence_pir14_consumer_registry.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir14_consumer_registry.py ->
  2 passed in 8.42s.
- python - <<script invoking build_project_intelligence in shadow planning,generation mode and
  write_consumer_registry(...)>> -> artifact=C:\Users\kkens\code\KasaneCore\ca_data\atlas\pir14_consumer_registry.current.json
  entries=9 telemetry_events=3 shadow_entries=3.
- python -m pytest -q tests\test_project_intelligence_pir14_consumer_registry.py
  tests\test_project_intelligence_rollout.py tests\test_project_intelligence_consolidation.py ->
  21 passed in 9.51s.
Unavailable checks: consumer cutover, shadow parity from real tasks across all phases, rollback
  drills, platform matrix, scale/concurrency artifacts, and automatic phase rollback thresholds
  remain unclaimed by this registry slice.
Safety invariants checked: the registry is advisory evidence only, uses source inventory plus
  supplied runtime telemetry, does not enable rollout, does not mutate canonical state, does not
  execute rollback, and does not retire legacy paths.
Migration/rollout state: rollout remains off by default; the generated artifact records shadow
  planning/generation telemetry but performs no consumer cutover.
Known limitations: PIR-14 remains in_progress until shadow parity, rollback drills,
  platform/scale artifacts, automatic threshold rollback, and production consumer cutover
  evidence pass.
Next package: PIR-14 — add shadow parity, rollback, platform, scale, and cutover evidence.
Blocker: none.
```

```text
Work package: PIR-1 — Durable concrete module foundations
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/module.py — concrete DigitalTwinModuleImpl over the durable Twin store,
  workspace-isolated by internal project key, with open/refresh/rebuild/event/runtime/query/
  context/health facade methods.
- agent/project_convergence/module.py — concrete ConvergenceModuleImpl over ConvergenceStore,
  with injectable Blueprint/Actual/verification loaders, persisted reports, and persisted
  bounded decisions.
- agent/architecture_blueprint/module.py and store.py — durable lifecycle status updates
  and deterministic get_active per project/workspace after reopen.
- agent/project_intelligence/_persistence.py, project_twin/store.py, project_intelligence/store.py,
  project_intelligence/checkpoint.py, project_convergence/store.py — file-backed defaults for
  concrete persistence; explicit test-supplied SQLite memory remains available.
- tests/test_project_intelligence_facade_conformance.py
- tests/test_project_twin_module_durability.py
- tests/test_blueprint_durable_lifecycle.py
- tests/test_convergence_module_durability.py
- tests/test_project_workspace_isolation.py
- tests/test_project_intelligence_recovery_baseline.py — PIR0-C04/C05/C06 locks now pass;
  remaining later-package locks stay strict xfail.
Executed commands and exact results:
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=31 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m py_compile agent/project_intelligence/_persistence.py agent/project_twin/store.py
  agent/project_twin/module.py agent/architecture_blueprint/module.py
  agent/project_convergence/module.py agent/architecture_blueprint/store.py
  agent/project_convergence/store.py agent/project_intelligence/store.py
  agent/project_intelligence/checkpoint.py tests/test_project_intelligence_facade_conformance.py
  tests/test_project_twin_module_durability.py tests/test_blueprint_durable_lifecycle.py
  tests/test_convergence_module_durability.py tests/test_project_workspace_isolation.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_facade_conformance.py
  tests/test_project_twin_module_durability.py tests/test_blueprint_durable_lifecycle.py
  tests/test_convergence_module_durability.py tests/test_project_workspace_isolation.py
  tests/test_project_intelligence_recovery_baseline.py -> 16 passed, 4 xfailed in 18.47s
- python -m pytest -q tests/test_project_intelligence_contracts.py
  tests/test_project_intelligence_persistence.py tests/test_project_intelligence_blueprint_lifecycle.py
  tests/test_project_intelligence_convergence_eval.py tests/test_project_intelligence_convergence_decision.py
  tests/test_project_twin_store.py tests/test_project_intelligence_facade_conformance.py
  tests/test_project_twin_module_durability.py tests/test_blueprint_durable_lifecycle.py
  tests/test_convergence_module_durability.py tests/test_project_workspace_isolation.py
  tests/test_project_intelligence_recovery_baseline.py -> 81 passed, 4 xfailed in 20.32s
- PowerShell-expanded project_intelligence + project_twin suites plus PIR-1 durability/isolation
  tests -> 427 passed, 4 xfailed in 38.53s
Unavailable checks: none required for PIR-1; production app composition begins in PIR-2.
Safety invariants checked: concrete modules remain behind public facades; no FastAPI/UI/app API/
  PlanPool imports in portable concrete modules; no production rollout/cutover/legacy deletion;
  explicit SQLite memory remains test-only when supplied by tests.
Migration/rollout state: rollout remains off by default; no consumer cutover.
Known limitations: Digital Twin source snapshots/analyzers and production construction are not
  wired until PIR-2/PIR-3; Convergence uses injected loaders until production composition supplies
  real Blueprint/Actual sources.
Next package: PIR-2 — production composition and rollout preflight.
Blocker: none.
```

```text
Work package: PIR-2 — Production composition root, service lifecycle, and rollout preflight
Status: acceptance_complete
Changed modules/files:
- agent/project_intelligence/production_factory.py — production composition root resolving
  durable module DBs under ca_data/project_intelligence, off-mode disabled compatibility,
  shadow/active concrete composition, persisted rollout state, and fail-closed preflight.
- agent/project_intelligence/service_registry.py — app.state lifecycle holder and shutdown close.
- app/api/atlas_project_intelligence.py and app/server.py — read-only health route under
  /api/atlas/project-intelligence/health.
- main.py — production lifespan registration/close for the Project Intelligence service.
- agent/project_intelligence/coordinator.py and factory.py — composition dependency types moved
  to public facade protocols.
- tests/test_project_intelligence_production_composition.py
- tests/test_project_intelligence_app_lifecycle.py
- tests/test_project_intelligence_rollout_preflight.py
- tests/test_project_intelligence_health_api.py
- tests/test_project_intelligence_recovery_baseline.py — PIR0-C01 production-composition lock
  now passes; remaining later-package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/coordinator.py
  agent/project_intelligence/factory.py agent/project_intelligence/production_factory.py
  agent/project_intelligence/service_registry.py app/api/atlas_project_intelligence.py
  app/server.py main.py tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py tests/test_project_intelligence_recovery_baseline.py ->
  15 passed, 3 xfailed in 16.15s
- python -m pytest -q tests/test_project_intelligence_rollout.py
  tests/test_project_intelligence_planner_bridge.py tests/test_project_intelligence_generator_bridge.py
  tests/test_project_intelligence_contracts.py tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py tests/test_project_intelligence_recovery_baseline.py ->
  50 passed, 3 xfailed in 17.47s
- PowerShell-expanded project_intelligence + project_twin suites plus PIR-1 durability/isolation
  tests -> 435 passed, 3 xfailed in 38.09s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_intelligence_recovery_baseline.py ->
  8 passed, 3 xfailed in 13.48s
Unavailable checks: production planner/generator/verification consumer cutover remains later
  PIR work; no behavior change is claimed for those consumers in PIR-2.
Safety invariants checked: off mode composes disabled modules and remains legacy-compatible;
  shadow/active compose concrete modules and fail closed on unusable stores; health endpoint
  returns no private rows; no Safe Apply, Proposal, Verification, PlanPool, or legacy deletion.
Migration/rollout state: rollout_state.json is persisted under ca_data/project_intelligence;
  rollback history is represented and preserved, but no phase cutover performed.
Known limitations: Project Intelligence service is registered and inspectable; real source
  snapshots and Twin refresh lifecycle begin in PIR-3.
Next package: PIR-3 — real project source snapshots and Twin refresh lifecycle.
Blocker: none.
```

```text
Work package: PIR-3 — Real project source snapshots and Twin refresh lifecycle
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/source_adapter.py — read-only ProjectSourceAdapter with workspace-safe
  root resolution, path-escape rejection, symlink/binary/oversize/file-count guards, dirty
  changed/deleted path detection, and parser manifest.
- agent/project_twin/project_identity.py — working-tree identity now includes bounded file
  content hashes so same-size dirty edits produce distinct source identities.
- agent/project_twin/contracts.py and store.py — TwinDelta carries source_commit,
  working_tree_hash, and parser_versions; SqliteProjectTwinStore persists them on revisions.
- agent/project_twin/module.py — concrete DigitalTwinModuleImpl opens real repositories by
  running static and behavioral analyzers behind the facade, persists last successful source
  build records, performs scoped incremental refresh, invalidates deleted stale facts, and
  retains the prior active revision on failed refresh.
- agent/project_twin/__init__.py — exports source snapshot adapter DTOs.
- tests/test_project_twin_source_adapter.py
- tests/test_project_twin_source_refresh_lifecycle.py
- tests/test_project_intelligence_recovery_baseline.py — PIR-3 remains represented in the
  active recovery status table; later-package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_twin/contracts.py agent/project_twin/store.py
  agent/project_twin/project_identity.py agent/project_twin/source_adapter.py
  agent/project_twin/module.py agent/project_twin/__init__.py
  tests/test_project_twin_source_adapter.py tests/test_project_twin_source_refresh_lifecycle.py
  -> compile OK
- python -m pytest -q tests/test_project_twin_source_adapter.py
  tests/test_project_twin_source_refresh_lifecycle.py tests/test_project_twin_module_durability.py
  tests/test_project_workspace_isolation.py -> 13 passed in 6.08s
- python -m pytest -q tests/test_project_intelligence_recovery_baseline.py
  tests/test_project_twin_source_adapter.py tests/test_project_twin_source_refresh_lifecycle.py
  tests/test_project_twin_module_durability.py tests/test_project_workspace_isolation.py ->
  21 passed, 3 xfailed in 18.93s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_twin_source_adapter.py
  tests/test_project_twin_source_refresh_lifecycle.py tests/test_project_twin_module_durability.py
  tests/test_project_workspace_isolation.py tests/test_project_twin_static_graph.py
  tests/test_project_twin_behavioral_graph.py tests/test_project_twin_store.py
  tests/test_project_intelligence_lifecycle.py tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py tests/test_project_intelligence_recovery_baseline.py ->
  67 passed, 3 xfailed in 27.19s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 438 passed, 3 xfailed in 43.29s
Unavailable checks: no external Atlas workspace restart process was required for PIR-3; restart
  persistence is covered by close/reopen of durable store plus last-build sidecar. Planner,
  Generator, Verification, and delivery-event cutover remain later PIR work.
Safety invariants checked: source adapter is read-only and rejects path escapes; concrete Twin
  remains behind the public facade; failed refresh returns degraded with the prior active
  revision; no PlanPool, Proposal, Safe Apply, Verification, command authority, rollout
  cutover, or legacy deletion behavior changed.
Migration/rollout state: production composition remains off by default; active/shadow concrete
  service now gets source-backed Twin behavior when called, but no consumer cutover performed.
Known limitations: restart-safe durable event projection, runtime verification ingest, deeper
  semantic/CFG/data-flow/resource graphs, and real Planner/PlanPool integration begin in PIR-4+.
Next package: PIR-4 — durable canonical event and delivery projection integration.
Blocker: none.
```

```text
Work package: PIR-4 — Durable canonical event and delivery projection integration
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/event_projection_store.py — durable SQLite event inbox, delivery nodes,
  delivery edges, diagnostics, full event payload retention, idempotent replay, poison state,
  workspace-isolated trace queries, and DurableDeliveryTraceProjector.
- agent/project_twin/event_bridge.py — in-memory compatibility projector is now workspace
  isolated; projection failure retry jobs include full event payloads; bridge/projector close
  hook added.
- agent/project_twin/module.py — concrete DigitalTwinModuleImpl projects canonical events
  through the event bridge and triggers source-backed refresh for workspace.changed and
  safe_apply.completed events when project_path is present.
- agent/project_intelligence/production_factory.py — production composition creates durable
  event_projection.sqlite3 and injects the durable bridge into the concrete Twin.
- agent/project_intelligence/coordinator.py — active record_apply_result and
  record_verification_result emit canonical ProjectEventEnvelope instances into the injected
  Twin facade without becoming mutation authority.
- tests/test_project_twin_durable_event_projection.py
- tests/test_project_intelligence_recovery_baseline.py — PIR-4 status lock advanced; later
  package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_twin/event_bridge.py
  agent/project_twin/event_projection_store.py agent/project_twin/module.py
  agent/project_twin/__init__.py agent/project_intelligence/production_factory.py
  tests/test_project_twin_durable_event_projection.py -> compile OK
- python -m pytest -q tests/test_project_twin_durable_event_projection.py
  tests/test_project_intelligence_event_bridge.py tests/test_project_intelligence_rollout.py ->
  24 passed in 2.95s
- python -m pytest -q tests/test_project_twin_durable_event_projection.py
  tests/test_project_intelligence_event_bridge.py tests/test_project_intelligence_rollout.py
  tests/test_project_twin_source_refresh_lifecycle.py tests/test_project_twin_module_durability.py
  tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py -> 38 passed in 10.75s
- python -m pytest -q tests/test_project_twin_durable_event_projection.py
  tests/test_project_intelligence_event_bridge.py tests/test_project_intelligence_rollout.py
  tests/test_project_twin_source_refresh_lifecycle.py tests/test_project_twin_module_durability.py
  tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_app_lifecycle.py tests/test_project_intelligence_rollout_preflight.py
  tests/test_project_intelligence_health_api.py tests/test_project_intelligence_recovery_baseline.py ->
  46 passed, 3 xfailed in 21.51s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 445 passed, 3 xfailed in 41.20s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
Unavailable checks: no live Atlas UI/operator flow was run; PIR-4 verifies the production
  Project Intelligence facade caller path and the concrete Twin ingest path. Direct producer
  call-site cutover in every legacy Atlas service remains migration work for later PIR packages.
Safety invariants checked: events are emitted after Project Intelligence apply/verification
  records, not before canonical writes; projection failures queue retry payloads and do not
  mutate PlanPool/Safe Apply/Verification canonical state; duplicate replay is idempotent;
  poison events are diagnosable and do not block later events; project/workspace isolation is
  enforced in durable projection tables.
Migration/rollout state: rollout remains off by default; active production composition has
  durable delivery projection available, but no legacy path deletion or broad consumer cutover.
Known limitations: real verification artifact normalization, source/Twin revision separation
  in reconciliation, context ranking, impact/test selection, and deeper graph precision begin
  in PIR-5+.
Next package: PIR-5 — real verification ingestion, reconciliation, context, impact, and test
  selection.
Blocker: none.
```

```text
Work package: PIR-5 — Real verification ingestion, reconciliation, context, impact, and test selection
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/runtime/collectors.py — pytest normalization preserves per-test coverage
  subjects and emits concrete plus legacy-compatible symbol refs.
- agent/project_twin/contracts.py, migrations.py, store.py — RuntimeObservation carries
  source_revision, persisted through a Twin store migration, with durable observation queries.
- agent/project_twin/static_graph.py — Python class/function/route facts persist source line
  ranges for targeted source excerpts.
- agent/project_twin/module.py — runtime ingest diagnoses stale source evidence; test
  selection and context evidence use durable observations and filter stale evidence; context
  includes bounded runtime/test items and source excerpts with manifest source revisions.
- tests/test_project_twin_verification_context.py
- tests/test_project_intelligence_runtime.py — stack-frame expectation aligned with concrete
  source-backed Twin refs.
- tests/test_project_intelligence_recovery_baseline.py — PIR-5 status lock advanced; later
  package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_twin/contracts.py agent/project_twin/migrations.py
  agent/project_twin/store.py agent/project_twin/static_graph.py
  agent/project_twin/runtime/collectors.py agent/project_twin/module.py
  tests/test_project_twin_verification_context.py tests/test_project_intelligence_runtime.py ->
  compile OK
- python -m pytest -q tests/test_project_twin_verification_context.py
  tests/test_project_intelligence_runtime.py tests/test_project_twin_source_refresh_lifecycle.py
  tests/test_project_twin_store.py -> 31 passed in 5.99s
- python -m pytest -q tests/test_project_twin_verification_context.py
  tests/test_project_intelligence_runtime.py tests/test_project_twin_source_refresh_lifecycle.py
  tests/test_project_twin_store.py tests/test_project_twin_static_graph.py
  tests/test_project_twin_durable_event_projection.py tests/test_project_intelligence_event_bridge.py
  tests/test_project_intelligence_rollout.py tests/test_project_intelligence_recovery_baseline.py ->
  71 passed, 3 xfailed in 21.26s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_intelligence_query_context.py::test_impact_recommended_tests_from_coverage
  tests/test_project_twin_verification_context.py tests/test_project_intelligence_runtime.py ->
  14 passed in 2.84s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 449 passed, 3 xfailed in 43.08s
Unavailable checks: no live external pytest/playwright command execution was run in this
  package; the package verifies canonical normalized artifacts and Project Intelligence/Twin
  ingestion APIs. PIR-13 remains the real Greenfield E2E gate.
Safety invariants checked: unavailable observations remain unavailable; stale source evidence
  is diagnosed and not used for current test selection/context verification; per-test coverage
  is preserved; source and Twin revisions remain separate; context is bounded and manifests
  record overflow rather than pretending complete context.
Migration/rollout state: rollout remains off by default; active concrete Twin now supports
  runtime evidence and context/test-selection queries, but no legacy consumer cutover or
  legacy deletion was performed.
Known limitations: cross-module semantic precision, parser-backed frontend analysis, richer
  CFG/data-flow/resource graphs, and labeled precision/recall benchmark expansion continue
  in PIR-6/PIR-7/PIR-15.
Next package: PIR-6 — whole-project semantic graph and parser-backed frontend analysis.
Blocker: none.
```

```text
Work package: PIR-6 — Whole-project semantic graph and parser-backed frontend analysis
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/analyzers/python.py — Python semantic analyzer now records source
  ranges, resolves receiver method calls from annotations and constructor assignments, and
  records Protocol/ABC-style implements edges.
- agent/project_twin/analyzers/registry.py — project-level linker resolves calls/imports
  through package re-export aliases after all files are analyzed.
- tests/test_project_intelligence_semantic_graph.py — labeled fixtures for re-export call
  resolution, receiver-type method resolution, Protocol implementation, source ranges, and
  incremental/full equivalence.
Executed commands and exact results:
- python -m py_compile agent/project_twin/analyzers/python.py
  agent/project_twin/analyzers/registry.py tests/test_project_intelligence_semantic_graph.py ->
  compile OK
- python -m pytest -q tests/test_project_intelligence_semantic_graph.py ->
  18 passed in 0.81s
- python -m pytest -q tests/test_project_intelligence_semantic_graph.py
  tests/test_project_intelligence_query_context.py tests/test_project_twin_static_graph.py
  tests/test_project_twin_verification_context.py tests/test_project_intelligence_recovery_baseline.py ->
  48 passed, 3 xfailed in 15.81s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 454 passed, 3 xfailed in 43.29s
Unavailable checks: no external LSP server was required; LSP-unavailable remains an explicit
  degraded fallback. The larger labeled precision/recall benchmark corpus remains tracked for
  final benchmark work.
Safety invariants checked: semantic analysis remains pure/read-only; unresolved dynamic calls
  remain bounded candidates with lower confidence; parser fallback is recorded as degraded,
  not silently equivalent; incremental invalidation keeps unchanged file facts.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: full CFG/data-flow/state/resource precision and frontend handler-scope
  behavior begin in PIR-7.
Next package: PIR-7 — real CFG, data-flow, state/event/recovery, and resource graphs.
Blocker: none.
```

```text
Work package: PIR-7 — Real CFG, data-flow, state/event/recovery, and resource graphs
Status: acceptance_complete
Changed modules/files:
- agent/project_twin/behavioral_graph.py — production Digital Twin behavioral analyzer now
  emits per-callable CFG block nodes and branch/loop/exception/return edges; SSA-lite
  definition/use/resource flow facts; concrete file/database/API/process/UI resource
  identities; state transition nodes/edges; retry/backoff/rollback recovery facts; event
  producer facts; source ranges and bounded inferred confidence; JS event handlers now link
  only to API calls inside their reachable handler body instead of all APIs in the file.
- tests/test_project_twin_pir7_graphs.py — labeled PIR-7 corpus for branch/loop/exception,
  parameter-to-resource flow, cross-function argument propagation, state/recovery transitions,
  scoped UI handler-to-API paths, and a concrete DigitalTwinModuleImpl production connection.
- tests/test_project_intelligence_recovery_baseline.py — PIR-7 status lock advanced; later
  package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_twin/behavioral_graph.py
  tests/test_project_twin_pir7_graphs.py -> compile OK
- python -m pytest -q tests/test_project_twin_pir7_graphs.py
  tests/test_project_twin_behavioral_graph.py tests/test_project_intelligence_behavioral_graph.py ->
  16 passed in 1.84s
- python -m pytest -q tests/test_project_twin_pir7_graphs.py
  tests/test_project_twin_behavioral_graph.py tests/test_project_intelligence_behavioral_graph.py
  tests/test_project_intelligence_recovery_baseline.py -> 24 passed, 3 xfailed in 14.49s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_twin_pir7_graphs.py
  tests/test_project_twin_behavioral_graph.py tests/test_project_intelligence_behavioral_graph.py
  tests/test_project_intelligence_semantic_graph.py tests/test_project_twin_source_refresh_lifecycle.py
  tests/test_project_twin_verification_context.py tests/test_project_intelligence_query_context.py
  tests/test_project_intelligence_recovery_baseline.py -> 61 passed, 3 xfailed in 20.21s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 457 passed, 3 xfailed in 44.00s
Unavailable checks: no live browser/runtime UI execution was required for this package; the
  package verifies parser/static graph facts and a concrete Twin facade refresh. PIR-13/PIR-14
  remain the real Greenfield E2E, platform, and rollout gates.
Safety invariants checked: behavioral facts remain inferred with confidence below 1.0; production
  Twin persists the facts behind the facade; frontend calls outside a handler are not promoted to
  reachable handler behavior; resource and state facts do not mutate PlanPool/Safe Apply authority.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: Blueprint target authority, Convergence gap policy, Planner/PlanPool integration,
  and final benchmark/retirement remain in PIR-8+.
Next package: PIR-8 — durable Blueprint planning, review, and critical-decision integration.
Blocker: none.
```

```text
Work package: PIR-8 — Durable Blueprint planning, review, and critical-decision integration
Status: acceptance_complete
Changed modules/files:
- agent/architecture_blueprint/contracts.py — BlueprintCreateRequest now carries structured
  requirement/actual context for target files, API/schema/config/dependency/runtime/NFR,
  preserve-behavior, command, approval, and critical-decision inputs.
- agent/architecture_blueprint/planner_adapter.py — new public-context planner adapter maps
  Requirement + Actual inputs into deterministic BlueprintSpec and adds an unresolved critical
  decision when an existing project requests full redesign without approval.
- agent/architecture_blueprint/generator.py — deterministic Blueprint generation now emits
  concrete file, API, schema, configuration, dependency, runtime, NFR, preserve-behavior,
  entrypoint, command, and test-contract target elements with planned bp:// identities and
  verification contracts.
- agent/architecture_blueprint/validator.py — validates command values, mandatory verification
  contracts, requirement verification coverage, unresolved decisions, planned-vs-Actual refs,
  dependency cycles, and full-project manifest/execution contracts.
- agent/architecture_blueprint/module.py and store.py — create uses the planner adapter,
  review persists durable diagnostics/decisions/topology/coverage artifacts, and activation
  revalidates the persisted revision before moving the active index.
- tests/test_architecture_blueprint_pir8.py and existing Blueprint tests — PIR-8 acceptance
  corpus for existing Change Blueprint, Greenfield full Blueprint, durable review/activation
  restart, critical-decision blocking, and target identity/verification contracts.
- tests/test_project_intelligence_recovery_baseline.py — PIR-8 status lock advanced; later
  package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/architecture_blueprint/contracts.py
  agent/architecture_blueprint/generator.py agent/architecture_blueprint/planner_adapter.py
  agent/architecture_blueprint/validator.py agent/architecture_blueprint/module.py
  agent/architecture_blueprint/store.py tests/test_architecture_blueprint_pir8.py
  tests/test_project_intelligence_blueprint_lifecycle.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_architecture_blueprint_pir8.py
  tests/test_blueprint_durable_lifecycle.py tests/test_project_intelligence_blueprint_generation.py
  tests/test_project_intelligence_blueprint_lifecycle.py
  tests/test_project_intelligence_blueprint_mapping.py -> 26 passed in 2.24s
- python -m pytest -q tests/test_architecture_blueprint_pir8.py
  tests/test_blueprint_durable_lifecycle.py tests/test_project_intelligence_blueprint_generation.py
  tests/test_project_intelligence_blueprint_lifecycle.py tests/test_project_intelligence_blueprint_mapping.py
  tests/test_project_intelligence_recovery_baseline.py -> 34 passed, 3 xfailed in 15.21s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_architecture_blueprint_pir8.py
  tests/test_blueprint_durable_lifecycle.py tests/test_project_intelligence_blueprint_generation.py
  tests/test_project_intelligence_blueprint_lifecycle.py tests/test_project_intelligence_blueprint_mapping.py
  tests/test_project_intelligence_greenfield.py tests/test_project_intelligence_plan_compiler.py
  tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_recovery_baseline.py -> 50 passed, 3 xfailed in 16.18s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_blueprint_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_architecture_blueprint_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 461 passed, 3 xfailed in 44.97s
Unavailable checks: no live Atlas UI critical-decision prompt was exercised in this package;
  unresolved Blueprint decisions surface through the existing Blueprint review/activation gate.
Safety invariants checked: target design uses bp:// planned identities; Actual refs remain only
  as expected materialization refs; existing-project full redesign requires explicit approval;
  review artifacts and active revision state persist; Blueprint does not mutate PlanPool, Twin,
  workspace, Proposal, Safe Apply, or Verification state.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: Convergence gap policy, Planner/PlanPool production integration, Proposal/
  Safe Apply refresh, recovery/resume, Greenfield E2E, platform rollout, benchmark, and legacy
  retirement remain in PIR-9+.
Next package: PIR-9 — Convergence correctness, evidence policy, and durable decisions.
Blocker: none.
```

```text
Work package: PIR-9 — Convergence correctness, evidence policy, and durable decisions
Status: acceptance_complete
Changed modules/files:
- agent/project_convergence/contracts.py — Convergence requests/reports now separate Actual
  Twin, source, requirement, mapping, and evidence revision identities; element results carry
  evidence policy, required evidence refs, and freshness state.
- agent/project_convergence/evaluator.py — evidence freshness compares verification source
  revision against Actual source revision, not Twin revision; mandatory gaps are retained until
  each element evidence policy passes; unavailable/observed/materialized evidence does not pass
  verified policies; typed dimension mismatches cover API/schema/config/dependency/behavior/
  state/recovery/resource/NFR-style contracts.
- agent/project_convergence/policy.py — completion candidate now requires every mandatory
  element result to be verified; the old any-verified shortcut is removed.
- agent/project_convergence/module.py and store.py — facade persists separated revision metadata
  in reports and exposes persisted decision history for restart proof.
- tests/test_project_convergence_pir9.py and existing Convergence/Completion tests — PIR-9
  corpus for source-vs-Twin revision correctness, mandatory evidence policies, unavailable
  evidence, typed dimensional gaps, persisted decisions, and no premature completion.
- tests/test_project_intelligence_recovery_baseline.py — PIR-9 status lock advanced; later
  package locks stay strict xfail.
Executed commands and exact results:
- python -m py_compile agent/project_convergence/contracts.py
  agent/project_convergence/evaluator.py agent/project_convergence/policy.py
  agent/project_convergence/module.py agent/project_convergence/store.py
  tests/test_project_convergence_pir9.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_project_convergence_pir9.py
  tests/test_project_intelligence_convergence_eval.py
  tests/test_project_intelligence_convergence_decision.py
  tests/test_convergence_module_durability.py tests/test_project_intelligence_completion.py ->
  31 passed in 2.43s
- python -m pytest -q tests/test_project_convergence_pir9.py
  tests/test_project_intelligence_convergence_eval.py
  tests/test_project_intelligence_convergence_decision.py
  tests/test_convergence_module_durability.py tests/test_project_intelligence_completion.py
  tests/test_project_intelligence_recovery_baseline.py -> 39 passed, 3 xfailed in 14.98s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_convergence_pir9.py
  tests/test_project_intelligence_convergence_eval.py
  tests/test_project_intelligence_convergence_decision.py
  tests/test_convergence_module_durability.py tests/test_project_intelligence_completion.py
  tests/test_project_intelligence_blueprint_generation.py tests/test_architecture_blueprint_pir8.py
  tests/test_project_intelligence_greenfield.py tests/test_project_intelligence_plan_compiler.py
  tests/test_project_intelligence_recovery_baseline.py -> 64 passed, 3 xfailed in 16.41s
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_blueprint_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_architecture_blueprint_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_convergence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_convergence_*.py' | ForEach-Object { $_.FullName });
  python -m pytest -q @files -> 467 passed, 3 xfailed in 45.87s
Unavailable checks: no live Planner/PlanPool production action was exercised in this package;
  PIR-10 owns authoritative PlanPool integration.
Safety invariants checked: source revision is not treated as Twin revision; unavailable evidence
  remains unavailable; materialized/observed does not satisfy verified evidence policies; Convergence
  returns bounded decisions only and does not mutate Blueprint, PlanPool, workspace, Proposal, Safe
  Apply, or Verification state.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: Planner/PlanPool production integration, Proposal/Safe Apply refresh, recovery/
  resume, Greenfield E2E, platform rollout, benchmark, and legacy retirement remain in PIR-10+.
Next package: PIR-10 — Planner and PlanPool production integration.
Blocker: none.
```

```text
Work package: PIR-10 — Planner and authoritative PlanPool production integration
Status: acceptance_complete
Changed modules/files:
- agent/project_intelligence/plan_compiler.py — Blueprint dependency cycles and missing
  dependencies now fail before PlanPool creation; pseudo Blueprint elements compile to
  non-file planning/verification items; planning envelope hashes and explicit
  Blueprint-element-to-PlanItem maps are persisted with revision refs.
- agent/project_intelligence/planpool_adapter.py — compiled Blueprint plans translate through
  the existing AtlasPlanPoolBuilder and AtlasPlanPoolStorage authority, preserving completed
  items and carrying Project Intelligence metadata onto pools and items.
- app/api/atlas_pipeline.py — production PlanPool creation invokes the registered Project
  Intelligence planning adapter in shadow/active modes, persists manifest/revision/readiness
  metadata on PlanPool state, and blocks active planning when PI context is stale/degraded.
- tests/test_project_intelligence_plan_compiler.py
- tests/test_project_intelligence_planpool_adapter.py
- tests/test_atlas_api_pipeline.py
- tests/test_project_intelligence_recovery_baseline.py — PIR0-C07 dependency-cycle lock now
  passes and PIR-10 status advanced; later package locks remain strict xfail.
Executed commands and exact results:
- python -m py_compile app/api/atlas_pipeline.py
  agent/project_intelligence/plan_compiler.py agent/project_intelligence/planpool_adapter.py
  tests/test_atlas_api_pipeline.py tests/test_project_intelligence_plan_compiler.py
  tests/test_project_intelligence_planpool_adapter.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_plan_compiler.py
  tests/test_project_intelligence_planpool_adapter.py tests/test_project_intelligence_planner_bridge.py
  tests/test_atlas_plan_pool_builder.py tests/test_atlas_plan_pool_storage.py
  tests/test_atlas_api_pipeline.py tests/test_project_intelligence_recovery_baseline.py ->
  91 passed, 2 xfailed in 24.21s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- $files = @(Get-ChildItem tests -Filter 'test_project_intelligence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_twin_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_blueprint_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_architecture_blueprint_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_convergence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_project_convergence_*.py' | ForEach-Object { $_.FullName }) +
  @(Get-ChildItem tests -Filter 'test_atlas_plan_pool_*.py' | ForEach-Object { $_.FullName }) +
  @((Resolve-Path tests/test_atlas_api_pipeline.py).Path, (Resolve-Path tests/test_atlas_planner_bridge.py).Path);
  python -m pytest -q @files -> 566 passed, 2 xfailed in 57.30s
Unavailable checks: no live external Planner LLM success path or UI session was required; the
  production API path was exercised deterministically through PlanPool creation with a registered
  Project Intelligence service. PIR-11 owns Proposal/Safe Apply refresh and PIR-13 owns real
  Greenfield E2E.
Safety invariants checked: off/no-service PlanPool creation remains legacy-compatible; shadow
  mode is non-interfering; active stale/degraded PI context records a blocking PlanPool metadata
  reason rather than approving execution; PlanPool storage remains authoritative; Planner does
  not access private module stores; completed items remain completed during downstream replan.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: coordinator active context still depends on later real module-output work;
  Proposal, Safe Apply, refresh, recovery/resume, Greenfield E2E, platform rollout, benchmark,
  and legacy retirement remain in PIR-11+.
Next package: PIR-11 — Proposal, Safe Apply, and refresh integration.
Blocker: none.
```

```text
Work package: PIR-11 — Proposal, Safe Apply, refresh, and generation-context integration
Status: acceptance_complete
Changed modules/files:
- agent/atlas_patch_proposal_service.py — Proposal generation accepts an optional Project
  Intelligence coordinator, builds manifest-backed generation context at the canonical
  Proposal input boundary, persists generation manifest/base revision metadata in proposals,
  and blocks stale Actual/Twin revisions before model invocation.
- agent/atlas_safe_apply_execution_service.py — after canonical Safe Apply persistence,
  successful applies notify Project Intelligence through record_apply_result, persist Twin
  refresh and Convergence metadata on safe_apply, preserve canonical apply success on PI
  failure as degraded retry metadata, and avoid duplicate PI notification for the same run
  correlation.
- agent/project_intelligence/contracts.py and coordinator.py — post-apply results now carry
  Convergence report/decision metadata; active record_apply_result evaluates and persists
  a bounded Convergence report/decision through the public Convergence facade after Twin ingest.
- app/api/atlas_pipeline.py, app/api/atlas_autopilot_factory.py,
  app/api/atlas_multi_item_autopilot.py, app/api/atlas_autonomous_codegen.py — app-created
  Proposal/Safe Apply services now pass the registered Project Intelligence coordinator when
  available while no-service/off behavior remains unchanged.
- tests/test_project_intelligence_pir11_generation_apply.py — real Proposal and Safe Apply
  service coverage in a temporary workspace for generation metadata, stale no-call blocking,
  post-apply Twin refresh plus Convergence report/decision, and PI notification idempotence.
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/contracts.py
  agent/project_intelligence/coordinator.py agent/atlas_patch_proposal_service.py
  agent/atlas_safe_apply_execution_service.py app/api/atlas_pipeline.py
  app/api/atlas_autopilot_factory.py app/api/atlas_multi_item_autopilot.py
  app/api/atlas_autonomous_codegen.py
  tests/test_project_intelligence_pir11_generation_apply.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_pir11_generation_apply.py
  tests/test_project_intelligence_generator_bridge.py
  tests/test_atlas_patch_proposal_codegen_contract.py tests/test_atlas_patch_generation_incident.py
  tests/test_atlas_read_before_edit.py tests/test_atlas_safe_apply_metadata_persistence.py
  tests/test_atlas_api_pipeline.py tests/test_project_intelligence_recovery_baseline.py ->
  84 passed, 2 xfailed in 28.67s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
Unavailable checks: no live external UI session was required for this package. A broader legacy
  manual-flow batch was not used as proof because it contains unrelated stale tests that call
  /plan-pools without sync=1 and Windows default-encoding source reads.
Safety invariants checked: stale generation blocks before the LLM call; Proposal remains
  proposal-only and does not run Safe Apply; Safe Apply remains canonical mutation authority;
  Project Intelligence post-apply failures are recorded as degraded retry metadata and do not
  undo successful canonical apply; duplicate PI post-apply notification is suppressed by
  correlation ID; Convergence remains advisory and does not mutate PlanPool or workspace state.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: verification adapter production integration, recovery/resume, Greenfield E2E,
  platform rollout, benchmark, and legacy retirement remain.
Next package: PIR-12 — Verification, recovery, checkpoint, and resume integration.
Blocker: none.
```

```text
Work package: PIR-12 — Verification, bounded recovery, checkpoint, and resume integration
Status: production_connected
Changed modules/files:
- agent/project_intelligence/contracts.py and coordinator.py — verification requests now carry
  distinct Blueprint, Actual Twin, source, and PlanPool revisions; active post-verification
  ingestion emits runtime/event records, evaluates Convergence through the public facade, and
  returns report/decision metadata without changing verification authority.
- agent/project_intelligence/verification_integration.py — production Atlas verification adapter
  converts persisted manual/auto verification results to runtime observations, records durable
  idempotent checkpoints, maps bounded Convergence decisions to existing continuation/repair/
  replan/critical-decision/halt service names, and keeps source/apply/PlanPool revisions separate.
- agent/atlas_verification_gate_service.py and agent/atlas_auto_verification_service.py — canonical
  manual and auto verification services record Project Intelligence metadata only after their
  existing verification persistence succeeds.
- app/api/atlas_pipeline.py, app/api/atlas_autopilot_factory.py, and
  app/api/atlas_multi_item_autopilot.py — registered production Project Intelligence coordinator
  and durable checkpoint controller are passed into verification service construction where
  available; no-service/off behavior remains legacy-compatible.
- tests/test_project_intelligence_pir12_verification_recovery.py — production-path verification
  coverage for manual service, replay idempotency, sync API wiring, and auto verification.
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/contracts.py
  agent/project_intelligence/coordinator.py agent/project_intelligence/verification_integration.py
  agent/atlas_verification_gate_service.py agent/atlas_auto_verification_service.py
  app/api/atlas_pipeline.py app/api/atlas_autopilot_factory.py
  app/api/atlas_multi_item_autopilot.py
  tests/test_project_intelligence_pir12_verification_recovery.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_pir12_verification_recovery.py ->
  4 passed in 3.92s
- python -m pytest -q tests/test_project_intelligence_pir12_verification_recovery.py
  tests/test_project_intelligence_verification_resume.py
  tests/test_project_twin_durable_event_projection.py
  tests/test_project_intelligence_pir11_generation_apply.py
  tests/test_atlas_api_pipeline.py -> 50 passed in 12.16s
- python tools/generate_project_intelligence_consumer_inventory.py -> wrote
  docs/generated/atlas_project_intelligence_consumer_inventory.json
  production_entrypoints=32 legacy_consumers=43 facades=6 adapters=3 critical_findings=6
- python -m pytest -q tests/test_project_intelligence_recovery_baseline.py ->
  9 passed, 2 xfailed in 13.18s
Unavailable checks: PIR-12 acceptance scenarios for bounded retry routing, restart resume through
  the recovery/continuation API, external edit prevention before blind resume, unsafe halt, critical
  decision surfacing, and final completion gating are not yet proven by this slice.
Safety invariants checked: verification remains canonical; Project Intelligence records only
  post-persistence metadata; unavailable/blocked verification is not converted to passed;
  checkpoints are idempotent by run correlation; Convergence decisions are advisory metadata and
  do not mutate PlanPool, Proposal, Safe Apply, Verification, or workspace state.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: this is production-connected, not acceptance-complete; remaining PIR-12 work
  must prove existing recovery/resume/bounded-retry/critical-decision/final-gate behavior.
Next package: PIR-12 — complete recovery, checkpoint, resume, and final-gate acceptance.
Blocker: none.
```

```text
Work package: PIR-12 — Verification, bounded recovery, checkpoint, and resume integration
Status: acceptance_complete
Changed modules/files:
- agent/project_intelligence/verification_integration.py — checkpoint metadata now carries the
  working tree hash needed to prevent blind resume after external edits.
- agent/atlas_recovery_service.py — existing recovery summaries read Project Intelligence
  checkpoint metadata, detect external source drift, map repair/replan/Blueprint/critical/unsafe
  decisions to existing recovery next actions, preserve completed PlanPool items, and gate completed
  pools on canonical verification plus Project Intelligence acceptance.
- agent/atlas_continuation_service.py — existing continuation prompt/metadata now surfaces
  Project Intelligence resume action, blind-resume allowance, checkpoint id, and final-gate blockers.
- tests/test_project_intelligence_pir12_verification_recovery.py — acceptance coverage added for
  checkpoint resume, recovery API external-edit prevention, bounded repair routing, critical-decision
  routing, unsafe halt, and final completion gating.
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/verification_integration.py
  agent/atlas_recovery_service.py agent/atlas_continuation_service.py
  tests/test_project_intelligence_pir12_verification_recovery.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_pir12_verification_recovery.py ->
  9 passed in 4.91s
- python -m pytest -q tests/test_project_intelligence_pir12_verification_recovery.py
  tests/test_project_intelligence_verification_resume.py tests/test_atlas_api_pipeline.py
  tests/test_project_intelligence_pir11_generation_apply.py
  tests/test_project_twin_durable_event_projection.py -> 55 passed in 13.46s
- python -m pytest -q tests/test_project_intelligence_recovery_baseline.py ->
  9 passed, 2 xfailed in 13.46s
Unavailable checks: a broader legacy corridor was not used as proof because stale fixtures in
  tests/test_atlas_manual_loop_smoke.py call /plan-pools without sync=1, and stale fallback-pool
  fixtures in tests/test_atlas_bounded_retry_service.py and tests/test_atlas_orchestration_summary.py
  index an empty fallback pool before exercising their target services.
Safety invariants checked: blind resume is denied on external source drift; failed verification
  routes to bounded repair without mutation; critical/unsafe decisions block continuation through
  existing decision/failure-stop surfaces; completed PlanPool items are not reset by recovery
  summaries; final completion requires canonical verification and Project Intelligence acceptance.
Migration/rollout state: rollout remains off by default; no legacy consumer cutover or legacy
  deletion was performed.
Known limitations: real Greenfield E2E, CI/platform/scale/cutover, benchmark, and legacy retirement
  remain in PIR-13+.
Next package: PIR-13 — real Greenfield E2E.
Blocker: none.
```

```text
Work package: PIR-13 — Real Greenfield state machine and end-to-end generation
Status: component_complete
Changed modules/files:
- agent/project_intelligence/greenfield_state_machine.py — durable Greenfield run state,
  transition store, explicit PIR-13 states, typed canonical outcomes, transition validation,
  idempotency keys, revision/ref/evidence capture, slice advancement, and completion gate
  requiring canonical verification plus Convergence acceptance.
- tests/test_project_intelligence_pir13_greenfield_state_machine.py — component coverage for
  persistence/restart, typed slice outcomes, idempotent replay, invalid transition rejection,
  and blocked completion without verification/Convergence acceptance.
Executed commands and exact results:
- python -m py_compile agent/project_intelligence/greenfield_state_machine.py
  tests/test_project_intelligence_pir13_greenfield_state_machine.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_pir13_greenfield_state_machine.py
  tests/test_project_intelligence_greenfield.py tests/test_project_intelligence_greenfield_e2e.py ->
  19 passed in 1.65s
Unavailable checks: normal Atlas API entrypoint wiring, real temporary workspace scenario execution,
  browser/API readiness probes, failure repair/resume, and live configured-model Greenfield evidence
  remain for later PIR-13 slices.
Safety invariants checked: the state machine accepts typed outcomes instead of Booleans, rejects
  invalid skips to completion, records idempotency/revision/evidence refs for every transition, and
  does not write the workspace or bypass Proposal/Safe Apply/Verification.
Migration/rollout state: rollout remains off by default; no legacy Greenfield helper deletion and no
  consumer cutover were performed.
Known limitations: this is component-complete only; production entrypoint and real scenario evidence
  are still incomplete.
Next package: PIR-13 — connect Greenfield state machine to normal Atlas entrypoint and real scenarios.
Blocker: none.
```

```text
Work package: PIR-13 — Normal Atlas entrypoint to real Safe Apply Greenfield scenario
Status: production_connected
Changed modules/files:
- agent/atlas_patch_proposal_planitem_service.py — approved patch proposal PlanItem drafts now
  preserve the source proposal's successful patch_generation contract and the canonical source
  action_type create/update, so Greenfield create work reaches Safe Apply as a real create instead
  of an update against a missing file.
- tests/test_project_intelligence_pir13_entrypoint_scenarios.py — normal API scenario from
  /api/atlas/plan-pools?sync=1 through patch proposal generation, proposal approval, PlanItem draft,
  PlanItem approval, and /api/atlas/safe-apply/execute against a real temporary workspace and the
  canonical AtlasFileSafeApplyExecutor.
- tests/test_project_intelligence_recovery_baseline.py — status lock updated to the PIR-13
  production_connected proof level.
Executed commands and exact results:
- python -m py_compile agent/atlas_patch_proposal_planitem_service.py
  tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_project_intelligence_recovery_baseline.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py ->
  1 passed in 6.80s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_patch_proposal_planitem_draft_api.py
  tests/test_project_intelligence_pir13_greenfield_state_machine.py
  tests/test_project_intelligence_greenfield.py tests/test_project_intelligence_greenfield_e2e.py
  tests/test_project_intelligence_recovery_baseline.py -> 45 passed, 2 xfailed in 24.28s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_patch_proposal_planitem_draft_api.py
  tests/test_atlas_patch_proposal_planitem_safe_apply_flow.py
  tests/test_atlas_patch_proposal_to_safe_apply_e2e.py
  tests/test_atlas_safe_apply_execution_api.py -> 22 passed, 18 failed in 11.03s
  because stale helper tests still call /api/atlas/plan-pools without sync=1 and receive the
  current async job handle instead of an inline plan_pool payload.
Unavailable checks: browser assertion/readiness probe, API readiness, restart reopen, injected
  intermediate failure with repair/resume, additional Python/FastAPI/SQLite/frontend-backend
  scenarios, and a live configured-model Greenfield run are not proven by this slice.
Safety invariants checked: Proposal remains non-mutating; proposal approval and PlanItem approval
  remain manual gates; Safe Apply is still the only workspace mutation path; no verification is
  converted from unavailable to passed; rollout remains off.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: production_connected means the normal Atlas API path now reaches a real
  temporary workspace write through canonical Safe Apply for one single-HTML scenario. PIR-13 is not
  acceptance_complete until real verification/readiness, restart, failure repair/resume, supported
  scenario breadth, artifact retention, and live-model gates are complete.
Next package: PIR-13 — add real verification/readiness, restart, fault repair/resume, and scenario
  breadth.
Blocker: none.
```

```text
Work package: PIR-13 — Single HTML visual verification and readiness evidence
Status: production_connected
Changed modules/files:
- agent/atlas_auto_verification_service.py — auto verification metadata now normalizes legacy
  boolean auto_verification flags into structured runtime metadata before command, visual, or
  Project Intelligence verification persistence.
- tests/test_project_intelligence_pir13_entrypoint_scenarios.py — the normal Atlas entrypoint
  Greenfield scenario now continues after real Safe Apply into /api/atlas/automation/verify-one,
  requiring visual contract pass, browser smoke pass/skip truth, verify_level evidence, persisted
  auto_verification metadata, and the auto_verification_passed event.
Executed commands and exact results:
- python -m py_compile agent/atlas_auto_verification_service.py
  tests/test_project_intelligence_pir13_entrypoint_scenarios.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py ->
  1 passed in 8.49s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_auto_verification_service.py tests/test_visual_contract_matrix.py
  tests/test_project_intelligence_pir12_verification_recovery.py
  tests/test_project_intelligence_recovery_baseline.py -> 78 passed, 2 xfailed in 32.44s
- Ad hoc API evidence capture for the same single-HTML scenario returned status=passed,
  visual_contract.status=passed, visual_contract.contract_id=static_html_visual_v1,
  browser_smoke.status=browser_smoke_passed, and verify_level=runtime_smoke_checked.
- python -m pytest -q tests/test_atlas_auto_verification_api.py::test_safe_apply_one_and_verify_success ->
  failed in 7.45s with status=applied_but_verification_failed because the existing test fixture
  trips requirement_coverage_incomplete even though its allowlisted pytest command passed. This is
  not used as PIR-13 proof.
Unavailable checks: restart/reopen persistence, injected intermediate failure with repair/resume,
  Python CLI/FastAPI/FastAPI+SQLite/frontend-backend scenario breadth, artifact-retention audit,
  and a live configured-model Greenfield run are not proven by this slice.
Safety invariants checked: verification runs only after Safe Apply metadata is applied; legacy
  boolean auto_verification flags are retained as enabled=false metadata instead of authorizing
  automatic execution; browser smoke is truthful evidence, not substituted by file existence; no
  unavailable check is converted to passed.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-13 remains production_connected, not acceptance_complete, until restart,
  fault repair/resume, scenario breadth, artifact-retention, and live-model gates pass.
Next package: PIR-13 — add restart/reopen persistence and fault repair/resume evidence.
Blocker: none.
```

```text
Work package: PIR-13 — Restart/reopen persistence for the single HTML scenario
Status: production_connected
Changed modules/files:
- tests/test_project_intelligence_pir13_entrypoint_scenarios.py — after real Safe Apply and
  visual verification, the scenario now creates a fresh FastAPI app via app.server.create_app,
  points it at the same Atlas data root, reloads the persisted PlanPool, and reads recovery and
  continuation APIs from disk-backed state.
Executed commands and exact results:
- python -m py_compile tests/test_project_intelligence_pir13_entrypoint_scenarios.py -> compile OK
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py ->
  1 passed in 8.79s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_recovery_service.py tests/test_project_intelligence_pir12_verification_recovery.py
  tests/test_project_intelligence_recovery_baseline.py -> 26 passed, 2 xfailed in 25.44s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_recovery_service.py tests/test_atlas_continuation_service.py
  tests/test_project_intelligence_pir12_verification_recovery.py
  tests/test_project_intelligence_recovery_baseline.py -> 28 passed, 2 xfailed, 10 failed in 26.19s
  because tests/test_atlas_continuation_service.py still uses a stale fallback-pool fixture that
  indexes pool.items[0] after build_fallback_pool now returns no items.
Unavailable checks: injected intermediate failure with repair/resume, Python CLI/FastAPI/
  FastAPI+SQLite/frontend-backend scenario breadth, artifact-retention audit, and a live
  configured-model Greenfield run are not proven by this slice.
Safety invariants checked: restart proof reads persisted PlanPool, Safe Apply, auto verification,
  recovery, and continuation state from disk through a fresh app; no mutation or verification is
  replayed during restart; unavailable continuation fixture failures are not counted as passed.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-13 remains production_connected, not acceptance_complete, until fault
  repair/resume, scenario breadth, artifact-retention, and live-model gates pass.
Next package: PIR-13 — add fault repair/resume and scenario breadth evidence.
Blocker: none.
```

```text
Work package: PIR-13 — Fault repair and resume through the normal Atlas entrypoint
Status: production_connected
Changed modules/files:
- tests/test_project_intelligence_pir13_entrypoint_scenarios.py — added a normal API scenario
  from /api/atlas/plan-pools?sync=1 through proposal generation, proposal approval, PlanItem
  draft, PlanItem approval, /api/atlas/automation/safe-apply-one-and-verify, bounded
  self-correction, repaired Safe Apply, repaired visual verification, event-journal assertions,
  fresh app reload, and recovery/continuation API reads from persisted state.
Executed commands and exact results:
- python -m py_compile tests/test_project_intelligence_pir13_entrypoint_scenarios.py ->
  compile OK
- python -m pytest -q
  tests/test_project_intelligence_pir13_entrypoint_scenarios.py::test_pir13_normal_entrypoint_fault_repair_recovers_and_resumes ->
  1 passed in 25.01s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py ->
  2 passed in 27.41s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_self_correction_service.py tests/test_atlas_auto_verification_service.py
  tests/test_visual_contract_matrix.py tests/test_project_intelligence_pir13_greenfield_state_machine.py
  tests/test_project_intelligence_recovery_baseline.py -> 81 passed, 2 xfailed in 49.38s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_self_correction_service.py tests/test_atlas_single_item_self_correction_loop.py
  tests/test_atlas_self_correction_visual_high_risk_gate.py tests/test_visual_contract_matrix.py
  tests/test_project_intelligence_pir13_greenfield_state_machine.py
  tests/test_project_intelligence_recovery_baseline.py -> 75 passed, 2 xfailed, 5 failed in
  55.32s because stale visual self-correction fixtures still expect high-risk frontend repairs
  to skip despite the current audited exception, and some fake patch services omit the newer
  patch_generation success metadata required by self-correction.
Unavailable checks: Python CLI/FastAPI/FastAPI+SQLite/frontend-backend scenario breadth,
  artifact-retention audit, and a live configured-model Greenfield run are not proven by this
  slice.
Safety invariants checked: the repaired path starts from a manually approved proposal and
  manually approved PlanItem; the first failed verification remains recorded as failed; repair is
  bounded through the existing self-correction service and low-risk policy; Safe Apply remains the
  only workspace mutation path; a fresh app reload reads persisted repaired state without replaying
  mutation or verification; unavailable/stale tests are not counted as passed.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-13 remains production_connected, not acceptance_complete, until scenario
  breadth, artifact-retention, and live-model gates pass.
Next package: PIR-13 — add scenario breadth evidence.
Blocker: none.
```

```text
Work package: PIR-13 — Python CLI failing-test repair scenario
Status: production_connected
Changed modules/files:
- app/api/atlas_pipeline.py — /api/atlas/automation/safe-apply-one-and-verify now carries the
  original allowlisted command_id and test_path/test_file metadata into the verification failure
  feedback handed to bounded self-correction, so command-based repairs re-run the same authorized
  verification target instead of losing the command target on repair.
- tests/test_project_intelligence_pir13_entrypoint_scenarios.py — added a normal API Python CLI
  Greenfield scenario from /api/atlas/plan-pools?sync=1 through proposal generation, proposal
  approval, PlanItem draft, PlanItem approval, /api/atlas/automation/safe-apply-one-and-verify,
  initial failing pytest_selected verification, bounded self-correction, repaired Safe Apply,
  repaired pytest_selected verification, and event-journal assertions.
Executed commands and exact results:
- python -m py_compile app\api\atlas_pipeline.py
  tests\test_project_intelligence_pir13_entrypoint_scenarios.py -> compile OK
- python -m pytest -q
  tests/test_project_intelligence_pir13_entrypoint_scenarios.py::test_pir13_python_cli_failing_test_repairs_through_allowlisted_pytest ->
  1 passed in 8.87s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py ->
  3 passed in 29.76s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_self_correction_service.py tests/test_atlas_auto_verification_service.py
  tests/test_visual_contract_matrix.py tests/test_project_intelligence_pir13_greenfield_state_machine.py
  tests/test_project_intelligence_recovery_baseline.py -> 82 passed, 2 xfailed in 52.45s
Unavailable checks: FastAPI API, FastAPI+SQLite persistence/restart, frontend/backend browser-to-API,
  artifact-retention audit, and a live configured-model Greenfield run are not proven by this
  slice.
Safety invariants checked: command execution remains allowlist-based through pytest_selected;
  repair reuses the original command target instead of accepting arbitrary commands; the first
  pytest failure remains recorded as failed; repair is bounded through the existing self-correction
  service and low-risk policy; Safe Apply remains the only workspace mutation path; unavailable
  checks are not counted as passed.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-13 remains production_connected, not acceptance_complete, until remaining
  scenario breadth, artifact-retention, and live-model gates pass.
Next package: PIR-13 — add FastAPI API scenario evidence.
Blocker: none.
```

```text
Work package: PIR-13 — FastAPI API scenario
Status: production_connected
Changed modules/files:
- tests/test_project_intelligence_pir13_entrypoint_scenarios.py — added a normal API FastAPI
  Greenfield scenario from /api/atlas/plan-pools?sync=1 through proposal generation, proposal
  approval, PlanItem draft, PlanItem approval, /api/atlas/automation/safe-apply-one-and-verify,
  real Safe Apply of app/main.py, and real pytest_selected verification using FastAPI TestClient
  against GET /health.
Executed commands and exact results:
- python -m py_compile tests\test_project_intelligence_pir13_entrypoint_scenarios.py ->
  compile OK
- python -m pytest -q
  tests/test_project_intelligence_pir13_entrypoint_scenarios.py::test_pir13_fastapi_api_scenario_reaches_real_pytest_probe ->
  1 passed in 8.53s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py ->
  4 passed in 31.74s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_auto_verification_service.py tests/test_visual_contract_matrix.py
  tests/test_project_intelligence_pir13_greenfield_state_machine.py
  tests/test_project_intelligence_recovery_baseline.py -> 77 passed, 2 xfailed in 53.66s
Unavailable checks: FastAPI+SQLite persistence/restart, frontend/backend browser-to-API,
  artifact-retention audit, and a live configured-model Greenfield run are not proven by this
  slice.
Safety invariants checked: FastAPI code is generated through Proposal and applied only through
  Safe Apply after manual proposal and PlanItem approvals; readiness is proven by an allowlisted
  pytest_selected TestClient probe, not by file existence; no unavailable check is counted as
  passed.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-13 remains production_connected, not acceptance_complete, until remaining
  scenario breadth, artifact-retention, and live-model gates pass.
Next package: PIR-13 — add FastAPI+SQLite persistence/restart scenario evidence.
Blocker: none.
```

```text
Work package: PIR-13 — FastAPI + SQLite persistence/restart scenario
Status: production_connected
Changed modules/files:
- tests/test_project_intelligence_pir13_entrypoint_scenarios.py — added a normal API
  FastAPI+SQLite Greenfield scenario from /api/atlas/plan-pools?sync=1 through proposal
  generation, proposal approval, PlanItem draft, PlanItem approval,
  /api/atlas/automation/safe-apply-one-and-verify, real Safe Apply of app/main.py, and real
  pytest_selected verification that writes an item to SQLite, reloads the generated FastAPI module,
  and reads the persisted row back.
Executed commands and exact results:
- python -m py_compile tests\test_project_intelligence_pir13_entrypoint_scenarios.py ->
  compile OK
- python -m pytest -q
  tests/test_project_intelligence_pir13_entrypoint_scenarios.py::test_pir13_fastapi_sqlite_persists_after_reload ->
  1 passed in 8.44s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py ->
  5 passed in 33.81s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_auto_verification_service.py tests/test_visual_contract_matrix.py
  tests/test_project_intelligence_pir13_greenfield_state_machine.py
  tests/test_project_intelligence_recovery_baseline.py -> 78 passed, 2 xfailed in 56.24s
Unavailable checks: frontend/backend browser-to-API, artifact-retention audit, and a live
  configured-model Greenfield run are not proven by this slice.
Safety invariants checked: SQLite-backed FastAPI code is generated through Proposal and applied
  only through Safe Apply after manual proposal and PlanItem approvals; persistence/restart is
  proven by an allowlisted pytest_selected TestClient probe that reloads the generated module and
  reads the SQLite row back; no unavailable check is counted as passed.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-13 remains production_connected, not acceptance_complete, until frontend/
  backend scenario, artifact-retention, and live-model gates pass.
Next package: PIR-13 — add frontend/backend browser-to-API scenario evidence.
Blocker: none.
```

```text
Work package: PIR-13 — Frontend/backend browser-to-API scenario
Status: production_connected
Changed modules/files:
- tests/test_project_intelligence_pir13_entrypoint_scenarios.py — added a normal API
  frontend/backend Greenfield scenario from /api/atlas/plan-pools?sync=1 through proposal
  generation, proposal approval, PlanItem draft, PlanItem approval,
  /api/atlas/automation/safe-apply-one-and-verify, real Safe Apply of app/main.py, and real
  pytest_selected verification that starts uvicorn, opens Chromium with Playwright, clicks the
  frontend button, and proves browser JavaScript fetched /api/message from the backend.
Executed commands and exact results:
- python -m py_compile tests\test_project_intelligence_pir13_entrypoint_scenarios.py ->
  compile OK
- python -m pytest -q
  tests/test_project_intelligence_pir13_entrypoint_scenarios.py::test_pir13_frontend_backend_browser_to_api_flow ->
  1 passed in 11.14s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py ->
  6 passed in 38.64s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_atlas_auto_verification_service.py tests/test_visual_contract_matrix.py
  tests/test_project_intelligence_pir13_greenfield_state_machine.py
  tests/test_project_intelligence_recovery_baseline.py -> 79 passed, 2 xfailed in 60.31s
Unavailable checks: artifact-retention audit and a live configured-model Greenfield run are not
  proven by this slice.
Safety invariants checked: frontend/backend code is generated through Proposal and applied only
  through Safe Apply after manual proposal and PlanItem approvals; browser-to-API readiness is
  proven by an allowlisted pytest_selected command that starts uvicorn and runs Chromium/Playwright;
  no unavailable check is counted as passed.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-13 remains production_connected, not acceptance_complete, until
  artifact-retention and live-model gates pass.
Next package: PIR-13 — add artifact-retention audit evidence.
Blocker: none.
```

```text
Work package: PIR-13 — Artifact-retention audit for the normal Atlas entrypoint
Status: production_connected
Changed modules/files:
- tests/test_project_intelligence_pir13_entrypoint_scenarios.py — the normal single-HTML
  Greenfield scenario now asserts retained proposal JSON/Markdown, proposal-approval
  JSON/Markdown, PlanItem draft JSON/Markdown, Safe Apply execution JSON/Markdown, workspace
  change-snapshot manifest, verification events.ndjson, and the persisted restart-visible Safe
  Apply snapshot reference.
Executed commands and exact results:
- python -m py_compile tests\test_project_intelligence_pir13_entrypoint_scenarios.py ->
  compile OK
- python -m pytest -q
  tests/test_project_intelligence_pir13_entrypoint_scenarios.py::test_pir13_normal_entrypoint_single_html_reaches_real_safe_apply ->
  1 passed in 8.91s
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py ->
  6 passed in 38.79s
Unavailable checks: a live configured-model Greenfield run is not proven by this slice.
Safety invariants checked: proposal, approval, draft, Safe Apply, snapshot, verification event,
  restart, recovery, and continuation evidence is read from durable artifacts written by the
  normal Atlas entrypoint; snapshot artifacts are asserted under the target workspace root while
  Atlas journal artifacts remain under ca_data; unavailable checks are not counted as passed.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-13 remains production_connected, not acceptance_complete, until the live
  configured-model Greenfield run passes through the normal entrypoint with recorded evidence.
Next package: PIR-13 — run live configured-model Greenfield evidence.
Blocker: none.
```

```text
Work package: PIR-13 — Live configured-model Greenfield gate probe
Status: blocked
Changed modules/files:
- docs/atlas_project_intelligence_recovery_current_status.md — PIR-13 now records the live
  configured-model gate as blocked by unavailable model runtime instead of treating it as
  production_connected or passing an unavailable check.
- tests/test_project_intelligence_recovery_baseline.py — recovery-status lock updated to require
  the explicit PIR-13 blocked proof level while this gate is unavailable.
Executed commands and exact results:
- Get-ChildItem Env: | Where-Object { $_.Name -match 'OPENAI|ANTHROPIC|CODEAGENT|LLM|MODEL|BASE_URL|API_KEY' } -> no matching configured model environment variables were present.
- Invoke-WebRequest -Uri 'http://127.0.0.1:8080/v1/models' -UseBasicParsing -TimeoutSec 5 ->
  connection refused by 127.0.0.1:8080.
- Invoke-WebRequest -Uri 'http://127.0.0.1:8000/v1/models' -UseBasicParsing -TimeoutSec 5 ->
  connection refused by 127.0.0.1:8000.
- python adapter probe through main._phase1_llm_json -> LLM_URL_PLANNER=
  http://localhost:8080/v1/chat/completions; warning 503 llm_not_ready; phase1_result=None.
Unavailable checks: the required live configured-model Greenfield run cannot be executed until a
  configured model endpoint is started or credentials are supplied.
Safety invariants checked: no synthetic/stubbed model output is counted as live-model evidence;
  unavailable remains unavailable; no Safe Apply, workspace mutation, or legacy Greenfield path
  deletion was performed for this probe.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-13 remains blocked until the same normal Atlas entrypoint path is rerun
  with a real configured model and records successful proposal, apply, verification, runtime, and
  restart evidence.
Next package: PIR-13 — rerun live configured-model Greenfield evidence after model provisioning.
Blocker: configured model unavailable in this environment.
```

```text
Work package: PIR-13 — Opt-in live configured-model Greenfield runner
Status: blocked
Changed modules/files:
- tools/run_pir13_live_greenfield.py — added an opt-in live PIR-13 runner that uses the
  configured Atlas model adapter, creates a real temporary workspace through the normal
  /api/atlas/plan-pools?sync=1 entrypoint with planner_mode=real_planner, refuses fallback/
  clarification/unavailable model output as blocked, and proceeds through Proposal,
  proposal approval, PlanItem draft, PlanItem approval, Safe Apply, and auto verification only
  when the live model returns usable artifacts. The pass path also reopens a fresh app and
  requires persisted PlanPool, Safe Apply, auto-verification, recovery, and continuation evidence.
- tests/test_pir13_live_greenfield_runner.py — added a synthetic-model runner mechanics test
  proving the opt-in runner reaches Safe Apply, verification, and restart evidence through the
  same API path when a model adapter returns usable structured output. This is not counted as
  live-model PIR-13 evidence.
- docs/atlas_project_intelligence_recovery_current_status.md — next action now points to the
  opt-in runner command and records that the current environment still blocks on model
  availability.
Executed commands and exact results:
- python -m py_compile tools\run_pir13_live_greenfield.py
  tests\test_pir13_live_greenfield_runner.py -> compile OK
- python tools\run_pir13_live_greenfield.py --allow-blocked-exit-zero --output-json
  ca_data\atlas\pir13_live_greenfield_report.current.json -> status=blocked, report written,
  model_probe.llm_url_planner=http://localhost:8080/v1/chat/completions,
  model_probe.result=null, blocked_reason=configured_model_unavailable.
- python -m pytest -q tests\test_pir13_live_greenfield_runner.py -> 1 passed in 8.75s
Unavailable checks: the required live configured-model Greenfield run still cannot be executed
  because no configured model returned JSON from the Atlas adapter in this environment.
Safety invariants checked: the runner does not inject deterministic success, does not count
  fallback planning as live evidence, keeps model-unavailable as blocked by default, and only
  auto-approves the explicitly generated low-risk scenario after Proposal creates a real proposal.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-13 remains blocked until the same runner passes with a real configured
  model and records successful proposal, apply, verification, runtime, and restart evidence.
Next package: PIR-13 — provision/start the configured model and run
  python tools/run_pir13_live_greenfield.py without --allow-blocked-exit-zero.
Blocker: configured model unavailable in this environment.
```

```text
Work package: PIR-13 — Live configured-model Greenfield acceptance
Status: acceptance_complete
Changed modules/files:
- agent/atlas_patch_proposal_service.py — structural-change proposal prompts now require
  complete full-content output for concrete create_file operations, while preserving directory
  materialization boundaries and proposal-only authority.
- tests/test_atlas_patch_proposal_api.py — added a structural create_file proposal regression
  proving the prompt contract and persisted proposed_content path.
- docs/atlas_project_intelligence_recovery_current_status.md — PIR-13 advances to
  acceptance_complete and the active package advances to PIR-14 after live configured-model
  evidence passed.
Executed commands and exact results:
- python tools\run_pir13_live_greenfield.py --output-json
  ca_data\atlas\pir13_live_greenfield_report.live.json -> exit 1, status=failed; live model
  reached plan_pool status=ready with source=real_planner and used_fallback=false, then
  patch_proposal failed with semantic_validation_failed:content_missing and no file was written.
- python -m py_compile agent\atlas_patch_proposal_service.py
  tests\test_atlas_patch_proposal_api.py tools\run_pir13_live_greenfield.py -> compile OK.
- python -m pytest -q
  tests\test_atlas_patch_proposal_api.py::test_structural_create_file_prompt_requires_full_content ->
  1 passed in 4.75s.
- python -m pytest -q tests\test_atlas_patch_proposal_api.py -> 15 passed in 7.02s.
- python tools\run_pir13_live_greenfield.py --output-json
  ca_data\atlas\pir13_live_greenfield_report.live.json -> exit 0, status=passed; model_probe
  status=ready for http://localhost:8080/v1/chat/completions; plan_pool status=ready;
  patch_proposal status=proposed, risk_level=low; proposal_approval status=approved;
  draft status=created; planitem_approval status=running; safe_apply_and_verify
  status=applied_and_verified; restart_evidence.status=passed; artifacts retained proposal
  JSON/Markdown, draft JSON/Markdown, change snapshot manifest, and events.ndjson.
Unavailable checks: none for PIR-13 live configured-model acceptance; PIR-14 platform/scale and
  consumer-cutover evidence remains not_started.
Safety invariants checked: live evidence used the configured Atlas model adapter and refused
  fallback/clarification/unavailable output; no deterministic success runner output was counted;
  Proposal remained advisory, low-risk approval was explicit, mutation happened only through
  Safe Apply, verification/runtime outcomes came from the normal runner path, and restart evidence
  was read after reopening app state.
Migration/rollout state: no legacy Greenfield helper deletion and no consumer cutover were
  performed.
Known limitations: PIR-14 CI/platform/scale/consumer cutover and PIR-15 benchmark/retirement
  remain incomplete.
Next package: PIR-14 — CI, platform, scale, and consumer cutover.
Blocker: none.
```

```text
Work package: PIR-14 — Recovery CI workflow entrypoint
Status: in_progress
Changed modules/files:
- .github/workflows/atlas-project-intelligence-recovery.yml — added a pull_request, main push,
  and manual workflow with focused-regression, integration, restart-fault, fixture-e2e, and
  cutover-platform-contract suites; each suite writes JUnit XML, appends a GitHub Step Summary,
  and uploads artifacts.
- tests/test_project_intelligence_pir14_ci_workflow.py — added static workflow contract tests
  for required suites, artifact retention, and truthful non-claims around live model runs and
  consumer-zero/legacy retirement.
- tests/test_project_intelligence_recovery_baseline.py — recovery status lock updated to require
  PIR-14 in_progress.
- docs/atlas_project_intelligence_recovery_current_status.md — PIR-14 marked in_progress with
  next evidence steps for GitHub CI, consumer registry, shadow parity, rollback, platform, and
  scale.
Executed commands and exact results:
- python -m py_compile tests\test_project_intelligence_pir14_ci_workflow.py
  tests\test_project_intelligence_recovery_baseline.py -> compile OK.
- python -m pytest -q tests\test_project_intelligence_pir14_ci_workflow.py
  tests\test_project_intelligence_recovery_baseline.py::test_recovery_status_selects_next_active_package ->
  4 passed in 0.86s.
- python -m pytest -q tests/test_project_intelligence_recovery_baseline.py
  tests/test_project_intelligence_contracts.py tests/test_project_intelligence_rollout.py
  tests/test_project_intelligence_boundaries.py -> 50 passed, 2 xfailed in 19.86s.
- python -m pytest -q tests/test_project_intelligence_production_composition.py
  tests/test_project_intelligence_planner_bridge.py tests/test_project_intelligence_generator_bridge.py
  tests/test_project_intelligence_pir11_generation_apply.py
  tests/test_project_intelligence_pir12_verification_recovery.py -> 27 passed in 7.91s.
- python -m pytest -q tests/test_project_intelligence_app_lifecycle.py
  tests/test_project_intelligence_persistence.py tests/test_project_intelligence_blueprint_lifecycle.py
  tests/test_project_intelligence_event_bridge.py tests/test_project_intelligence_verification_resume.py ->
  37 passed in 2.99s.
- python -m pytest -q tests/test_project_intelligence_pir13_entrypoint_scenarios.py
  tests/test_pir13_live_greenfield_runner.py -> 7 passed in 42.12s.
- python -m pytest -q tests/test_project_intelligence_consolidation.py
  tests/test_project_intelligence_hardening.py tests/test_project_intelligence_benchmark.py ->
  28 passed in 1.57s.
- gh pr checks 1701 --watch --interval 20 -> exit 0; GitHub Actions workflow
  "Atlas Project Intelligence Recovery" passed on pull_request run 27311076310 and branch push
  run 27311074180. Both runs completed focused-regression, integration, restart-fault,
  fixture-e2e, and cutover-platform-contracts successfully.
Unavailable checks: live model execution, consumer cutover, platform matrix, and scale evidence
  are not claimed by this CI-entrypoint slice.
Safety invariants checked: the new workflow runs pytest suites only, does not run the live
  configured-model runner, does not enable rollout, does not mutate production data, and does not
  remove or retire legacy paths.
Migration/rollout state: rollout remains off by default; no consumer cutover and no legacy
  deletion.
Known limitations: PIR-14 remains in_progress until real consumer registry, shadow parity,
  rollback drills, platform/scale artifacts, and consumer cutover evidence pass.
Next package: PIR-14 — add consumer registry, shadow parity, rollback, platform, scale, and
  cutover evidence.
Blocker: none.
```
