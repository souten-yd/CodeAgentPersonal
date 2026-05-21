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
- Atlas remains targeted at a fully autonomous code agent.
- Self-improving CodeAgentPersonal / KasaneCore remains explicitly in scope.
- ThinUI is the frontend strategy for autonomous and self-improving behavior, not a replacement for the final goal.
- PR-74 added the automation-first ThinUI / CLI-compatible workflow shell.
- PR-75 hides advanced execution panels by default.
- Minimal workflow shell remains visible by default.
- Existing advanced execution and diagnostic tools remain accessible.
- Execution semantics remain unchanged.
- `EXECUTE ONE ACTION` remains required for manual execution.
- Dry-run-first remains required.
- Suggested commands are not executed automatically.

# Atlas Autopilot Current Status

## Current
- PR-ATLAS-SCALE-76 completed diagnostics isolation baseline; PR-ATLAS-SCALE-76B finalizes drawer, manifest, docs, and tests.
- Focus: hide diagnostics/raw JSON/low-level IDs and direct subsystem controls from minimal mode while keeping accessibility via Diagnostics mode.
- No execution semantics changes.

## Why UI Simplification Is Needed
- Current UI exposes too many advanced execution controls by default.
- Normal workflow surfaces and diagnostic/internal controls are mixed.
- ThinUI staging is required before safe/autonomous phases can be made broadly usable.

## Historical (Clearly Historical)
- Completed baseline remains: PR-ATLAS-PIPE-0〜60D, PR-ATLAS-SCALE-61〜72.


- Historical quality gate reference: PR-ATLAS-DOCS-QUALITY-GATE-01.
- Historical quality marker: PR-ATLAS-SCALE-65B.

- Diagnostics remain accessible through toggles and are hidden by default, not removed.

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
