# Atlas UI Default Reconfirmation

Status: POST-SCALE-160-UI-DEFAULT-RECONFIRM completed.

## Decision

Keep the current guarded Atlas Next root default for now.

The active default route remains `/`, backed by the prebuilt Atlas Next dist only when `validate_atlas_next_dist()` passes through `can_serve_atlas_next_default()`. The legacy `/ui/` route remains the fallback, and root falls back to the legacy UI when the Vue dist is missing or invalid.

## Preferred Future UI

The preferred future normal Atlas experience is still the buildless ThinUX / FastUI conversational shell described in `docs/atlas_fastui_ux_notes.md`.

That future default switch requires a separate default-route PR. It must prove the buildless shell route, legacy fallback, route contracts, tests, and rollback behavior before replacing the current guarded Atlas Next default.

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
