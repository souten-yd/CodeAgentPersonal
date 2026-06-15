# Atlas Twin / Forge / Git Steward Master Goal

Status: proposed implementation goal.

This document records the approved direction for integrating Project Intelligence, Project Digital Twin, Genesis/Greenfield, Forge route/model evaluation, and local Git development management into one guarded execution control plane.

## Goal

Build an Atlas execution system that chooses the right route, model, Twin assistance level, implementation instruction style, Git isolation policy, and verification gates for each task.

The system must strongly reuse the existing implementation:

- `agent/project_intelligence/*`
- `agent/project_twin/*`
- `agent/project_intelligence/greenfield.py`
- `agent/project_intelligence/greenfield_state_machine.py`
- `agent/model_forge/route_matrix.py`
- `agent/model_forge/route_taxonomy.py`

New code is allowed when existing code cannot satisfy the required contract, but the default strategy is integration, refactoring, and consolidation rather than replacement.

## Core concept

```text
Atlas Twin Control Plane
  + Forge Execution Policy Matrix
  + Atlas Git Steward
```

Together these provide:

1. Project understanding through the existing Project Digital Twin.
2. Route selection through the existing Forge Route Matrix.
3. Model weakness-aware execution through Forge capability profiles.
4. Model-specific TwinBrief and implementation instruction compilation.
5. Safe local Git branch/worktree/commit/rollback management.
6. Patch, integration, flag, merge, proof, and test-debt gates.
7. Real LLM and real runtime evaluation before declaring completion.

## Authority model

Atlas may autonomously manage local Git state:

- initialize local repositories;
- harden `.gitignore`;
- create local branches and worktrees;
- fetch, pull, or clone from remotes;
- create local commits;
- rollback Atlas-owned local changes;
- record branch, diff, commit, and evidence refs.

Atlas must request approval before remote publication or remote mutation:

- pushing to GitHub or another remote;
- creating a remote branch;
- creating a PR;
- pushing tags;
- merging a PR;
- deleting remote refs;
- force-pushing.

## Required product behavior

For every non-trivial Atlas development task, the system should produce an `ExecutionPolicy` containing:

- selected Forge route;
- selected model or model role;
- instruction style;
- Twin injection level;
- required Twin modules;
- required safety and verification gates;
- Git policy;
- reasons and confidence.

Example:

```json
{
  "route": "blueprint_slice",
  "model_id": "local-coder",
  "instruction_style": "interface_first",
  "twin_injection_level": 3,
  "required_twin_modules": ["TwinBrief", "BlastMap", "ContractSentinel", "TwinProof"],
  "required_gates": ["PatchImpactGate", "NoTestWeakening", "FeatureFlagBaseline"],
  "git_policy": {
    "local_branch_required": true,
    "worktree_preferred": true,
    "local_commit_required": true,
    "remote_publish_requires_approval": true
  }
}
```

## Must preserve

- Safe Apply boundaries.
- Approval gates.
- Project isolation.
- Existing rollout semantics: off, shadow, active.
- Existing Forge route taxonomy.
- Existing Greenfield Safe Apply slice behavior.
- Truthful evidence reporting: unavailable is never passed.
- No automatic test weakening.
- No automatic stale test deletion.
- No remote publication without approval.

## Definition of Done

This program is not complete when only unit tests pass. Completion requires:

1. Contract tests for every new public DTO and policy.
2. Integration tests proving Atlas can produce ExecutionPolicy from route + model profile + Twin context.
3. Greenfield/Genesis integration tests that run through branch/worktree, Safe Apply, Twin refresh, verification, and proof recording.
4. Adversarial tests for unsafe route requests, over-restrictive Twin injection, stale test deletion, feature flag omission, dirty working tree protection, and remote publication attempts without approval.
5. Real LLM evaluation using at least one local model path and one stronger/frontier-assisted mock or provider path, recording whether the expected instruction style and answer structure are produced.
6. Real runtime evaluation where a generated or modified small project is built/tested/run through the normal Atlas/Portal/Greenfield entrypoint where available.
7. Shadow-mode evidence before active rollout.
8. Documentation updated with known limitations and rollback instructions.

## Completion language

Use explicit proof levels:

- `contract_present`
- `component_complete`
- `shadow_connected`
- `production_connected`
- `real_llm_evaluated`
- `real_runtime_evaluated`
- `acceptance_complete`

Do not mark a package `acceptance_complete` from focused tests alone.
