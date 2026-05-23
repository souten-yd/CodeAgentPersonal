- PR-ATLAS-SCALE-105 completed: local-only readiness metadata history diff export/copy for currently computed and filtered diff results; browser-local/display-only; no metadata upload; no backend mutation; no readiness decision; no execution eligibility computation; no execution controls; runtime remains level_0_manual_only; Level-1/autonomous execution remain disabled; backend workflow_state remains authoritative; Vue execution capability remains none.
- PR-ATLAS-SCALE-102 completed: local-only readiness metadata history import/export (browser storage only), with local JSON validation and merge/replace options; no metadata upload; no backend mutation; no readiness decision; no execution eligibility computation; no execution controls; runtime remains level_0_manual_only; Level-1/autonomous execution remain disabled; backend workflow_state remains authoritative; Vue execution capability remains none.
- PR-ATLAS-SCALE-100 completed: local display-only readiness metadata snapshot comparison (current vs saved/pasted local snapshot), advisory-only, local-only, no backend mutation/upload, no readiness decision, no execution eligibility computation, no execution controls; runtime remains level_0_manual_only; Level-1/autonomous execution remain disabled.
- PR-ATLAS-SCALE-99 completed: local display-only copy/export of already-fetched Level-1 readiness metadata for operator review; local-only and non-mutating; no readiness decisions; no execution eligibility computation; no execution controls; runtime remains level_0_manual_only; Level-1/autonomous execution remain disabled.
- PR-ATLAS-SCALE-98 completed.
- PR-ATLAS-SCALE-97 completed: read-only UI display for Level-1 readiness gate-source mapping via GET diagnostics only; no execution controls; runtime remains level_0_manual_only; Level-1/autonomous execution remain disabled.
- PR-ATLAS-SCALE-94 completed: disabled backend skeleton contract only; no execution endpoint exposure; runtime remains level_0_manual_only; Level-1/autonomous execution remain disabled.
- PR-ATLAS-SCALE-95 completed: GET-only Level-1 readiness diagnostics for disabled backend skeleton metadata; no execution endpoint exposure; runtime remains level_0_manual_only; Level-1/autonomous execution remain disabled.
- Diagnostics are metadata-only.
# Atlas Autonomous Execution Readiness Policy

## Purpose
- This document defines readiness requirements before Atlas may move from guarded manual / semi-auto operation toward autonomous execution.
- This policy does not enable autonomous execution.
- This policy does not change runtime behavior.
- This policy exists to prevent premature automation.

## Current Execution Boundary
- Completed automation PR: PR-ATLAS-SCALE-105
- Current automation track: PR-ATLAS-SCALE-106
- Historical marker preserved for compatibility: Current automation track: PR-ATLAS-SCALE-105
- Next automation track: PR-ATLAS-SCALE-106
- Historical marker preserved for compatibility: Next automation track: PR-ATLAS-SCALE-105
- PR-ATLAS-SCALE-93 defined Level-1 guarded execution design only.
- PR-ATLAS-SCALE-94 added disabled backend skeleton only (no execution enable, no runtime level change, no Vue execution controls).
- Level-1 execution remains disabled.
- Runtime remains level_0_manual_only.
- Autonomous execution remains disabled.
- Backend workflow_state remains authoritative.
- Vue defaultization remains guarded and not execution-enable.
- Vue execution capability remains none.


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

## Self-Improvement Gate (PR-91 Consolidation)
- Self-improvement is explicitly in scope for the final Atlas / KasaneCore goal.
- PR-91 adds a metadata-only self-improvement gate foundation.
- PR-91 does not perform self-modification.
- autonomous self-improvement remains disabled.
- automatic self-modification remains disabled.
- self-modification is strict-gate by default.
- runtime, execution semantics, safety policy, autonomous controls, remote git policy, data_root, and UI workflow state are strict-gate by default.
- Self-improvement readiness requires evidence for snapshot, patch transaction, risk classification, verification allowlist, dry-run approval, rollback readiness, artifact capture, stop gate, loop bound, and remote git gate.
- self_improvement_gate_ready does not authorize automatic execution.
- self_improvement_gate_ready does not authorize patch apply.
- self_improvement_gate_ready does not authorize git operations.
- requested_operation must be none for remote git readiness.
- invalid or unreadable reference manifests block remote git readiness.
- Atlas remains Level 0 manual-only.


## PR-ATLAS-SCALE-91B Checkpoint Update

