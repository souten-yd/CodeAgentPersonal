# Atlas Autonomous-first UI Policy

## Purpose
Prevent Atlas UI from expanding into an unmanageable dashboard again.
All future UI work must prioritize the final autonomous code-agent workflow.

## Core Principle
Atlas UI is a supervision surface for autonomous development.
It is not a collection of direct subsystem control panels.

## Final User Flow
The preferred normal flow is:
1. User enters goal.
2. Atlas creates a strategic implementation plan.
3. User reviews plan, risk, verification, and rollback/readiness.
4. User approves.
5. Atlas proceeds through allowed policy gates.
6. Atlas shows progress, failures, recovery options, and final report.
7. Atlas prepares draft PR or artifact bundle when allowed.

## Default Visible UI
Only these are visible by default:
- goal input
- project path
- strategic plan summary
- phase/status/progress
- current item
- next action
- primary CTA
- approval summary
- risk summary
- verification summary
- artifact summary
- progress timeline
- stop / pause / emergency controls

## Hide by Default
These should be hidden behind Advanced or Diagnostics:
- raw JSON
- internal IDs
- direct service buttons
- manual subsystem panels
- repo index manual controls
- repo context manual controls
- context refresh manual controls
- planner packaging manual controls
- impact-map direct controls
- debug review internals
- patch regeneration internals
- direct next-action orchestrator panels
- multi-item supervised status internals

## Remove or Deprecate
Future PRs should remove or deprecate UI surfaces that are:
- duplicate views of the same backend state
- stale after workflow_state contract exists
- debug-only and superseded by diagnostics drawer
- unused by tests and not referenced by manifest
- not needed for normal supervised/autonomous flow
- not needed for emergency recovery
- not needed for audit or diagnostics

Deletion rules:
- First mark as deprecated in manifest.
- Keep access for at least one migration PR unless the element is broken and unused.
- Do not remove safety controls.
- Do not remove diagnostic visibility without replacement.
- Do not remove backend APIs as part of UI cleanup.
- Do not remove DOM IDs in the same PR as behavior changes.

## Classify Every UI Surface
Every Atlas UI surface must be classified as one of:
- minimal_workflow
- safety_always_visible
- advanced_execution
- diagnostics
- deprecated
- removed_after_migration

Definitions:
- minimal_workflow: needed for normal autonomous/supervised operation.
- safety_always_visible: safety, stop, pause, confirmation, risk, failure, rollback status.
- advanced_execution: direct manual controls for expert operation.
- diagnostics: raw data, internal IDs, debug details, subsystem internals.
- deprecated: scheduled for removal or legacy-only.
- removed_after_migration: safe to remove after Vue Atlas Next and CLI parity.

## Anti-divergence Rules
- Do not add a new visible panel by default unless it supports the final user flow.
- Do not expose a direct subsystem button in minimal mode.
- Do not add raw JSON to minimal mode.
- Do not add internal IDs to minimal mode.
- Do not add duplicate status cards without manifest classification.
- Do not make UI compute execution eligibility.
- UI is not the source of workflow truth.
- Every new UI surface must update the UI surface manifest and contract tests.

## Backend Contract Requirement
All future UI clients must use backend workflow contract:
- workflow_state
- available_actions
- blocked_reasons
- safety flags
- readiness policy
- artifacts
- approval summary
- verification summary

## Relationship to Full Autopilot
The UI must be designed for eventual full task autopilot:
- Plan approval should be the main gate.
- Run/continue should operate through policy.
- Medium/high risk stops for human approval.
- Snapshot / restore / patch transaction / rollback readiness must be shown when available.
- Fully automatic mode must not require users to operate low-level internal panels.

## Relationship to CLI/TUI
CLI/TUI must consume the same backend contract.
No future client may depend on classic ui.html DOM structure.
