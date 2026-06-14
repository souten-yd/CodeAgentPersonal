# Atlas Runtime Progress and Resume/Rehydrate Hardening Test Plan

## AUIR-1: LLM Props Initialization

### Tests

Create a test or browser smoke that loads the UI and triggers the same startup path as real usage.

Assertions:

- No `ReferenceError` or TDZ error for `_current_n_ctx_ui`.
- LLM props fetch failure is logged as warning but Atlas shell still initializes.
- Token indicator DOM remains available.
- Atlas tab can be selected after props failure.

Suggested test names:

```text
tests/test_atlas_ui_llm_props_init.py
tests/test_atlas_ui_startup_smoke.py
```

If there is Playwright infrastructure:

```text
tests/playwright/test_atlas_llm_props_init.spec.ts
```

## AUIR-2: Progress Event Model

### Backend Tests

Use a fake LLM/progress source.

Assertions:

- `llm_started` is persisted.
- `llm_first_token` is persisted.
- `llm_token_delta` updates latest snapshot.
- terminal event updates latest snapshot.
- events include workspace_id, pool_id, run_id, item_id, phase, model, tokens, tps, and last_progress_at.

Suggested tests:

```text
tests/test_atlas_runtime_progress_events.py
```

## AUIR-3: Reload/Resume Rehydration

### Backend Tests

- Create a fake active run.
- Persist progress events.
- Call runtime snapshot endpoint.
- Assert active status and latest LLM progress are returned.

### Frontend/Playwright Tests

Flow:

1. Start or mock active Atlas run.
2. Open Atlas.
3. Observe active status and indicator.
4. Reload page.
5. Return to Atlas.
6. Assert status and indicator are restored.

Old behavior should fail by showing only an empty green frame.

Suggested tests:

```text
tests/test_atlas_runtime_snapshot.py
tests/playwright/test_atlas_reload_resume.spec.ts
```

## AUIR-4: Reconnection UX

Tests:

- Simulate missed events and reconnect with `after_sequence`.
- Assert no duplicate events.
- Assert stale/reconnecting status appears if live connection is gone.
- Assert backend stalled state is visually distinct from disconnected state.

## AUIR-5: Mobile/Tab Switch Smoke

Tests:

- Mobile viewport.
- Switch from Atlas to another mode and back.
- Background/foreground simulation if supported.
- Reload during active run.
- Verify active status and indicator.

## Required Manual Evidence

If automated browser tests cannot run, record a manual smoke:

```text
1. Start Atlas plan.
2. Approve execution.
3. Confirm token indicator updates during LLM generation.
4. Switch to Lumen/Nexus/Forge and return to Atlas.
5. Confirm active development status remains visible.
6. Reload browser.
7. Confirm status and last progress are restored.
8. Confirm no `_current_n_ctx_ui` warning appears.
```

Manual evidence is not a substitute for automated regression tests, but it is useful runtime evidence.
