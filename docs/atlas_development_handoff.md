## Active PR Pointer (Updated)

Completed:
- PR-ATLAS-SCALE-72

Current PR:
- PR-ATLAS-SCALE-72

Next PR:
- PR-ATLAS-SCALE-73: Atlas autonomous execution readiness checkpoint and roadmap consolidation

Known Current Code Facts:
- Operator Loop uses verification recommendation handoff metadata for manual approval summary context.
- Verification Recommendation handoff metadata is advisory-only and manual approval context only.
- Suggested commands are never executed.
- Confirmation requirement remains unchanged (`EXECUTE ONE ACTION`).
- Missing handoff metadata is non-blocking.
- No tests/shell/verification/safe_apply/patch generation/retry/rollback/remote git are executed by handoff metadata.

# Atlas Development Handoff

## 1. Current Status

- Completed:
  - PR-ATLAS-PIPE-0〜60D
  - PR-ATLAS-SCALE-61〜63B
  - PR-ATLAS-DOCS-ROADMAP-01
  - PR-ATLAS-DOCS-ROADMAP-02
- Current capability:
  - Guarded semi-auto Operator Loop
  - Repo Index
  - Repo Context
  - Planner packaging
  - impacted-test recommendation
- Not yet implemented:
  - automatic verification execution
  - rollback/snapshot transaction
  - full autonomous coding
  - GitHub write automation
  - self-improvement automation

## 2. Current Safety Boundaries

- no execute all
- no auto continue
- no shell=True
- no remote git
- no automatic safe_apply
- no automatic verification
- no automatic retry
- no automatic patch generation
- no automatic test execution
- human confirmation required for execution

## 3. Current PR Pointer (Historical)

Historical completed PR markers:
- PR-ATLAS-SCALE-68 (historical completed)
- Historical marker: PR-ATLAS-SCALE-63B

Current docs PR:
- PR-ATLAS-DOCS-ROADMAP-02

Next implementation PR (historical):
- PR-ATLAS-SCALE-70 (completed historical marker)

Known limitation:
- PR-64 verification hints are still global-ish; PR-65 will map hints per PlanItem more precisely.

Future autonomous PR range:
- PR-73〜82

## 4. Development Restart Instructions

You are continuing development of CodeAgentPersonal / KasaneCore Atlas.

Before making changes:

1. Read docs/atlas_development_handoff.md
2. Read docs/atlas_scale_master_roadmap.md
3. Read docs/atlas_unified_autopilot_checkpoint.md
4. Confirm the latest merged PR on GitHub
5. Inspect main branch files directly before trusting PR body text
6. Do not assume a previous PR fully implemented its stated changes
7. Verify actual files, tests, and runtime wiring

Current next PR (historical, stale pointer removed):
PR-ATLAS-SCALE-70 (historical)

Hard safety rules:

* no execution semantics change unless explicitly requested
* no shell=True
* no remote git
* no auto safe_apply
* no auto verification
* no execute all
* no auto continue
* no Path("ca_data") direct writes
* preserve classic script contract
* update checkpoint docs after every PR

## 5. Verification Checklist for Every PR

- Check recent PR body
- Check actual main files
- Check missing helper/binding mismatch
- Check cache bust if JS/UI changed
- Check root/data_root usage
- Check no Path("ca_data")
- Check no import/export in classic JS
- Check docs Current PR / Next PR
- Run targeted pytest
- Run node --check for modified JS

## 6. Required Final PR Report Format

Every PR response must include:
- Completed PR
- Current PR
- Next PR
- Files changed
- Tests run
- Known limitations
- Safety confirmation
- Whether follow-up PR is required

## Atlas Constitution / Checklist Reference Update

- docs/atlas_development_constitution.md
- docs/atlas_preflight_checklist.md
- docs/atlas_postflight_checklist.md
- docs/atlas_pr_template.md
- docs/atlas_self_development_rules.md

Current PR:
- PR-ATLAS-DOCS-CONSTITUTION-01

Next PR:
- PR-ATLAS-SCALE-64: Use repo context for verification planning and CI/test selection hints without auto execution

Known Current Code Facts:
- Atlas development must follow constitution/preflight/postflight docs.
- Future self-development requires snapshot/restore foundation before autonomous modification.



## PR-ATLAS-SCALE-64
- Completed: PR-ATLAS-SCALE-64
- Current PR: PR-ATLAS-SCALE-66B
- Next PR (historical): PR-ATLAS-SCALE-70 (completed)
- Verification planning is advisory-only.
- Suggested commands are never executed.
- CI/test selection hints are local metadata only.
- Missing Repo Index remains non-blocking.
- No GitHub CI fetching or GitHub write operations are introduced.


## Atlas Quality Gate Update

- Future Atlas PRs must follow runtime-chain contract-test rules.
- String-only tests are insufficient.
- UI features must verify DOM → API helper → dashboard binding → endpoint → response unwrap → render target.
- Backend features must verify router → endpoint → request-aware data_root → service injection → response shape.
- Every PR must include adversarial self-review.

Current PR:
- PR-ATLAS-DOCS-QUALITY-GATE-01

Next PR:
- PR-ATLAS-SCALE-65B: Fix verification-plan UI binding and strengthen PR-64 contracts


- Context Refresh v2 uses PlanItem Impact Map.
- advisory-only
- no execution

- Next PR (historical): PR-ATLAS-SCALE-70 (completed)

- Next PR pointer updated to PR-ATLAS-SCALE-69 for verification recommendation handoff metadata.


## PR-ATLAS-SCALE-72 Update
- Operator Loop action contract includes verification_recommendation_handoff metadata.
- Operator Loop UI displays verification handoff summary for manual approval context.
- Operator Loop UI can copy/export verification handoff JSON.
- Copy/export is manual-only and does not execute anything.
- Handoff metadata is advisory-only.
- Suggested commands are not executed.
- Confirmation requirement remains unchanged.
- `EXECUTE ONE ACTION` remains required for execution.
- Dry-run-first remains required.
- Missing handoff metadata remains non-blocking.
- No tests, shell, verification, safe_apply, patch generation, retry, rollback, or remote git are triggered by handoff metadata or copy/export.

- copy/export is manual-only.
- Suggested commands are not executed.
- Confirmation requirement remains unchanged.
- Dry-run-first remains required.
