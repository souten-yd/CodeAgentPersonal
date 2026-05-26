# Atlas Full Automation, Self-Recovery, and Conversational UX Plan

## Purpose

This document extends the canonical Atlas automation roadmap after PR-ATLAS-SCALE-146. It defines the post-Level-4 plan for safe full automation, self-improvement hardening, non-LLM recovery, and a Codex-like conversational Atlas UX.

The canonical roadmap remains `docs/atlas_scale_master_roadmap.md`.
The canonical safety policy remains `docs/atlas_autonomous_execution_readiness_policy.md`.
The machine-readable phase contract remains `docs/atlas_automation_phase_manifest.json`.

## Current relationship to the existing roadmap

The existing PR-144 through PR-146 plan must remain intact:

- PR-ATLAS-SCALE-144: Self-improvement approved patch apply.
- PR-ATLAS-SCALE-145: Self-improvement draft PR creation.
- PR-ATLAS-SCALE-146: Level-4 self-improvement checkpoint.

This document must not be used to bypass PR-144 through PR-146 gates. Full automation begins only after the Level-4 checkpoint or after an explicit roadmap update that says otherwise.

## Design goals

1. Provide a four-level user-selectable automation safety profile.
2. Allow progression from review-only safety to Codex/Claude-like autonomous coding capability.
3. Keep direct merge forbidden by default.
4. Keep Vue and Atlas Next non-authoritative; backend workflow state remains the source of truth.
5. Make self-improvement safer than ordinary repository work.
6. Never mutate the stable runtime directly during self-improvement.
7. Add a recovery path that does not depend on the LLM, the modified application code, FastAPI, or the target code being healthy.
8. Move the Atlas UI toward a simple conversational UX while preserving advanced diagnostics behind an explicit drawer or mode.

## Automation safety profiles

Atlas should expose a single backend-owned automation safety profile. UI, CLI, and any future API clients must read the same backend profile.

### Profile 0: Review Only

Purpose: safest possible mode.

Allowed:

- Read-only repository inspection.
- Planning.
- Patch preview.
- Risk classification.
- Verification recommendation.
- Artifact review.
- Conversational explanation.

Forbidden:

- File mutation.
- Command execution.
- Patch apply.
- Git mutation.
- Branch creation.
- PR creation or update.
- Auto-continue.
- Self-modification.

### Profile 1: Guarded Single Action

Purpose: current Level-1 style operation.

Allowed:

- One low-risk allowlisted action at a time.
- Dry-run-first flow.
- Explicit approval token or confirmation text.
- Snapshot and rollback readiness before mutation.

Forbidden:

- Auto-continue.
- Execute-all.
- Autonomous loop execution.
- Remote git push.
- Direct merge.
- Self-apply.

### Profile 2: Supervised Bounded Auto

Purpose: human-supervised multi-step automation.

Allowed:

- Bounded loop planning.
- Bounded retry proposal.
- Low or medium risk work under configured limits.
- Allowlisted verification execution when explicitly enabled.
- Draft PR preparation under human gates.

Requires explicit approval for:

- Patch apply.
- Retry apply.
- Branch creation.
- Draft PR creation.
- Medium, high, strict, or self-improvement changes.

Forbidden:

- Direct merge.
- Remote push without a dedicated gate.
- Strict-gate automatic mutation.
- Self-apply.
- Automatic rollback unless separately enabled by a future explicit PR.

### Profile 3: Autonomous Dev Agent

Purpose: Codex/Claude-like autonomous coding capability with Atlas safety controls.

Allowed when all gates pass:

- Goal to plan to patch to candidate apply to verify to fix loop.
- Project-scoped file editing.
- Allowlisted command execution.
- Automatic patch regeneration.
- Automatic verification.
- Bounded retry.
- Draft PR creation and update.

Still forbidden by default:

- Direct merge.
- Production data mutation.
- Secret mutation.
- Unbounded loops.
- Remote push without a dedicated explicit gate.
- Self-modification without self-improvement gates.

