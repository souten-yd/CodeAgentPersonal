# Atlas Autonomous Execution Readiness Policy

## Purpose
- This document defines readiness requirements before Atlas may move from guarded manual / semi-auto operation toward autonomous execution.
- This policy does not enable autonomous execution.
- This policy does not change runtime behavior.
- This policy exists to prevent premature automation.

## Current Execution Boundary
- Manual execution remains the only allowed execution mode.
- EXECUTE ONE ACTION remains required.
- dry-run-first remains required.
- ThinUI primary CTA may trigger at most one existing manual action per click.
- Primary CTA must not run Build Queue, Preview Token, Advance to confirmation, Execute and refresh, safe_apply, verification, patch generation, retry, or rollback.
- Suggested commands are not executed automatically.
- Verification recommendations remain advisory.
- safe_apply remains manually gated.
- Retry and rollback remain manual unless a future explicit policy PR changes this.

## Autonomous Execution Is Forbidden Until Readiness Gates Pass
1. **Snapshot / Restore Gate**
   - workspace snapshot exists before mutation
   - restore is validated
   - restore proof is captured
   - snapshot manifest is stored under resolved data_root
   - no Path("ca_data") direct writes

2. **Patch Transaction Gate**
   - proposed changes are represented as patch transactions
   - transaction has file list, diff summary, risk class, and rollback metadata
   - transaction can be dry-run validated before apply
   - transaction artifacts are captured

3. **Risk Classification Gate**
   - each action/item has risk classification
   - low-risk / medium-risk / high-risk / strict-gate must be explicit
   - unknown risk is not low risk
   - runtime, launcher, Docker, execution APIs, data_root, safety docs, UI workflow state, and self-modification are strict-gate by default

4. **Verification Allowlist Gate**
   - verification commands must be selected from an allowlist
   - allowlist does not execute commands
   - allowlisted means eligible for future guarded/manual verification only
   - no broad shell
   - no arbitrary command execution
   - no shell metacharacters
   - no remote git
   - no package install
   - no destructive commands
   - no automatic test execution until allowlist and policy gates are satisfied
   - recommended commands remain suggestions only until a future execution policy enables them
   - automatic verification remains disabled

5. **Dry-run and Approval Gate**
   - dry-run-first is mandatory
   - EXECUTE ONE ACTION or future equivalent approval token is mandatory
   - human approval is mandatory for medium/high risk
   - self-modification requires stricter gates than ordinary repo work

6. **Rollback Readiness Gate**
   - rollback plan exists
   - restore plan is required and must be valid
   - snapshot manifest and rollback metadata are required
   - rollback strategy is manual snapshot restore
   - rollback readiness is metadata-only and does not execute rollback
   - restore remains manual-only
   - failed verification must not silently continue
   - automatic rollback requires a future explicit policy PR

7. **Artifact Capture Gate**
   - plan / intent summary, workspace snapshot manifest, patch transaction manifest, rollback metadata, risk classification record, verification allowlist record, dry-run approval gate record, and rollback readiness gate record are required references
   - dry-run result, execution result, verification plan, and verification result references are tracked when available and missing references are recorded explicitly
   - warnings and recovery instructions are captured as explicit lists
   - artifacts must use resolved data_root
   - artifact capture is metadata-only in PR-87 and does not execute actions
   - artifact capture does not create fake execution results
   - artifact capture does not create fake verification results
   - artifacts must be inspectable from future UI/CLI

8. **Stop / Kill Switch Gate**
   - user can stop ongoing autonomous flow
   - stop state is visible in ThinUI/CLI
   - no auto-continue after stop

9. **Loop Bound Gate**
   - max actions per loop
   - max retries
   - max runtime
   - max files changed
   - max risk level
   - no unbounded autonomous loop

10. **Remote Git Gate**
   - no git push
   - no git pull
   - no git clone
   - no direct merge
   - draft PR creation requires a future explicit policy PR

- Risk classification alone does not authorize execution.

11. **Self-Improvement Gate**
   - CodeAgentPersonal / KasaneCore self-modification is stricter than ordinary repo work
   - self-improvement requires snapshot / restore / patch transaction / rollback proof / allowlisted verification / human policy gate
   - launcher / Docker / runtime / UI / execution APIs / data_root / policy docs are strict-gate by default

## Readiness Levels
- Level 0: Manual only
  - current state
  - no autonomous execution

- Level 1: Guarded single-step automation candidate
  - one low-risk action at a time
  - dry-run-first
  - human approval required
  - no auto-continue

- Level 2: Guarded bounded loop candidate
  - limited low-risk sequence
  - hard loop bounds
  - allowlisted verification
  - artifacts captured
  - stop gate required

