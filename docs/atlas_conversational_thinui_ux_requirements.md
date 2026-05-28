# Atlas Conversational ThinUI UX Requirements

## Purpose

This document refines the post-Level-4 Atlas UX requirements. It complements `docs/atlas_full_automation_self_recovery_ux_plan.md` and must be read together with the canonical roadmap and safety policy.

The goal is to provide a Codex-like conversational development experience while preserving KasaneCore's existing theme system, keeping the browser lightweight, and keeping backend workflow state authoritative.

## UX goals

Atlas should feel like a simple coding conversation, not a dense control panel.

The user experience should be:

1. The user describes a development goal in conversation.
2. Atlas asks only the requirement questions needed to remove ambiguity.
3. Atlas shows a compact scope, risk, safety profile, changed-files summary, and recovery plan.
4. Atlas proceeds according to the selected safety profile and configured operating envelope.
5. Atlas edits, verifies, fixes, and prepares a draft PR when the selected profile allows it.
6. The user can stop, inspect, or recover at any time.

## Theme continuity

The conversational Atlas shell must preserve existing KasaneCore theme behavior.

Requirements:

- Reuse existing theme settings, including dark/light mode and accent color.
- Do not hardcode a separate Codex-like color palette.
- Treat Codex-like UX as an interaction model, not a forced visual clone.
- Continue to support current theme switching across Atlas, Lumen, Nexus, Echo, and the new conversational shell.
- Safety profile badges, risk labels, phase cards, and action buttons must derive visual style from theme tokens.
- New CSS should use existing CSS custom properties where possible.
- Any new theme tokens must be introduced as compatibility additions rather than replacing the existing theme system.

## Buildless default shell

The default conversational Atlas shell must be buildless.

Requirements:

- No npm install is required for ordinary Atlas UI development.
- No Vite build is required for the default shell.
- No Vue single-file component compilation is required for the default shell.
- Runtime startup must not run npm build.
- RunPod startup must not run npm build.
- Docker may still build optional Atlas Next preview assets, but those assets must not be required for the default conversational shell.
- The default shell should use `ui.html`, static CSS, and vanilla ES modules under `web/js/`.
- Atlas Next / Vue remains optional preview or child view only.

## ThinUI and server-first contract

The conversational Atlas shell must be ThinUI. Heavy work belongs on the server.

Server-side responsibilities:

- repository indexing
- code search
- impact analysis
- diff generation and summarization
- patch transaction building
- risk classification
- verification planning
- verification execution orchestration
- recovery planning
- artifact filtering and summarization
- long-running job state
- cursor pagination and range reads

Browser-side responsibilities:

- render conversation and cards
- send user intent
- display current backend state
- request paginated details
- show one primary action
- keep only ephemeral UI state locally

The browser must not store full repo indexes, full artifact bundles, complete verification logs, full PlanPool payloads, or complete Nexus bundles unless the user explicitly downloads them.

## Lightweight data loading

The UI must avoid loading large data upfront.

Requirements:

- Use summary-first endpoints for conversations, plans, diffs, logs, artifacts, and verification results.
- Use cursor pagination for long lists.
- Use range reads or logical slices for large logs and diffs.
- Use viewport-aware prefetch near scroll boundaries.
- Use virtualization for long message lists, diff views, artifact lists, and logs.
- Keep only visible and recently viewed ranges in browser memory.
- Open large artifacts in a detail drawer or download flow rather than injecting them into the main conversation stream.
- Do not embed full RepoIndex, full PlanPool, full history, or full verification logs in the initial page payload.

## Conversational interaction structure

Default visible elements:

- conversation transcript
- goal input
- current phase card
- next action card
- safety profile badge
- changed files summary
- verification summary
- recovery status
- one primary CTA

Hidden by default behind diagnostics mode:

- raw JSON
- low-level IDs
- direct subsystem controls
- internal gate manifests
- multi-panel diagnostics
- full artifacts and long logs

## Pre-authorized bounded automation

Atlas should support a mode where it can continue development steps without asking for every safe internal step, but only after the user explicitly configures the operating envelope.

The operating envelope must include:

- repository or workspace scope
- allowed path scope
- blocked path scope
- maximum risk level
- command allowlist
- maximum loop count
- maximum retries
- maximum changed files
- maximum runtime
- checkpoint policy
- recovery policy
- draft-PR-only or merge policy

This is not unrestricted execution. It is bounded automation inside a pre-authorized and audited envelope.

Strict-gate actions, self-improvement, direct merge, remote push, secret changes, production data mutation, and platform-critical runtime changes require their own explicit gates.

## Implementation placement

This UX work belongs after the current PR-144 through PR-146 self-improvement checkpoint plan.

Planned PRs:

| PR | Purpose |
| --- | --- |
| PR-ATLAS-SCALE-151 | Buildless themed ThinUI conversational shell contract |
| PR-ATLAS-SCALE-152 | Buildless themed ThinUI conversational shell implementation |

PR-151 must define the backend state contract and UI data-loading contract before UI implementation. PR-152 must implement the shell without making the UI authoritative and without adding a required build step.

## Implementation placement (POST-SCALE-160 buildless chat panel track)

| PR | Surface | Files |
| --- | --- | --- |
| POST-SCALE-160-CLAUDE-CHAT-PANEL | `#atlas-claude-col` shell + chat transcript + input + shell selector | `ui.html`, `web/js/atlas_claude_panel.js`, `web/css/app.css`, `app/api/atlas_automation_safety_profile.py` |
| POST-SCALE-160-CLAUDE-CHAT-PROFILE-CONTROLS | Features drawer, Automation Profile preset radios, confirmation-text-gated preview/select | `ui.html`, `web/js/atlas_claude_panel.js`, `app/api/atlas_automation_safety_profile.py` |
| POST-SCALE-160-CLAUDE-CHAT-COMPLETE-AUTOMATION-PROFILE | Pre-authorised envelopes and chat-driven autonomous loop session preparation | `app/atlas/pre_authorized_bounded_dev_envelope.py`, `app/atlas/autonomous_loop_envelope_runner.py`, `app/api/atlas_automation_safety_profile.py` |
