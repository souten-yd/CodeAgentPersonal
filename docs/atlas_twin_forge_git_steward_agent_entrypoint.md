# Atlas Twin / Forge / Git Steward — Agent Entrypoint

Status: proposed agent execution entrypoint.

Use this file when implementing the approved Twin / Forge / Git Steward integration. Follow the repository `AGENTS.md` first, then this file, then the master goal and detailed plan.

## Canonical read order

1. `AGENTS.md`
2. `docs/atlas_twin_forge_git_steward_master_goal.md`
3. `docs/atlas_twin_forge_git_steward_detailed_plan.md`
4. `docs/atlas_twin_forge_git_steward_current_status.md`
5. Existing Project Intelligence docs and contracts
6. Existing Project Twin modules and tests
7. Existing Greenfield modules and tests
8. Existing Forge route modules and tests
9. Target code and direct callers

## Non-negotiable rules

- Reuse existing code before writing replacements.
- Do not create a parallel Greenfield pipeline; integrate it as Genesis.
- Do not mix Twin injection policy into `RouteMatrix`; add ExecutionPolicy above it.
- Local Git operations may run autonomously.
- Remote publication requires approval.
- Preserve Safe Apply and approval boundaries.
- Preserve off/shadow/active rollout behavior.
- Treat unavailable real LLM or runtime evidence as unavailable, not passed.
- Do not call a package complete from unit tests alone.
- Do not weaken tests or gates to make a package pass.
- Do not auto-delete stale tests; mark retirement candidates.

## Recommended implementation workflow

For each package:

1. Read current status and identify the next package.
2. Inspect existing implementation and tests before designing new code.
3. Decide reuse, extend, consolidate, or replace.
4. Add or update contracts first.
5. Add focused tests for contract and policy behavior.
6. Add integration tests for the actual path the package serves.
7. Add adversarial tests.
8. Run targeted tests.
9. Run the smallest relevant integration path.
10. If real LLM or real runtime evidence is required, run it or mark it unavailable.
11. Update current status with exact commands and evidence.
12. Stop before remote publication unless the user approved it.

## Package slicing

Prefer small PR-sized slices:

- Contracts and DTOs.
- Forge ExecutionPolicy selection.
- TwinBrief compilation.
- Instruction compilation.
- Genesis taxonomy and adapter.
- BlastMap and Contract Sentinel.
- TwinProof and Assumption Breaker.
- Git Steward MVP.
- Patch/Integration/Flag/Merge gates.
- Proof Ledger and Repair Compass.
- Real LLM/runtime evaluation harness.
- Atlas pipeline shadow integration.
- Active rollout.

## Required integration path

The final integration path must prove:

```text
User task
  -> Route selection
  -> Model capability profile lookup
  -> ExecutionPolicy
  -> Local Git branch/worktree
  -> Project Intelligence context
  -> TwinBrief
  -> model-specific instruction
  -> Safe Apply
  -> local commit
  -> Twin refresh
  -> Patch Impact / TwinProof gates
  -> Proof Ledger
```

## Real LLM evaluation

Real LLM evaluation is required before acceptance for packages that claim model-facing behavior.

Minimum evidence:

- local model path when available;
- stronger or frontier-assisted path when configured, or unavailable evidence if not configured;
- model id, route, injection level, instruction style, prompt/brief ref, output, and evaluation verdict;
- adversarial prompts covering hard constraints, missing tests, and unsupported Twin overrides.

## Real runtime evaluation

Real runtime evaluation is required before acceptance for packages that claim generation, Genesis, Portal, or Git Steward behavior.

Minimum evidence:

- build/test/run a small representative project or feature;
- record command outputs and runtime observations;
- verify local Git branch/commit/diff refs;
- verify Twin refresh and Proof Ledger entries;
- verify unavailable outcomes are not reported as passed.

## Current package status values

Use these proof levels:

- `not_started`
- `contract_present`
- `component_complete`
- `shadow_connected`
- `production_connected`
- `real_llm_evaluated`
- `real_runtime_evaluated`
- `acceptance_complete`
- `blocked`

Do not use plain `completed` without the proof level.
