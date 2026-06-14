# Atlas Project Intelligence Behavioral Impact Hardening Agent Entrypoint

## Start Here

Read in this order:

1. `AGENTS.md`
2. `docs/atlas_project_intelligence_behavioral_impact_hardening_current_status.md`
3. `docs/atlas_project_intelligence_behavioral_impact_hardening_plan.md`
4. `docs/atlas_project_intelligence_behavioral_impact_hardening_test_plan.md`
5. Existing PIR/PFG/PFH docs only when touching their areas
6. Target source files and tests

## First Package to Implement

Start with:

```text
PIBIH-1: LLM Planning Timeout and Streaming Progress Hardening
```

Do not start with Behavioral Graph or Impact Analysis until the Plan timeout path is reliable. Slow model planning failure blocks the rest of the track.

## PIBIH-1 Implementation Prompt

Implement Atlas planning LLM timeout hardening.

Current hypothesis:

```text
Atlas Plan/DeepPlanner can fail with slow local models because the current timeout path does not distinguish:
- waiting for first token / prefill;
- idle timeout after generation starts;
- total timeout;
- structured-output retry exhaustion.

If token generation starts, the stall timer must reset on progress. A slow but progressing model must not be treated as stalled.
```

Required work:

1. Inspect the real Plan/DeepPlanner/structured-output LLM call chain.
2. Identify whether `stream=True` or `on_progress` is used.
3. Add or harden timeout fields:
   - `first_token_timeout_seconds`
   - `idle_token_timeout_seconds`
   - `total_timeout_seconds`
4. Preserve backward compatibility with existing `timeout_seconds`.
5. Add progress events:
   - `llm_started`
   - `llm_first_token`
   - `llm_token_delta`
   - `llm_heartbeat`
   - `llm_idle_waiting`
   - `llm_completed`
   - `llm_stalled_before_first_token`
   - `llm_stalled_after_progress`
   - `llm_total_timeout`
6. Add fake streaming tests.
7. Update the current status doc with evidence.

## Suggested Initial Code Search

Search these symbols:

```text
generate_structured
call_llm_json
AtlasLLMJsonAdapter
with_progress
ATLAS_LLM_STREAMING
_post_chat_stream
llm_stalled
timeout_seconds
DeepPlanner
PlanPool
```

## Required Acceptance Before Moving to PIBIH-2

- Fake slow first token succeeds within first-token timeout.
- Fake continuous slow token stream succeeds.
- Fake no-first-token path fails with before-first-token reason.
- Fake after-progress stall fails with after-progress reason.
- Existing structured-output fallback behavior still passes.
- Current status doc is updated with evidence and remaining gaps.

## After PIBIH-1

Proceed in this order:

```text
PIBIH-2: Impact Analysis Core
PIBIH-3: Deep Behavioral Graph V3
PIBIH-4: Project Intelligence Planning and Generation Injection
PIBIH-5: Plan-Time Nexus Web Research
PIBIH-6: Impact UI / Planner Exposure
PIBIH-7: Runtime Evidence Promotion and Historical Risk Memory
```

## Do Not

- Do not mark inferred behavioral facts verified.
- Do not bypass Proposal / Safe Apply / Verification.
- Do not run external web research unless `ATLAS_NEXUS_WEB_RESEARCH=1`.
- Do not call OpenRouter or external providers in Local Only mode.
- Do not store secrets.
- Do not claim unavailable runtime/model/web evidence as passed.
