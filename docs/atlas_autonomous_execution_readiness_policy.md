# Atlas Autonomous Execution Readiness Policy

## Canonical relationship

This file is the canonical safety and level-advancement policy for Atlas automation.

The canonical implementation roadmap is `docs/atlas_scale_master_roadmap.md`.
The machine-readable phase contract is `docs/atlas_automation_phase_manifest.json`.

Do not duplicate active/current/next PR pointers in additional planning files. Any future handoff or UI migration note must link to the master roadmap instead of copying its PR table.

## Current execution boundary

- Completed automation PR: PR-ATLAS-SCALE-141
- Current automation track: PR-ATLAS-SCALE-142
- Next automation track: PR-ATLAS-SCALE-142
- Current level: Level 3 autonomous implementation loop candidate
- Target level: Level 3 autonomous implementation loop candidate
- Next level advancement checkpoint: PR-ATLAS-SCALE-146
- Final goal: fully autonomous code agent
- Self-improvement goal: self-improving CodeAgentPersonal / KasaneCore platform

PR-ATLAS-SCALE-141 adds strict self-modification risk classification. It is limited to backend-only classification metadata for an approved self-improvement proposal. A classification may record target repo, target area, proposal risk, final classification, strict gate requirement, and required next gates.

The classifier does not perform execution, mutate project files, preview patches, generate patches automatically, apply patches, run verification, create branches, create or update PRs, run retry, rollback or restore automatically, use remote git, auto-continue, execute-all, direct merge, self-apply, self-modify, add a public execution route, or enable Vue authority.

PR-ATLAS-SCALE-128 through PR-ATLAS-SCALE-141 completed the patch proposal, patch transaction preview, approved single patch apply, local branch artifact, local branch creation, draft PR policy, manually approved draft PR creation, manually approved PR update, bounded loop policy, bounded retry/failure metadata, explicit Level-2 checkpoint, Level-3 candidate contract, self-improvement proposal mode, and strict self-modification risk classifier. These steps do not enable unbounded autonomous execution, execute-all, direct merge, Vue authority, self-modification, or remote git push.

Patch preview remains disabled after the strict self-modification risk classifier.

## Contract phrase lock

This policy does not enable unbounded autonomous execution. Current Atlas state is Level 3 autonomous implementation loop candidate with proposal-only self-improvement metadata and classification-only self-modification risk metadata. Future PRs must explicitly move levels.

- Backend workflow state is authoritative.
- ThinUI remains supervision layer.
- CLI should use the same backend workflow contract.
- allowlist does not execute commands.
- recommended commands remain suggestions only.
- no arbitrary command execution.
- explicit approval is mandatory for medium/high/strict risk.
- EXECUTE ONE ACTION remains required for single-step actions.
- strict_gate always requires explicit approval.
- gate readiness does not execute automatically.
- restore plan is required and must be valid.
- restore remains manual-only.
- automatic rollback requires a future explicit policy PR.
- plan / intent summary, patch transaction manifest, dry-run result, execution result, verification plan, verification result, warnings and recovery instructions, and resolved data_root are required evidence classes.
- artifact capture does not create fake execution results.
- artifact capture does not create fake verification results.
- missing references are recorded explicitly.
- stop state must be visible in ThinUI/CLI.
- stop metadata does not stop real jobs or kill processes.
- self-improvement proposal and risk classifier modes are metadata-only; autonomous self-improvement remains disabled; automatic self-modification remains disabled; self-modification is strict-gate by default.
- Level 1: Guarded single-step automation.
- Level 2: Guarded bounded loop.
- Level 3: Autonomous implementation loop candidate.
- execute all remains forbidden.
- auto continue remains forbidden.
- automatic safe_apply, automatic verification, automatic retry, automatic rollback, and automatic patch generation remain disabled.
- no git push, no git pull, no git clone, no git fetch, no git remote, no direct merge, and no automatic PR creation.
- draft PR creation and PR update remain manually gated through dedicated backend helpers; automatic PR creation, automatic PR update, and direct merge remain forbidden.
- max actions per loop, max retries, max runtime, max files changed, and max risk level are mandatory.
- No unbounded autonomous loop.
- Auto-continue remains disabled.
- Execute-all remains forbidden.

## Non-negotiable safety invariants

After PR-ATLAS-SCALE-141:

- runtime remains level_3_autonomous_implementation_loop_candidate
- strict self-modification risk classifier is classification-only
- strict self-modification risk classifier requires an approved self-improvement proposal
- patch preview remains disabled until PR-ATLAS-SCALE-142
- self-modification remains disabled
- self-apply remains disabled
- autonomous loop execution remains disabled
- autonomous execution remains disabled
- backend workflow_state remains authoritative
- Vue remains non-authoritative and display-only
- suggested commands are not executed automatically
- verification recommendations remain advisory unless selected through explicit gated execution
- safe_apply remains manually gated
- automatic patch generation remains disabled
- automatic patch apply remains manually gated
- automatic verification remains disabled
- automatic retry remains disabled
- automatic rollback remains disabled
- execute-all remains forbidden
- auto-continue remains forbidden
- git push/pull/clone remains forbidden
- direct merge remains forbidden
- automatic PR creation and automatic PR update remain forbidden

