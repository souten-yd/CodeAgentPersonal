# plan_pool failure cluster — investigation + rollback demo — 2026-06-17

The failure classifier put `KeyError: 'plan_pool'` (~82 failures, the largest cluster) in
GENUINELY_BROKEN. Investigating it (the detect → investigate → fix → verify → rollback loop, no
frontier needed for the deterministic parts) showed it is **test debt, not a code regression**.

## Findings

- `POST /api/atlas/plan-pools` intentionally went **async** (returns `{"pool_id","status":"queued"}`)
  to avoid the proxy 524 timeout on slow LLM planning; `?sync=1` keeps the synchronous response.
- `?sync=1` alone runs the real planner → hangs without a fast LLM. `?sync=1` +
  `planner_mode=fallback_only` returns a `plan_pool` in ~0.1 s, no LLM.
- BUT `build_fallback_pool` creates `items=[]` **by design** (`fallback_plan_items_generated: False`),
  so the next test step `created['items'][0]` raises `IndexError`. The tests assumed the fallback would
  generate items; it never does.

So the ~82 `KeyError: 'plan_pool'` failures are **stale tests** (the API is correct): they rely on a
removed synchronous-with-items contract. A proper fix is per-test — supply a `plan_payload` with the
items each test exercises — which is real test rework, not a one-line change.

## The loop, demonstrated (no frontier dependency)

1. **detect** (deterministic classifier): KeyError:'plan_pool' ×82.
2. **investigate**: probed the live endpoint (200, returns queued) → the API works.
3. **fix attempt** (deterministic, no LLM): add `?sync=1`+`fallback_only` to 9 call sites — cleared
   KeyError, but `IndexError` surfaced (fallback has no items).
4. **verify**: the fix was incomplete (tests still fail).
5. **rollback** (Git): `git checkout -- <files>` reverted the 9-line change cleanly; working tree clean.

## Gap to add to KasaneCore (per the standing policy)

The deterministic classifier (and a context-free weak-LLM judge) cannot tell a `KeyError` /
`AssertionError` that is a **code bug** from one that is **test debt** — that needs CODE CONTEXT (does
the endpoint/function actually work?). The weak-LLM judge should be fed the relevant code / an endpoint
probe so it can make that call locally. This is why the "401 genuinely_broken" is an over-count: like
plan_pool, many are stale tests against intentionally-changed contracts.

## Implication

"Resolve all 559 failures" is mostly **test-debt cleanup against intentionally-changed contracts**, not
fixing product code. The productive version is: re-judge the 401 with the weak LLM + code context to
separate the few real bugs from the test debt, then fix the real bugs and schedule the debt.
