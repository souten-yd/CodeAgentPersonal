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
