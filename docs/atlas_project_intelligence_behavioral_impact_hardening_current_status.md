# Atlas Project Intelligence Behavioral Impact Hardening Current Status

## Track

PIBIH: Project Intelligence Behavioral Impact Hardening

## Overall Status

```text
status: ready_to_start
current_package: PIBIH-1
next_action: implement LLM Planning Timeout and Streaming Progress Hardening
```

## Completed Foundations

The following tracks are treated as completed foundations and must not be restarted from scratch:

- Project Intelligence Recovery foundation.
- Portal / Play / Capsule foundation.
- Portal + Model Forge foundation.
- Portal + Model Forge Hardening foundation if already merged in the current branch.
- Existing Project Twin durable store, static graph, behavioral graph, rollout, and coordinator modules.

## Current Known Gaps

1. Slow local models can time out during Plan/DeepPlanner structured-output calls before first token or after token generation starts if progress does not reset the stall timer.
2. Impact Analysis contracts exist, but practical traversal and Plan/UI exposure need hardening.
3. Behavioral graph exists but needs deeper function, variable, state, resource, and UI/API relation inference.
4. Project Intelligence active planning can use Twin context, but generation still needs richer context injection.
5. Plan-time Nexus Web Research exists behind a flag but needs a planning decision point and PlanPool/PlanItem integration.
6. Runtime/verification evidence should feed future impact risk without falsely verifying inferred facts.

## Active Package

### PIBIH-1: LLM Planning Timeout and Streaming Progress Hardening

Priority: highest.

### Required Investigation

- Locate every Atlas planning path that calls `generate_structured`, `call_llm_json`, or `AtlasLLMJsonAdapter`.
- Verify whether Plan/DeepPlanner/PlanPool builders pass `stream=True` or `on_progress`.
- Inspect `_post_chat_stream` behavior and confirm whether last-progress is updated for:
  - first token,
  - content deltas,
  - non-content heartbeat chunks,
  - final completion,
  - errors.
- Confirm current timeout source:
  - request timeout,
  - socket timeout,
  - stalled generation watchdog,
  - frontend/workbench timeout,
  - structured-output retry timeout.

### Acceptance Checklist

- [ ] Fake backend with long prefill and valid eventual first token succeeds within first-token timeout.
- [ ] Fake backend with continuous slow token deltas succeeds.
- [ ] Fake backend with no first token fails as `llm_stalled_before_first_token`.
- [ ] Fake backend with one token then no progress fails as `llm_stalled_after_progress`.
- [ ] Total timeout is distinct from first-token and idle-token timeout.
- [ ] Structured-output retry still works.
- [ ] Existing non-streaming tests still pass.
- [ ] Plan status/journal metadata records timeout phase truthfully.

## Evidence Log Template

Append one block per package completion:

```text
Completed package:
Status:
Changed modules/files:
Behavior implemented:
Focused tests:
Syntax checks:
Affected tests:
Real model evidence:
Project Intelligence evidence:
Impact analysis evidence:
Web research evidence:
Runtime/Portal evidence:
Unavailable checks:
Safety invariants:
Remaining gaps:
Next package:
Blocker:
```

## Next Package Queue

```text
PIBIH-1: LLM Planning Timeout and Streaming Progress Hardening
PIBIH-2: Impact Analysis Core
PIBIH-3: Deep Behavioral Graph V3
PIBIH-4: Project Intelligence Planning and Generation Injection
PIBIH-5: Plan-Time Nexus Web Research
PIBIH-6: Impact UI / Planner Exposure
PIBIH-7: Runtime Evidence Promotion and Historical Risk Memory
```
