# Atlas UI Default Reconfirmation

Status: POST-SCALE-160-UI-DEFAULT-RECONFIRM completed and re-applied for the buildless Claude chat panel.

## Decision

Revert the default `/` route to the buildless `ui.html` shell that hosts the Claude-Code-style conversational Atlas panel (POST-SCALE-160-CLAUDE-CHAT-PANEL track).

The active default route is `/`, served from `serve_existing_ui_index()` which returns `ui.html`. Atlas Next Vue3 is no longer a runnable/default UI in this tree: `web/atlas-next` is absent, there is no `/atlas-next` server route or static mount, FastAPI startup does not run npm/Vite builds, and the manifest keeps any Vue default-route facts only as explicitly deprecated, non-active historical metadata. The legacy `/ui/` route remains available for the same buildless shell.

## Preferred Future UI

The active normal Atlas experience is now the buildless ThinUX / FastUI conversational shell described in `docs/atlas_fastui_ux_notes.md` and embodied by `web/js/atlas_claude_panel.js` (DOM `#atlas-claude-col` in `ui.html`). Detailed UX requirements live in `docs/atlas_claude_chat_panel_ux_plan.md`.

## Scope Boundaries

This reconfirmation does not change route behavior, runtime behavior, workflow authority, execution capability, or server startup behavior.

Still forbidden in this checkpoint:

- serving raw Vue source
- re-adding `/atlas-next` runtime serving or raw dist fallback
- requiring Atlas Next dist validation for the active default shell
- bypassing legacy `/ui/` fallback
- running npm or Vite during FastAPI server startup
- making Vue workflow state authoritative
- adding Vue execution controls
- enabling stable runtime mutation
- enabling direct merge, remote push, self-apply, pointer switching, or recovery execution

## Next Track

POST-SCALE-160-STABLE-RUNTIME-MUTATION-APPLY may proceed only after it proves the stable mutation gate output, verified candidate workspace, stable runtime snapshot, rollback evidence, verification evidence, recovery evidence, strict approval, and exact confirmation text.
