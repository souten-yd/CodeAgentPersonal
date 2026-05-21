## Active PR Pointer (Updated)

Completed:
- PR-ATLAS-SCALE-73

Current PR:
- PR-ATLAS-SCALE-73

Next PR:
- PR-ATLAS-SCALE-74: Minimal Atlas Workflow UI shell

Known Current Code Facts:
- PR-64〜72 completed the advisory execution-readiness foundation.
- Atlas remains targeted at a fully autonomous code agent.
- ThinUI is the future default interface, not a change in final goal.
- Current UI exposes too many low-level execution/diagnostic controls.
- Minimal workflow UI and Advanced/Diagnostics separation will begin in PR-74.
- Execution semantics remain unchanged.
- `EXECUTE ONE ACTION` remains required for manual execution.
- Dry-run-first remains required.
- Suggested commands are not executed automatically.

# Atlas Scale Master Roadmap

## Final Vision: Autonomous Development Platform
- large repo coding agent
- goal → research → plan → implement → test → fix → PR
- self-improving CodeAgentPersonal/KasaneCore platform
- eventually capable of autonomous implementation loops under policy/safety gates

## Safety Baseline (Unchanged)
- Recommendations are not executions.
- Suggested commands are not executed automatically.
- `EXECUTE ONE ACTION` confirmation remains required.
- Dry-run-first remains required.
- No execution semantics change in PR-73.

## PR-73〜PR-80 ThinUI / Autonomous Readiness Roadmap
- **PR-73: Autonomous Code Agent roadmap consolidation and ThinUI readiness checkpoint**
  - consolidate docs
  - classify current UI surfaces
  - preserve autonomous-code-agent final goal
  - no execution semantics change
- **PR-74: Minimal Atlas Workflow UI shell**
  - visible default UI: task input, project path, status, plan summary, verification handoff summary, primary CTA
  - no execution semantics change
- **PR-75: Hide advanced execution panels by default**
  - move Build Queue / Prepare / Preview Token / Next Action Orchestrator / direct Safe Apply / Retry / Patch Regen into Advanced drawer
  - preserve DOM IDs and tests
- **PR-76: Diagnostics drawer and raw JSON isolation**
  - raw JSON, run IDs, pool IDs, direct repo context tools, planner packaging, impact map, context refresh v2 into Diagnostics
  - accessible but hidden by default
- **PR-77: Atlas workflow state machine UI**
  - single primary CTA changes by backend phase: Plan → Prepare → Dry Run → Execute One Action → Refresh / Continue
  - preserve EXECUTE ONE ACTION gate
- **PR-78: ThinUI contract tests and manifest-driven UI smoke**
  - minimal surfaces visible
  - advanced/diagnostic surfaces accessible but hidden by default
  - no classic script contract violations
- **PR-79: Autonomous execution readiness policy checkpoint**
  - readiness matrix for automatic verification / safe apply / rollback / retry
  - no full-auto execution yet unless policy says ready
- **PR-80: ThinUI architecture checkpoint**
  - evaluate whether Atlas backend supports fully separate UI / CLI
  - document API-only workflow contract

## PR-81〜PR-90 Autonomous Code Agent Execution Roadmap
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

## Historical Chronology (Historical)
- Completed baseline: PR-ATLAS-PIPE-0〜60D
- Completed baseline: PR-ATLAS-SCALE-61〜72
- Historical docs/checkpoint references retained for traceability.


- Historical quality gate reference: PR-ATLAS-DOCS-QUALITY-GATE-01.
- Historical quality marker: PR-ATLAS-SCALE-65B.
