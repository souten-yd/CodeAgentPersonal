# Atlas Claude Chat Panel UX Plan

## Purpose

This document defines the buildless Claude-Code-style conversational panel that occupies the Atlas mode pane in `ui.html`. It complements `docs/atlas_conversational_thinui_ux_requirements.md`, `docs/atlas_fastui_ux_notes.md`, and `docs/atlas_full_automation_self_recovery_ux_plan.md`. The canonical roadmap is `docs/atlas_scale_master_roadmap.md`; the canonical phase manifest is `docs/atlas_automation_phase_manifest.json`.

The goal is to refresh the Atlas lower-area UX into a Codex/Claude-Code-like conversation shell while keeping the legacy `#atlas-panel-col` dashboard reachable as a fallback, and to expose a single **Automation Profile** preset selector that unifies the existing safety profile tiers and the new pre-authorised envelope recipes so chat-driven full automation becomes possible without bypassing the backend.

## Relationship to existing roadmap

This work lives in the **POST-SCALE-160** track. It does not advance the canonical SCALE pointer (`completed_automation_pr`, `current_automation_track`). Three planned PRs:

| PR | Outcome |
| --- | --- |
| `POST-SCALE-160-CLAUDE-CHAT-PANEL` | Buildless DOM + CSS + shell selector + read-only safety profile and envelope endpoints. |
| `POST-SCALE-160-CLAUDE-CHAT-PROFILE-CONTROLS` | Automation Profile preset radios, confirmation-text-gated preview/select endpoints. |
| `POST-SCALE-160-CLAUDE-CHAT-COMPLETE-AUTOMATION-PROFILE` | Pre-authorised bounded dev and self-improvement envelopes; chat-driven autonomous loop session preparation. |

## Buildless invariants

Required:

- No npm install, no Vite build, no Vue SFC compilation, no bundler step.
- Shell lives inside `ui.html` and `web/js/atlas_claude_panel.js` (vanilla ES module). CSS is appended to `web/css/app.css`.
- All theme tokens come from existing `:root` variables (`--bg`, `--bg1`, `--bg2`, `--border`, `--text`, `--text2`, `--accent`, `--font-ui`, `--font-mono`). No new palette.
- Marked.js is reused from the existing CDN load (`ui.html` head); no extra dependencies are added.

Forbidden:

- The chat shell becoming authoritative for execution, approval, apply, or self-modification without backend gates (added to `forbidden_mainline_drift_after_scale_113`).
- Hiding the legacy `#atlas-panel-col` irrecoverably.
- New capability tiers in `_PROFILE_CAPABILITIES`.

## Layout

Atlas mode renders one of two panels depending on `localStorage['atlas_shell_preference']`:

- `claude` (default): `#atlas-claude-col`.
- `legacy`: `#atlas-panel-col` (existing dashboard, unchanged).

A small `<select id="atlas-shell-select">` near the Atlas mode button lets the user switch at any time. The selector persists into local storage and is hidden in non-Atlas modes.

## DOM contract

`#atlas-claude-col` contains, in order:

1. `header.atlas-claude-header` — title, subtitle, Recover and Use-legacy-panel buttons.
2. `section.atlas-claude-status-row` — 7 badges: Profile, Target, Phase, Next action, Files, Verify, Recovery.
3. `section#atlas-claude-transcript` — `aria-live="polite"`; user/atlas/system roles; marked.js rendering; 200-message rolling window.
4. `section.atlas-claude-input-wrap` — textarea + Features / Start Atlas / Stop / Send buttons.
5. `details#atlas-claude-features-drawer` — Automation Profile radios, self-improvement override, work target, confirmation input, Preview/Select buttons, profile-result preview.
6. `details.atlas-claude-diagnostics-drawer` — redundant entry into the legacy panel.

The legacy `#atlas-panel-col` is preserved verbatim. Stop and Recover from the new shell synthesise clicks on the legacy `#atlas-workflow-stop-btn` and call `AtlasDashboard.loadRecoveredPlan()` / `refreshStatus()` so the legacy module remains the single source of truth for those behaviours.

## State machine

Browser state is ephemeral:

- `state.transcript` — list of message records, capped at 200.
- `state.presets` / `state.envelopes` — fetched from `/policies` and `/pre-authorized-envelopes`.
- `state.latestSafetyProfile` / `state.latestEnvelope` — populated from `/latest`.
- `state.workflowState` — polled every 8 seconds from `/api/atlas/workflow-state/read-only`.

Persisted (localStorage) keys:

- `atlas_shell_preference` — `"claude"` or `"legacy"`.
- `atlas_claude_last_goal` — the most recent free-text goal.
- `atlas_claude_transcript_window_index` — reserved for future rolling-window features.

## Automation Profile presets

The UI surfaces a single preset list. Internally each preset maps to a `(automation_safety_profile, envelope_id)` tuple.

| # | Preset id | Safety profile | Envelope | Enables full automation |
| --- | --- | --- | --- | --- |
| 0 | `review_only` | `review_only` | `none` | no |
| 1 | `single_action` | `guarded_single_action` | `none` | no |
| 2 | `supervised_auto` | `supervised_bounded_auto` | `none` | no |
| 3 | `autonomous_custom` | `autonomous_dev_agent` | `none` | no (bounds per request) |
| 4 | `autonomous_bounded_dev` | `autonomous_dev_agent` | `pre_authorized_bounded_dev_envelope` | **yes** |
| 5 | `autonomous_self_improvement` | `autonomous_dev_agent` | `pre_authorized_self_improvement_envelope` | **yes** |

