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

## 3. Current PR Pointer

Current completed PR:
- PR-ATLAS-SCALE-67B
- Historical marker: PR-ATLAS-SCALE-63B

Current docs PR:
- PR-ATLAS-DOCS-ROADMAP-02

Next implementation PR:
- PR-ATLAS-SCALE-68: Verification Recommendation UI using Planner Packaging v2

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

Current next PR:
PR-ATLAS-SCALE-68: Verification Recommendation UI using Planner Packaging v2

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
- Next PR: PR-ATLAS-SCALE-68: Verification Recommendation UI using Planner Packaging v2
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

- Next PR: PR-ATLAS-SCALE-68: Verification Recommendation UI using Planner Packaging v2

- Next PR pointer updated to PR-ATLAS-SCALE-69 for verification recommendation handoff metadata.
