## Active PR Pointer (Updated)

Completed:
- PR-ATLAS-SCALE-76
- PR-ATLAS-SCALE-76B
- PR-ATLAS-SCALE-76C
- PR-ATLAS-SCALE-77
- PR-ATLAS-SCALE-80: out-of-order architecture checkpoint (docs/manifest/tests only; Vue migration plan + autonomous-first UI policy)

Current implementation PR:
- PR-ATLAS-SCALE-78: ThinUI contract tests and manifest-driven UI smoke

Next implementation PR:
- PR-ATLAS-SCALE-79: Autonomous execution readiness policy checkpoint

Known Current Code Facts:
- PR-73 consolidated ThinUI readiness and autonomous code agent roadmap.
- PR-73B explicitly hardens the self-improvement roadmap.
- Atlas remains targeted at a fully autonomous code agent.
- ThinUI is the future default interface, not a change in final goal.
- Current UI exposes too many low-level execution/diagnostic controls.
- PR-74 added the automation-first ThinUI / CLI-compatible workflow shell.
- PR-75 hides advanced execution panels by default.
- Minimal workflow shell remains visible by default.
- Existing advanced execution and diagnostic tools remain accessible.
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


## Automation-first UI / CLI Contract
- Atlas UI is not the source of workflow truth.
- Backend workflow state is authoritative.
- Browser ThinUI, future CLI, future replacement UI, and future full-auto controller must use the same high-level workflow contract.
- UI remains a thin supervision layer: task input, project path, status/progress, phase, approval summary, artifact summary, primary CTA, and stop/emergency control.
- UI must not encode execution decisions.
- Detailed Atlas panels are legacy/debug/advanced surfaces.
- Normal operation should not require direct Build Queue / Prepare / Preview Token / Next Action Orchestrator / Context Refresh / Planner Packaging / Verification Recommendation controls.
- ThinUI is replaceable.
- Future CLI or redesigned UI must drive Atlas through the same backend workflow contract without depending on current DOM structure.
- Final goal remains: fully autonomous code agent (goal → research → plan → implement → test → fix → PR) and self-improving CodeAgentPersonal / KasaneCore platform.

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
- **PR-74: Automation-first ThinUI / CLI workflow shell**
  - add minimal workflow shell
  - define browser UI / CLI / replacement UI / full-auto controller contract
  - backend workflow state is source of truth
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
- **PR-80: ThinUI architecture checkpoint (docs/manifest/tests only; out-of-order)**
  - record Vue Atlas Next migration plan
  - record autonomous-first UI cleanup policy
  - define Go/No-Go criteria for parallel Vue UI
  - decision: Vue implementation starts after PR-80 unless explicitly approved
  - legacy UI remains until parity tests pass
  - no runtime UI replacement in PR-80
  - out-of-order note: PR-80 does not imply PR-77〜79 implementation completion

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


## PR-91〜PR-100 Self-Improving Atlas / KasaneCore Roadmap
- **PR-91: Self-improvement policy and risk classification**
  - classify CodeAgentPersonal / KasaneCore files by risk
  - runtime / launcher / Docker / UI / safety gate files are strict-gate
  - no autonomous self-modification yet
- **PR-92: Self-repo snapshot and restore validation**
  - verify snapshot/restore works on CodeAgentPersonal itself
  - rollback proof required before any self-modification
- **PR-93: Self-repo planning mode**
  - Atlas can plan changes to its own codebase
  - advisory only
  - no patch apply yet
- **PR-94: Self-repo patch candidate generation**
  - generate patch candidates for CodeAgentPersonal / KasaneCore
  - manual approval required
  - no automatic apply
- **PR-95: Self-repo safe_apply with strict gate**
  - apply approved self-modification patches only
  - dry-run-first
  - restore point required
- **PR-96: Self-repo verification loop**
  - run allowlisted tests only
  - no broad shell
  - no unsafe commands
- **PR-97: Self-repo failure recovery**
  - rollback on failed verification
  - preserve artifacts and failure analysis
- **PR-98: Self-improvement draft PR workflow**
  - create branch / draft PR candidate
  - CI observation
  - no direct merge
- **PR-99: Self-improvement guarded autopilot**
  - bounded loop for low-risk self changes
  - strict stop conditions
  - human approval for medium/high risk
- **PR-100: Self-improving CodeAgentPersonal / KasaneCore milestone**
  - end-to-end validation
  - snapshot → plan → patch → test → fix → draft PR
  - rollback and recovery verified

### Self-improvement Safety Boundary
- Self-improvement has stricter gates than ordinary repository work.
- Core runtime, launcher, Docker, UI, safety policies, execution APIs, and data-root handling are strict-gate by default.
- Autonomous self-modification is forbidden until snapshot/restore, patch transaction, verification, rollback, and artifact capture are validated.
- ThinUI supervises self-improvement; it does not hide safety-critical state.
- Medium/high-risk self-modification requires explicit human approval.
- Direct merge is out of scope until a later explicit policy PR.

- Diagnostics remain accessible through toggles and are hidden by default, not removed.


## UI Anti-divergence Policy
- See `docs/atlas_vue_migration_plan.md` for PR-80 migration architecture checkpoint and Go/No-Go switching criteria.
- See `docs/atlas_autonomous_first_ui_policy.md` for surface classification and cleanup/deprecation policy.
- Final autonomous code-agent and self-improvement roadmap remains unchanged.

## PR-76C Checkpoint Notes

- PR-76C fixes Diagnostics drawer structure after PR-76B.
- Diagnostics drawer is structurally bounded and does not wrap minimal workflow surfaces.
- Diagnostics section IDs exist and are manifest-covered.
- Raw JSON/result panels are diagnostics surfaces.
- Direct subsystem tools are diagnostics surfaces.
- Low-level ID fields are diagnostics surfaces where practical.
- PR-80 remains an out-of-order architecture checkpoint and does not imply PR-77〜79 are complete.
- Backend workflow state is authoritative.
- Execution semantics remain unchanged.
- EXECUTE ONE ACTION remains required for manual execution.
- Dry-run-first remains required.


- PR-77 adds workflow state machine UI for the automation-first shell.
- Workflow primary CTA is derived from existing state.
- Primary CTA may trigger at most one existing manual action per click.
- Primary CTA does not auto-continue.
- Primary CTA does not execute all.
- Primary CTA does not bypass dry-run-first.
- Primary CTA does not bypass EXECUTE ONE ACTION.
- Backend workflow state remains authoritative.
- ThinUI remains replaceable and CLI-compatible.
- PR-80 remains an out-of-order architecture checkpoint and does not imply PR-78〜79 are complete.
- Atlas final goal remains a fully autonomous code agent.
- Self-improving CodeAgentPersonal / KasaneCore remains explicitly in scope.
- Execution semantics remain unchanged.