## Self-improvement mode is a separate axis

Self-improvement must not simply be Safety Profile 3. It is a separate capability because changing KasaneCore itself is higher risk than changing an ordinary project.

Recommended settings:

```json
{
  "automation_safety_profile": "review_only | guarded_single_action | supervised_bounded_auto | autonomous_dev_agent",
  "self_improvement_enabled": false,
  "self_improvement_scope": "none | docs_tests_only | atlas_non_runtime | atlas_runtime_strict | full_platform_strict"
}
```

Self-improvement must remain disabled unless the profile, scope contract, checkpoint, candidate workspace, verification, and recovery gates all pass.

## Self-improvement isolation model

Self-improvement must never patch the stable runtime directly.

Required architecture:

```text
stable runtime
  current working application used by the user

candidate workspace
  isolated self-improvement copy or git worktree

recovery supervisor
  minimal tool that does not import app/, main.py, FastAPI, or LLM code

checkpoint store
  manifests, hashes, release pointers, boot diagnostics, and recovery scripts
```

### Candidate workspace requirements

A self-improvement run must:

1. Declare target repo, target area, allowed paths, blocked paths, max files, and risk level.
2. Create a stable checkpoint before mutation.
3. Create a candidate workspace using git worktree when possible, with copy fallback when worktree is unavailable.
4. Apply patches only inside the candidate workspace.
5. Run candidate verification in the candidate workspace.
6. Promote only if all required checks pass.
7. Keep failed candidates quarantined for inspection.

### Promotion model

Prefer release-pointer promotion over in-place overwrite.

Example:

```text
releases/
  stable_20260526_001/
  candidate_20260526_002/
current_release.json
```

Promotion changes the active pointer only after verification passes. Windows support must avoid relying exclusively on symlinks; a JSON pointer is the safer default.

## Non-LLM recovery model

Recovery must work even when:

- The LLM is unavailable.
- The modified application fails to import.
- FastAPI cannot start.
- `main.py` is broken.
- The target code being repaired is broken.

### Recovery Supervisor requirements

Add an external recovery supervisor under `recovery/`.

Recommended files:

```text
recovery/recover.py
recovery/recover.bat
recovery/recover.ps1
recovery/recovery_manifest_schema.json
```

The recovery supervisor must not import:

- `main.py`
- `app/`
- Atlas runtime modules
- LLM providers
- FastAPI application code

The recovery supervisor may read JSON manifests, validate hashes, switch release pointers, restore file copies, and record recovery reports.

## Checkpoint model

### Release checkpoint

Records code, launcher, UI, scripts, config templates, hashes, current commit, and rollback script references.

### Data checkpoint

Records settings, Atlas artifacts, SQLite/DB backup metadata, model DB metadata, and migration status. Database restore must be explicit and must avoid unsafe live copies.

### Boot health checkpoint

After git update, release promotion, or first launch after update, Atlas should run a boot self-diagnosis and write a checkpoint record.

Required checks:

- Python import smoke.
- FastAPI router include smoke.
- `/health` or equivalent health probe.
- Atlas contract smoke.
- UI asset existence.
- Atlas Next mount/display-only status.
- Recovery supervisor availability.
- Optional degraded checks for LLM, TTS, ASR, Nexus, and external services.

## Recovery button UX

A recovery button must not depend on the broken application runtime.

Recommended behavior:

1. Display the latest stable checkpoints when available.
2. Invoke the recovery supervisor or show an OS-specific command.
3. Switch release pointer or restore files using the recovery supervisor.
4. Record a recovery report.
5. Restart or instruct the launcher to restart.

If the web UI is unavailable, the same recovery path must work from command line.

## Conversational Atlas UX direction

Atlas should move toward a Codex-like conversational shell while keeping backend state authoritative.

### UX principles

1. One primary conversation input.
2. One visible primary action at a time.
3. State is shown as simple cards, not many subsystem panels.
4. Advanced diagnostics remain available but hidden by default.
5. The user can ask what Atlas is doing, why it is blocked, what will change, and how to recover.
6. Every action must map to a backend workflow state and artifact chain.
7. Vue or Atlas Next may render the shell, but must not become the source of truth.