## Completed Readiness Metadata Review Phase

SCALE-100 through SCALE-112 completed the local-only readiness metadata review phase. That phase is now closed.

Those PRs may remain as operator review tools, but they are not the mainline path to complete automation. Future mainline work must advance the canonical automation track unless the user explicitly authorizes a PR-B repair or a narrowly scoped exception.

## Readiness gates before autonomous execution

Autonomous execution remains forbidden until the relevant gates pass.

1. Snapshot / Restore Gate
   - workspace snapshot exists before mutation
   - restore is validated
   - restore proof is captured
   - snapshot manifest is stored under resolved data_root
   - no direct Path("ca_data") writes

2. Patch Transaction Gate
   - proposed changes are represented as patch transactions
   - transaction has file list, diff summary, risk class, and rollback metadata
   - transaction can be dry-run validated before apply
   - transaction artifacts are captured

3. Risk Classification Gate
   - each action has explicit risk classification
   - unknown risk is not low risk
   - runtime, launcher, Docker, execution APIs, data_root, safety docs, UI workflow state, and self-modification are strict-gate by default

4. Verification Allowlist Gate
   - verification commands must be selected from an allowlist
   - allowlist resolution alone does not execute commands
   - no broad shell, arbitrary command execution, shell metacharacters, remote git, package install, or destructive commands

5. Dry-run and Approval Gate
   - dry-run-first is mandatory
   - explicit approval token is mandatory before guarded execution
   - human approval is mandatory for medium/high/strict risk
   - self-modification requires stricter gates than ordinary repo work

6. Rollback Readiness Gate
   - rollback plan exists
   - restore plan is valid
   - snapshot manifest and rollback metadata are required
   - rollback readiness verification does not execute rollback unless a later explicit PR allows it

7. Artifact Capture Gate
   - plan, snapshot, patch transaction, rollback metadata, risk classification, verification allowlist, dry-run approval, and rollback readiness records are captured
   - dry-run, execution, verification plan, and verification result references are tracked when available
   - missing evidence is recorded explicitly and not fabricated

8. Stop / Kill Switch Gate
   - stop state is visible
   - no auto-continue after stop
   - stop blocks continuation

9. Loop Bound Gate
   - max actions, retries, runtime, files changed, risk level, verification attempts, failures, and patch transactions are bounded
   - no unbounded autonomous loop

10. Remote Git Gate
   - no git push/pull/clone before a dedicated policy and implementation gate
   - no direct merge
   - draft PR creation and PR update remain manually gated until later automation levels explicitly expand them

11. Self-Improvement Gate
   - CodeAgentPersonal / KasaneCore self-modification is stricter than ordinary repo work
   - launcher, Docker, runtime, UI, execution APIs, data_root, and policy docs are strict-gate by default

## Readiness levels

### Level 0: Manual only

Historical baseline. No autonomous execution.

### Level 1: Guarded single-step automation

One low-risk, allowlisted action at a time. Dry-run first. Explicit approval token required. No auto-continue.

### Level 2: Guarded bounded loop

Limited low-risk sequence with hard loop bounds, captured artifacts, allowlisted verification, stop gate, and human approval for each iteration.

### Level 3: Autonomous implementation loop candidate

Current state. Candidate metadata can describe plan, patch proposal, dry-run request, artifact evaluation, draft PR update metadata, human approval requests, self-improvement proposals, and self-modification risk classification. It cannot execute commands, preview patches, apply patches, run verification, retry, update PRs, push branches, merge, self-apply, self-modify, or let Vue authorize workflow state.

### Level 4: Self-improvement candidate

Atlas may improve CodeAgentPersonal / KasaneCore itself under stricter self-modification gates, draft PR only, no direct merge.

## Anti-drift requirements

Every future automation PR must prove the following:

- It matches the PR row in `docs/atlas_scale_master_roadmap.md`.
- It does not add another local-only readiness decoration as mainline work after SCALE-113.
- It does not recreate deleted duplicate planning files.
- It does not change runtime level before the planned transition PR.
- It does not add execution, mutation, patch apply, remote git push, autonomous loop execution, automatic PR creation, direct merge, or self-modification before the scheduled PR.
- PR-B changes are repair-only and point back to the parent PR acceptance criteria.

## Confirmation checklist

When verifying a PR, report:

- implemented
- missing
- implementation defects
- over-implementation / forbidden changes
- safety
- next required instruction

This checklist must be based on actual main-branch files, manifest, tests, runtime contract, and PR diff when needed, not only the PR body.