- Level 3: Autonomous implementation loop candidate
  - plan → patch → dry run → apply → verify → fix
  - bounded retries
  - rollback readiness
  - draft PR only
  - no direct merge

- Level 4: Self-improvement candidate
  - stricter than Level 3
  - applies to CodeAgentPersonal / KasaneCore itself
  - requires all self-improvement roadmap gates

- Current Atlas state remains Level 0.
- This PR does not advance the runtime to Level 1.
- Future PRs must explicitly move levels.

## Required Evidence Before Level Advancement
- passing tests for snapshot/restore
- patch transaction test coverage
- rollback dry run
- allowlisted verification contract
- artifact capture contract
- stop/kill switch contract
- data_root contract
- no forbidden command execution
- primary CTA remains single-action until policy changes
- docs/checkpoint updated

## Forbidden Until Future Explicit PR
- execute all
- auto continue
- automatic safe_apply
- automatic verification
- automatic retry
- automatic rollback
- automatic patch generation
- automatic PR creation
- git push/pull/clone
- direct merge
- self-modification without strict gates

- Atlas final goal remains a fully autonomous code agent and a self-improving CodeAgentPersonal / KasaneCore platform.

## Relationship to ThinUI / CLI
- ThinUI remains supervision layer.
- CLI should use the same backend workflow contract.
- Backend workflow state is authoritative.
- UI must not become the source of execution policy.
- Manifest remains classification source for UI surfaces.

## Relationship to PR-80
- PR-80 was an out-of-order architecture checkpoint.
- PR-80 does not imply autonomous execution readiness.
- PR-80 does not imply PR-79 was complete.
- This PR defines the missing autonomous execution readiness policy checkpoint.


## PR-ATLAS-SCALE-84B Checkpoint Update

Completed PR: PR-ATLAS-SCALE-84B (Fix verification allowlist py_compile / node check contracts).

Current implementation PR:
- PR-ATLAS-SCALE-85: Dry-run and approval gate consolidation

Next implementation PR:
- PR-ATLAS-SCALE-86: Rollback readiness gate consolidation

Known Current Code Facts:
- PR-84B fixes verification allowlist py_compile / node check contracts.
- Verification allowlist is metadata-only and does not execute commands.
- python -m py_compile <safe relative file> is allowlisted metadata only.
- node --check web/js/<safe js file> is allowlisted metadata only.
- Targeted pytest -q tests/<safe test file>.py is allowlisted metadata only.
- Allowlisted means future guarded/manual verification eligibility, not execution authorization.
- Automatic verification remains disabled.
- Automatic command execution remains disabled.
- Automatic safe_apply remains disabled.
- Automatic patch generation remains disabled.
- Automatic patch apply remains disabled.
- Automatic rollback remains disabled.
- Autonomous execution remains disabled.
- Level 0 manual-only remains.
- EXECUTE ONE ACTION remains required.
- Dry-run-first remains required.
- PR-80 remains an out-of-order architecture checkpoint.
- Atlas final goal remains a fully autonomous code agent.
- Self-improving CodeAgentPersonal / KasaneCore remains in scope.

- explicit approval is mandatory for medium/high/strict risk
- strict_gate always requires explicit approval
- confirmation token or future equivalent approval token remains mandatory
- gate readiness does not execute automatically


## Stop / Kill Switch Gate
- user can stop ongoing autonomous flow before any future autonomous mode.
- stop state must be visible in ThinUI/CLI.
- no auto-continue after stop.
- execute-all remains forbidden.
- stop / kill switch gate is metadata-only in PR-88.
- PR-88 does not stop real jobs or kill processes.
- stop acknowledgement must not be fabricated.
- Current Atlas state remains Level 0 manual-only.

## Loop Bound Gate (PR-89)
- PR-89 adds loop bound gate consolidation as a metadata-only gate.
- The loop bound gate does not run loops, does not retry automatically, and does not continue automatically.
- loop_bound_ready does not authorize automatic execution.
- Explicit bounds are required: max actions per loop, max retries, max runtime, max files changed, max risk level, max consecutive failures, max verification attempts, and max patch transactions.
- No unbounded autonomous loop is allowed.
- Auto-continue remains disabled.
- Execute-all remains forbidden.
- Automatic loop execution remains disabled.
- Automatic retry remains disabled.
- Atlas remains Level 0 manual-only.


## Remote Git Gate (PR-90 metadata-only foundation)
- no git push.
- no git pull.
- no git clone.
- no git fetch.
- no git remote.
- no direct merge.
- no automatic PR creation.
- draft PR creation requires a future explicit policy PR.
- Remote git gate is metadata-only in PR-90.
- PR-90 does not run git commands.
- PR-90 does not create branches, PRs, or merges.
- remote_git_gate_ready does not authorize git operations.
- Atlas remains Level 0 manual-only.
