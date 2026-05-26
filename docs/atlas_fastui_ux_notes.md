# Atlas FastUI UX Notes

## Goal

Atlas should use a new light conversational interface. The old Atlas screen does not need to be preserved when a new layout is clearer and faster.

## Visual continuity

The new screen should keep the existing KasaneCore theme behavior.

- Reuse current theme settings.
- Reuse accent color settings.
- Support light and dark mode.
- Use existing CSS variables where possible.
- Do not copy another product's colors directly.
- Keep the same theme feeling across Atlas, Lumen, Nexus, and Echo.

## Layout

The main screen should be simple.

Default visible elements:

- conversation area
- goal input
- current status card
- next step card
- small profile badge
- files summary
- check summary
- recovery status
- one main action when needed

Advanced details should be hidden in drawers.

## Settings

Settings should start collapsed.

- Show one compact settings button.
- Expand into a drawer when selected.
- Use a smooth lightweight transition.
- Keep advanced items grouped.
- Keep theme entry points available.

## Lightweight client

The browser should stay light.

- Load summaries first.
- Load details only when selected.
- Use pagination for long lists.
- Use range loading for large text.
- Prefetch the next small range near scroll boundaries.
- Avoid putting full logs or large artifacts into the first page.

## Waiting experience

Long operations should feel clear and pleasant.

Allowed effects:

- gentle active-card motion
- progress rail
- loading skeletons
- small timeline ticks
- subtle completion animation

Effects must respect reduced-motion settings and must not hide errors.

## Implementation phase

Use this direction for the post-Level-4 UX work.

- PR-ATLAS-SCALE-151: FastUI shell contract
- PR-ATLAS-SCALE-152: FastUI shell implementation
