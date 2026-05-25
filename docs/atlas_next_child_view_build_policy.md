# Atlas Next Child View Build Policy

This note fixes the integration boundary for the next Atlas UI implementation PR.

## Intended UI Shape

- The main `/` route continues to serve the existing `ui.html` shell.
- The existing Atlas button opens Atlas mode in the main shell.
- Atlas mode may embed `/atlas-next/` as a child workbench view.
- `/atlas-next/` remains an explicit guarded preview route until a dedicated default promotion PR passes all default gates.

## Build Policy

- Docker image build may run `npm ci && npm run build` under `web/atlas-next` when the Vue package is present.
- Runtime/server startup must not run npm build.
- RunPod startup must use the prebuilt image dist or existing checked-out dist; it must not add a startup npm build fallback.

## Safety Constraints

- Backend workflow state remains authoritative.
- Vue remains non-authoritative.
- `ui.html` remains the default shell until a dedicated default promotion PR.
- No raw Vite source serving.
- No fallback or redirect bypass to Vue.
- No execution capability, autonomous mutation, autonomous execution, or self-modification is enabled by this integration policy.
- Runtime semantics are unchanged by the child-view integration.

## Next Implementation PR

The next implementation PR should apply this policy by:

- keeping `/` on the main shell,
- embedding `/atlas-next/` only under Atlas mode,
- adding Docker build-time Vue dist generation,
- preserving the existing guarded `/atlas-next/` route,
- updating only the directly related contracts and manifest entries.
