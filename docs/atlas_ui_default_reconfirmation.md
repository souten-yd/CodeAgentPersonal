# Atlas UI Default Reconfirmation

Status: POST-SCALE-160-UI-DEFAULT-RECONFIRM completed and re-applied for the buildless Claude chat panel.

## Decision

Revert the default `/` route to the buildless `ui.html` shell that hosts the Claude-Code-style conversational Atlas panel (POST-SCALE-160-CLAUDE-CHAT-PANEL track).

The active default route is `/`, served from `serve_existing_ui_index()` which returns `ui.html`. The guarded Atlas Next preview is still reachable at `/atlas-next/` for users who explicitly opt in by building the dist (`cd web/atlas-next && npm ci && npm run build`); `ATLAS_NEXT_DEFAULT_ENABLED` is now `False`, so even a valid Atlas Next dist no longer takes over `/`. `can_serve_atlas_next_default()`, `validate_atlas_next_dist()`, and the legacy `/ui/` route remain unchanged for code-reachability.

## Preferred Future UI

The active normal Atlas experience is now the buildless ThinUX / FastUI conversational shell described in `docs/atlas_fastui_ux_notes.md` and embodied by `web/js/atlas_claude_panel.js` (DOM `#atlas-claude-col` in `ui.html`). Detailed UX requirements live in `docs/atlas_claude_chat_panel_ux_plan.md`.

## Scope Boundaries

This reconfirmation does not change route behavior, runtime behavior, workflow authority, execution capability, or server startup behavior.

Still forbidden in this checkpoint:

- serving raw Vue source
- bypassing Atlas Next dist validation
- bypassing legacy `/ui/` fallback
- running npm during FastAPI server startup
- making Vue workflow state authoritative
- adding Vue execution controls
- enabling stable runtime mutation
- enabling direct merge, remote push, self-apply, pointer switching, or recovery execution

## Next Track

POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY may proceed only after it proves the stable mutation gate output, verified candidate workspace, stable runtime snapshot, rollback evidence, verification evidence, recovery evidence, strict approval, and exact confirmation text.