Completed PR: PR-ATLAS-SCALE-91B.
Current implementation PR: PR-ATLAS-SCALE-92: Readiness gate rollup / Level-0 completion checkpoint.
Next implementation PR: PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint.
PR-91B fixes self-improvement gate integration wiring and evaluated-payload persistence.
PR-91C fixes the final self-improvement manifest contract drift.
self_improvement_scope is self_improving_codeagentpersonal_kasanecore.
final_goal remains fully_autonomous_code_agent.
Invalid or unreadable referenced manifests block self-improvement readiness.
Self-improvement gate is metadata-only and does not modify code, generate patches, apply patches, run safe_apply, run tests or verification, or run git commands.
Autonomous self-improvement remains disabled; automatic self-modification remains disabled; self-modification is strict-gate by default.
self_improvement_gate_ready does not authorize automatic execution, patch apply, or git operations.
Automatic command execution, patch generation, patch apply, safe_apply, verification, restore, rollback, loop execution, and retry remain disabled.
auto-continue remains disabled; execute-all remains forbidden; autonomous execution remains disabled.
Atlas runtime remains Level 0 manual-only and primary CTA remains single existing manual action only.


- Vue implementation has not started in this PR series.


## PR-ATLAS-SCALE-92 Level-0 Completion Checkpoint
- PR-ATLAS-SCALE-92 completed the Level-0 metadata-only readiness foundation via readiness gate rollup.
- Level-0 completion checkpoint is metadata-only and does not enable Level-1 execution.
- Level-0 completion does not authorize autonomous execution, patch generation/apply, safe_apply, verification execution, rollback/restore, or git operations.
- Runtime remains Level 0 manual-only.
- Current implementation PR is PR-ATLAS-SCALE-93: Level-1 guarded execution design checkpoint.
- Vue implementation is allowed only after PR-92 is merged and has not started in PR-92.
- Separate UI track after merge: PR-ATLAS-VUE-01 read-only parallel UI track; existing ui.html remains default and backend workflow_state remains authoritative.
- PR-80 remains Vue migration planning checkpoint and did not add Vue runtime code.
- automatic command execution disabled; automatic verification disabled; automatic patch generation disabled; automatic patch apply disabled; automatic safe_apply disabled; automatic rollback disabled; automatic restore disabled; automatic loop execution disabled; automatic retry disabled; auto-continue disabled; execute-all forbidden; autonomous execution disabled; autonomous self-improvement disabled; remote git disabled; direct merge forbidden; primary CTA remains single existing manual action only.

## PR-ATLAS-SCALE-93 Level-1 Guarded Execution Design Checkpoint

SCALE-93 is a design-only checkpoint. Runtime remains `level_0_manual_only` and no execution/autonomous behavior is enabled in this PR.

### Level-1 boundary (defined, not enabled)
- Guarded single-step execution candidate only
- Exactly one action at a time
- Low-risk only
- Dry-run-first is mandatory
- Explicit human approval token is mandatory
- Backend-owned execution authority only
- Vue has no execution authority
- No auto-continue
- No execute-all
- No autonomous loop
- No remote git push/merge
- No self-modification execution
- No Level-2 behavior

### Required Level-1 gates before any implementation
Each gate must include: status, owner/source, required evidence, blocking reason when unsatisfied, and test requirement.

| Gate | Status | Owner/Source | Required evidence | Blocking reason (if unmet) | Test requirement |
|---|---|---|---|---|---|
| Snapshot/restore readiness | required_not_satisfied | backend services/policy | Snapshot manifest + restore plan under data_root | Cannot safely recover workspace | contract + integration coverage |
| Patch transaction readiness | required_not_satisfied | patch transaction service | Transaction metadata + rollback metadata linkage | Cannot trace or recover mutation intent | service + manifest contracts |
| Risk classification readiness | required_not_satisfied | risk classification policy | Deterministic low/medium/high/strict classification evidence | Cannot constrain to low-risk-only | risk classification contracts |
| Dry-run proof readiness | required_not_satisfied | dry-run gate policy | Successful dry-run record bound to candidate action | Execute without proof is forbidden | dry-run gate tests |
| Explicit approval token readiness | required_not_satisfied | approval gate policy | Human approval token/record tied to action | No human authorization for mutation | approval gate tests |
| Allowlisted verification readiness | required_not_satisfied | verification allowlist policy | Allowed verification plan + command compliance | Verification could become arbitrary execution | allowlist contracts |
| Rollback readiness | required_not_satisfied | rollback readiness policy | Snapshot + rollback strategy + restore references | No safe restoration path | rollback readiness tests |
| Artifact capture readiness | required_not_satisfied | artifact capture policy | Persisted run artifacts and warnings | Audit/replay evidence missing | artifact capture tests |
| Stop/kill switch readiness | required_not_satisfied | stop gate policy | Explicit stop controls + blocked auto-continue | Unsafe inability to halt | stop gate contracts |
| Loop bound readiness | required_not_satisfied | loop-bound policy | Max actions/retries/runtime/failures bounds | Unbounded automation risk | loop-bound contracts |
| Remote git restriction readiness | required_not_satisfied | remote git gate policy | Policy evidence that push/merge stays forbidden | Potential external side effects | remote git gate tests |
| Self-improvement gate readiness | required_not_satisfied | self-improvement gate policy | Scope + strict gate evidence with no auto mutation | Self-modification could bypass safety | self-improvement gate tests |
| Audit log readiness | required_not_satisfied | audit/reporting policy | Immutable run/decision log references | Post-incident traceability gap | audit log contracts |
| data_root/path safety readiness | required_not_satisfied | path safety policy | Normalized/contained paths + escape protection | File safety boundary can be violated | path safety tests |
| Forbidden command execution policy | required_not_satisfied | command safety policy | Blocklist/allowlist proof for forbidden operations | Dangerous commands may run | policy regression tests |
| Backend authority enforcement | required_not_satisfied | backend workflow contract | workflow_state marks backend authoritative | Authority drift into UI | contract tests |
| UI non-authority enforcement | required_not_satisfied | Vue client + manifest policy | Vue endpoints remain read-only + planning metadata only | UI could trigger execution | client/manifest regression tests |



