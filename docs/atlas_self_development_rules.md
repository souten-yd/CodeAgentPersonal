# Atlas Self-Development Rules

目的:
将来AtlasがCodeAgentPersonal/KasaneCore自身を改修する際の安全ルール。

## 1. Self-Modification Principle

Atlas may improve itself only under stricter rules than normal project edits.

## 2. Required Before Self-Modification

必須:
- workspace snapshot
- restore point
- before hash manifest
- changed files manifest
- rollback plan
- test plan
- human approval

## 3. Strict Gate Files

以下は常にhigh-risk:
- main.py
- app/server.py
- app/api/*
- agent/*
- web/js/*
- ui.html
- Dockerfile
- start scripts
- launcher scripts
- requirements files
- model loading logic
- TTS/ASR runtime logic
- data root / storage logic
- rollback/snapshot logic

## 4. Self-Development Forbidden Until PR-73+

禁止:
Until snapshot/restore foundation exists:
- full autonomous self-modification
- auto safe_apply to own repo
- auto verification loop that modifies own repo
- auto rollback
- auto GitHub PR creation

## 5. Required Transaction Model

将来PR-73以降で必須:
- create snapshot
- apply patch transactionally
- run verification
- compare before/after manifest
- if failure, restore snapshot
- write recovery artifact

## 6. Human Approval

Always required for:
- core runtime changes
- storage/root changes
- execution policy changes
- rollback/snapshot changes
- GitHub write operations


## Self-Improvement Roadmap Boundary
- CodeAgentPersonal / KasaneCore self-modification is a first-class future goal.
- Self-modification is stricter than ordinary target repo work.
- The following are strict-gate by default:
  - launcher
  - Dockerfile / container build scripts
  - runtime startup
  - execution APIs
  - safe_apply / verification / rollback code
  - UI workflow state machine
  - data_root / CA_DATA resolution
  - security / policy / safety docs
- Autonomous self-modification requires:
  - snapshot
  - restore
  - patch transaction
  - allowlisted verification
  - rollback proof
  - artifact capture
  - human policy gates
- No direct merge / push / remote git write until an explicit future policy PR.

## PR-91 Self-Improvement Gate Boundary
- Self-improving CodeAgentPersonal / KasaneCore remains explicitly in scope.
- No autonomous self-modification is allowed at Level 0.
- Strict-gate applies to self-modification-sensitive files and runtime/policy/control boundaries.
- Patch generation, patch apply, verification, and rollback remain manual-only unless a future explicit policy PR enables them.
- Remote git and direct merge remain forbidden.
- Self-improvement gate records are evidence-only metadata and do not execute actions.


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
