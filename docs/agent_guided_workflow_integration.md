# Agent Guided Workflow Integration (Phase 12.8)

## Roles
- Chat: lightweight conversation, consultation, and search-assisted QA.
- Agent: top-level workbench for implementation-oriented work.
- Task: guided workflow layer inside Agent (kept for compatibility during transition).

## Agreed policy
- Keep Chat as conversation-first.
- Make Agent the primary workspace.
- Integrate existing Task/Plan workflow into Agent as Guided Workflow over time.
- Do not remove Task abruptly.
- Preserve existing Task compatibility while enabling the same workflow from Agent.

## Short-term (Phase 12.8)
- Keep existing Task mode and jobs flow.
- Add Guided Workflow entry in Agent mode.
- Reuse the existing shared Plan Workflow entry (`startPlanWorkflow`) from Chat/Task and Agent.

## Mid-term
- Absorb Task tab responsibilities into Agent Tasks/Runs surfaces.
- Keep backward-compatible endpoints and UI behavior during migration.

## Long-term
- Clarify workspace boundaries among Chat / Agent / Nexus / Echo.
- Maintain safety gates and human-in-the-loop review points.

## Explicit non-goals
- No automatic apply.
- No bulk apply/approve.
- No Plan/Patch approval bypass.

## Current workflow entry points
- Chat/Task Plan button (`startPlanWorkflow()`).
- Agent Guided Workflow button (`startAgentGuidedWorkflow()`).