- SCALE-95 added GET-only Level-1 readiness diagnostics only.
- No execution endpoint is exposed.
- Backend workflow_state remains authoritative.
- Vue execution capability remains none.
- SCALE-96 may add deeper gate-source mapping/readiness evidence, not execution enable.


- PR-ATLAS-SCALE-96 completed.
- SCALE-96 added metadata-only gate-source mapping / evidence summary.
- No execution endpoint is exposed.
- Level-1 execution remains disabled.
- Runtime remains level_0_manual_only.
- Autonomous execution remains disabled.
- Backend workflow_state remains authoritative.
- Vue execution capability remains none.
- Next PR may add readiness UI display for gate-source mapping, not execution enable.

- SCALE-97 may add readiness UI display for gate-source mapping, not execution enable.

- next work is PR-ATLAS-SCALE-106

- SCALE-99 may add export/copy metadata or another display-only refinement, not execution enable.

Completed automation PR: PR-ATLAS-SCALE-99
Current automation track: PR-ATLAS-SCALE-100
Next automation track: PR-ATLAS-SCALE-100
Completed automation PR: PR-ATLAS-SCALE-95
Completed automation PR: PR-ATLAS-SCALE-96
Completed automation PR: PR-ATLAS-SCALE-97
Completed automation PR: PR-ATLAS-SCALE-98
Current automation track: PR-ATLAS-SCALE-96
Current automation track: PR-ATLAS-SCALE-98
Current automation track: PR-ATLAS-SCALE-99
## SCALE-101 Update (local history only)
- PR-ATLAS-SCALE-101 completed: local browser-storage readiness metadata history only; browser-storage-only, no backend mutation/upload, no readiness decision, no execution eligibility computation, no execution controls; runtime remains level_0_manual_only; Level-1/autonomous execution remain disabled.
- Completed automation PR: PR-ATLAS-SCALE-105
- Current automation track: PR-ATLAS-SCALE-106
- Next automation track: PR-ATLAS-SCALE-106
- History is local-only and does not mutate backend.
- History does not upload metadata.
- History does not decide readiness.
- History does not compute execution eligibility.
- UI adds no execution controls and exposes no execution endpoint.
- Level-1 execution remains disabled.
- Runtime remains level_0_manual_only.
- Autonomous execution remains disabled.
- Backend workflow_state remains authoritative.
- Vue execution capability remains none.
- Next PR may add local-only history import/export refinement, not execution enable.


- Next PR may add local-only history diff view, and must not enable execution.

- Historical marker preserved for compatibility: Completed automation PR: PR-ATLAS-SCALE-101

- Historical marker preserved for compatibility: 
- Historical marker preserved for compatibility: Next automation track: PR-ATLAS-SCALE-102


- PR-ATLAS-SCALE-104 completed.
- SCALE-103 adds a local-only readiness metadata history diff view (browser-local display only).
- The history diff view does not upload metadata, does not mutate backend state, does not decide readiness, and does not compute execution eligibility.
- UI adds no execution controls and exposes no execution endpoint; Level-1 execution remains disabled.
- Runtime remains level_0_manual_only; autonomous execution remains disabled; backend workflow_state remains authoritative; Vue execution capability remains none.
- Next PR may add local-only diff export and must not enable execution.


## Current Atlas Vue UI Track State

- Completed UI PRs: PR-ATLAS-VUE-01 through PR-ATLAS-VUE-21
- Current UI track: Vue defaultization complete
- Planned UI track: return to PR-ATLAS-SCALE-106 automation track
- Historical marker preserved for compatibility: Planned UI track: return to PR-ATLAS-SCALE-105 automation track
- Current automation track: PR-ATLAS-SCALE-106
- Next automation track: PR-ATLAS-SCALE-106
- next work is PR-ATLAS-SCALE-106
- runtime remains level_0_manual_only
- Vue execution capability remains none
- Backend workflow_state remains authoritative

- Historical marker preserved for compatibility: Current automation track: PR-ATLAS-SCALE-104.
- Historical marker preserved for compatibility: Next automation track: PR-ATLAS-SCALE-104.

- Historical marker preserved for compatibility: Current automation track: PR-ATLAS-SCALE-105
- Historical marker preserved for compatibility: Next automation track: PR-ATLAS-SCALE-105
- Historical marker preserved for compatibility: next work is PR-ATLAS-SCALE-105