### Primary conversational states

- `idle`
- `understanding_goal`
- `planning`
- `needs_scope_confirmation`
- `previewing_changes`
- `awaiting_approval`
- `running_dry_run`
- `applying_candidate`
- `verifying_candidate`
- `promoting_candidate`
- `draft_pr_ready`
- `blocked`
- `recoverable_failure`
- `recovered`

### Minimal visible UI

Default Atlas screen should show:

- Conversation transcript.
- Goal input.
- Current phase card.
- Next action card.
- Risk / safety profile badge.
- Changed files summary.
- Verification summary.
- Recovery status.
- One primary CTA.

Hidden by default:

- Raw JSON.
- Low-level IDs.
- Direct subsystem controls.
- Internal gate manifests.
- Multi-panel diagnostics.

### Suggested user-facing commands

The conversational shell should support natural language equivalents of:

- “Plan this.”
- “Show changed files.”
- “Explain the risk.”
- “Run dry-run.”
- “Approve this one action.”
- “Create draft PR.”
- “Stop.”
- “Recover previous stable checkpoint.”
- “Switch safety profile.”

## Post-Level-4 implementation plan

The following PRs extend the roadmap after PR-ATLAS-SCALE-146.

| PR | Required outcome | Runtime impact | Drift check |
| --- | --- | --- | --- |
| PR-ATLAS-SCALE-147 | Automation safety profile framework | no new execution | profile selection only |
| PR-ATLAS-SCALE-148 | External recovery supervisor foundation | no app dependency | recovery must not import app/ |
| PR-ATLAS-SCALE-149 | Candidate workspace manager | no stable mutation | self-improvement uses candidate only |
| PR-ATLAS-SCALE-150 | Boot self-diagnosis and stable checkpoint | no autonomous loop | startup health artifact only |
| PR-ATLAS-SCALE-151 | Conversational Atlas shell contract | UI/UX only | backend workflow state remains authoritative |
| PR-ATLAS-SCALE-152 | Conversational shell implementation | display/supervision only | one primary CTA, no authority shift |
| PR-ATLAS-SCALE-153 | Self-improvement candidate apply | candidate mutation only | stable runtime untouched |
| PR-ATLAS-SCALE-154 | Candidate verification gate | allowlisted verification only | no promote without evidence |
| PR-ATLAS-SCALE-155 | Promotion gate and release pointer switch | controlled promotion | rollback-ready pointer required |
| PR-ATLAS-SCALE-156 | Automatic failure recovery v1 | recovery automation | no LLM or app import required |
| PR-ATLAS-SCALE-157 | Autonomous loop execution v1 | bounded execution | draft PR only, no direct merge |
| PR-ATLAS-SCALE-158 | Full automation mode checkpoint | explicit transition | Safety Profile 3 gates required |
| PR-ATLAS-SCALE-159 | Self-improvement autonomous candidate loop | candidate-only self automation | no direct stable mutation |
| PR-ATLAS-SCALE-160 | Fully autonomous code agent milestone | final checkpoint | goal to draft PR E2E, no direct merge |

## Full automation completion criteria

Atlas can be considered a fully autonomous code agent only when all of the following are true under an explicit safety profile:

- `autonomous_execution_enabled` is true.
- `autonomous_loop_execution_enabled` is true.
- Automation safety profile is explicit and audited.
- Candidate workspace is used for self-improvement.
- Recovery supervisor is available without LLM or app imports.
- Stable checkpoint exists before mutation.
- Boot health checkpoint exists after promotion.
- Automatic patch generation, apply, verification, and bounded retry are available within configured limits.
- Draft PR creation and update are available within configured limits.
- Direct merge remains forbidden unless a future explicit policy changes it.
- Stop, rollback, and recovery paths are tested.
- Conversational UX can explain state, risk, next action, and recovery.
