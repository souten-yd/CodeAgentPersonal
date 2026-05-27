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
- Include a backend-owned work target mode selector with two choices: software development/repair and platform self-improvement.
- Treat the work target mode selector as workflow intent only; it must not authorize self-improvement, self-apply, execution, direct merge, remote git push, or Vue authority without backend gates.

## Work Target Mode

Later FastUI work should let the user choose whether Atlas is improving the platform itself or developing/repairing ordinary software.

Required behavior:

- Present the choice as a compact button group, segmented control, or equivalent setting.
- Map choices to backend workflow state such as `software_development_or_repair` and `platform_self_improvement`.
- Keep backend workflow state authoritative for eligibility, profile, scope, checkpoint, candidate workspace, verification, and recovery gates.
- Do not let the UI choice bypass strict self-improvement gates or enable stable-runtime mutation.
- Keep this planned for PR-ATLAS-SCALE-151 / PR-ATLAS-SCALE-152 or a directly adjacent UI/UX PR after Level-4 gates.

## UI Default Checkpoint

Before changing the default Atlas route again, the project must explicitly confirm the intended default UI.

Preferred direction:

- Buildless ThinUX / FastUI conversational shell as the normal Atlas experience.
- Existing KasaneCore theme and accent colors remain active.
- Heavy work stays server-side.
- Browser payloads stay small.
- Atlas Next may remain available only when prepared assets are valid and fallback behavior is documented.

This checkpoint should be read before any future UI default route change.

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

Use this direction for the post-Level-4 UX work and later UI default decisions.

- PR-ATLAS-SCALE-151: FastUI shell contract, including backend-owned work target mode contract.
- PR-ATLAS-SCALE-152: FastUI shell implementation, including a compact mode selector for software development/repair versus platform self-improvement.
- POST-SCALE-160-UI-DEFAULT-RECONFIRM: confirm whether the default Atlas route should remain Atlas Next or return to the buildless ThinUX / FastUI shell.