Preset 5 requires `strict_gate_approved` and a Level-4 self-improvement checkpoint at the backend. Preset 4 enables full automatic code generation for ordinary development work without enabling self-improvement.

The labels "safety profile" and "tolerance/permission profile" are merged into the single **Automation Profile** label. The two internal axes remain for backend invariants but are not surfaced as separate selectors.

## Pre-authorized bounded dev envelope

Envelopes are bound recipes paired with a capability tier. They do not introduce new capability tiers; they record the user's explicit pre-authorization to activate the derived runtime flags (`autonomous_execution_enabled`, `autonomous_loop_execution_enabled`, `automatic_patch_apply_enabled`, `automatic_self_improvement_enabled`) inside a bounded scope. The `_PROFILE_CAPABILITIES` matrix and the safety profile manifest invariants (which keep `direct_merge_enabled`, `self_apply_enabled`, `self_modification_enabled`, etc. permanently `false`) are unchanged. Activation flags live exclusively on the envelope manifest under `<data_root>/atlas/pre_authorized_envelopes/`.

Two envelopes ship with the panel:

- `pre_authorized_bounded_dev_envelope` — `autonomous_dev_agent` capability, no self-improvement, bound `max_actions_per_loop=12`, `max_files_changed=25`, `max_runtime_seconds=1800`, `allowed_paths=[app/, web/, tests/, docs/]`, `blocked_paths=[.git/, .github/workflows/, scripts/release/, secrets/, infra/]`.
- `pre_authorized_self_improvement_envelope` — `autonomous_dev_agent` capability + self-improvement scope `atlas_runtime_strict`, strict gate and Level-4 checkpoint required, bound `max_actions_per_loop=6`, `max_files_changed=12`, `blocked_paths` extended with `app/server.py` and `main.py`.

`autonomous_loop_envelope_runner.prepare_autonomous_loop_session` validates a chat-driven request against the latest envelope and emits a session record. Bound violations (path, command, action count, runtime, risk level) are rejected with explicit blocking reasons; the runner does not execute commands itself.

## Backend endpoints used

New, read-only with respect to executable runtime state:

- `GET  /api/atlas/automation-safety-profile/policies`
- `GET  /api/atlas/automation-safety-profile/pre-authorized-envelopes`
- `GET  /api/atlas/automation-safety-profile/latest`
- `POST /api/atlas/automation-safety-profile/preview`
- `POST /api/atlas/automation-safety-profile/select` (writes a manifest; never executes)
- `POST /api/atlas/automation-safety-profile/start-autonomous-loop` (prepares a session record; never executes)

Reused (unchanged): `POST /api/atlas/plan-pools`, `POST /api/atlas/pipeline/dry-run`, `GET /api/atlas/workflow-state/read-only`, `GET /api/atlas/recovery/latest`, `GET /api/atlas/continuation/latest`, `POST /api/atlas/automation/decide`, `POST /api/atlas/automation/safe-apply-one`, `POST /api/atlas/automation/verify-one`, `POST /api/atlas/multi-item-autopilot/run`.

## Fallback policy

Five layers of fallback to the legacy panel:

1. Per-user preference (`atlas_shell_preference = legacy`).
2. CSS attribute `data-atlas-shell="legacy"` (visual switch only).
3. Always-visible `Use legacy panel` button in the header.
4. Diagnostics drawer `Open legacy Atlas panel` redundant entry.
5. If `atlas_claude_panel.js` fails to load, the inline `setMode` script falls back to showing `#atlas-panel-col` directly.

Recovery, stop, and approval semantics continue to be owned by the legacy module; the new shell synthesises clicks on the legacy buttons.

## Known Current Code Facts

- The buildless shell lives at `web/js/atlas_claude_panel.js`; DOM at `ui.html` `#atlas-claude-col` (immediately above `#atlas-panel-col`).
- Backend endpoints live in `app/api/atlas_automation_safety_profile.py`; registered in `app/server.py` `include_routers`.
- Envelope recipes live in `app/atlas/pre_authorized_bounded_dev_envelope.py`.
- Autonomous loop session preparation lives in `app/atlas/autonomous_loop_envelope_runner.py`.
- The legacy panel `#atlas-panel-col` and its inline JS remain unchanged; `setMode('atlas')` branches on `localStorage['atlas_shell_preference']`.
- The `automation_safety_profile.py` `_PROFILE_CAPABILITIES` matrix, `validate_automation_safety_profile` invariants, and `write_automation_safety_profile` schema are unchanged.

## Acceptance criteria

1. Atlas mode displays the new shell by default; switching the selector to `legacy` displays the legacy panel verbatim.
2. The Features drawer hosts a single `Automation Profile` preset list with six radios; capability and bound details render inline.
3. Selecting an `Autonomous Bounded Dev` or `Autonomous Self-Improvement` preset writes both the safety profile manifest and the envelope manifest; the safety profile manifest still holds every locked-down flag at `false`; the envelope manifest carries the derived `autonomous_loop_execution_enabled`, `automatic_patch_apply_enabled`, etc.
4. The `start-autonomous-loop` endpoint refuses any request that exceeds the envelope bounds (paths, commands, actions, runtime, files, risk).
5. The legacy fallback is always reachable in one click.

## Drift checks

- `_PROFILE_CAPABILITIES` unchanged.
- Existing `automation_safety_profile.py` invariants unchanged.
- Global manifest `autonomous_execution_enabled`, `direct_merge_enabled`, `remote_git_push_enabled`, `self_apply_enabled` remain `false` by default.
- The two new entries in `forbidden_mainline_drift_after_scale_113` are honoured: shell never becomes authoritative; legacy fallback never disappears.
