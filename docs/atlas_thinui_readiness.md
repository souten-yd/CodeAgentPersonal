# Atlas ThinUI Readiness

## Purpose
- Current UI is too complex for normal operation.
- Existing UI exposes internal subsystems directly.
- Minimal workflow UI is required before full autonomous mode becomes usable.
- ThinUI does not change the final goal: a fully autonomous code agent.

## Final Goal Preserved
- Atlas final goal remains fully autonomous code agent.
- Goal path remains goal → research → plan → implement → test → fix → PR.
- Self-improving CodeAgentPersonal/KasaneCore remains in scope as a self-improving CodeAgentPersonal/KasaneCore platform objective.
- ThinUI is the frontend strategy for that goal.

## Current UI Problem
- Too many execution buttons are visible at once.
- Too many direct subsystem panels are visible by default.
- Raw IDs and JSON are visible by default.
- Normal users cannot tell which controls are required for normal flow.
- Detailed controls are useful for diagnostics, but should not be the default workflow.

## Minimal Workflow UI
Visible by default:
- task/goal input
- project path
- status/progress
- plan summary
- impact/verification summary
- approval handoff summary
- one primary CTA
- stop/reset
- copy/export approval context

## Advanced Execution Controls
Hidden by default:
- Build Queue
- Prepare
- Preview Token
- Advance to confirmation
- Execute confirmed action and refresh
- Next Action Orchestrator direct panel
- Multi-item Supervised Status
- Supervised Safe Apply
- Supervised Retry
- Patch Regen
- Candidate Approval direct panels

## Diagnostics / Developer Tools
Hidden by default:
- raw JSON panels
- repo index manual operations
- repo context manual operations
- PlanItem Impact Map direct button
- Context Refresh v2 direct button
- Planner Packaging v2 direct button
- Verification Recommendation direct button
- Verification Recommendation Handoff direct button
- direct pool_id/run_id/multi_status_run_id controls
- copy raw payload

## ThinUI Target Architecture
- UI should become a thin state display and approval surface.
- Backend remains responsible for workflow state.
- Frontend should not encode execution decisions.
- Future separate UI / CLI should be possible with the same backend APIs.

## Safety Requirements
- EXECUTE ONE ACTION remains required until policy explicitly changes.
- dry-run-first remains required.
- suggested commands are not executed automatically.
- advanced tools remain accessible.
- emergency stop/reset must remain visible.
- full-auto mode requires snapshot/restore/transaction/rollback readiness.

## PR-74〜80 UI Roadmap
- PR-74: Minimal Atlas Workflow UI shell.
- PR-75: Hide advanced execution panels by default.
- PR-76: Diagnostics drawer and raw JSON isolation.
- PR-77: Atlas workflow state machine UI.
- PR-78: ThinUI contract tests and manifest-driven UI smoke.
- PR-79: Autonomous execution readiness policy checkpoint.
- PR-80: ThinUI architecture checkpoint.

## PR-81+ Autonomous Execution Roadmap
- workspace snapshot / restore foundation
- patch transaction manager
- autonomous execution policy v1
- auto verification loop
- auto patch regeneration loop
- full task autopilot v1
- self-improvement guardrails
- self-improving CodeAgentPersonal platform
- GitHub branch / draft PR automation
- autonomous development milestone
