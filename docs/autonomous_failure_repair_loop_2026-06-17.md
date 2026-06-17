# Autonomous failure-repair loop — repair wired into the G3 cycle, frontier-free

2026-06-17. The repair pieces (cluster by shared cause, templated input fix, assertion-preservation gate)
existed but were only run from throwaway scripts. `failure_repair_loop.py` makes them a first-class
autonomous capability by composing them with the existing `improvement_loop` — so the system self-heals
its test failures with **no frontier model in the loop**.

## Strategy: root-cause-first, peeled iteratively

It is NOT blind "retry until green" iteration. The engine is **root-cause driven**: cluster N failures to
their ONE shared cause and fix the root once (plan_pool drift → 83 failures clear together). It is
**applied iteratively** because real drifts are chained — fixing one root cause makes the deterministic
verify reveal the next (plan_pool KeyError → a missing `threading` import → the verification/run async
drift → safe-apply drift). Each cycle targets one root cause; each pass removes a whole cluster, not a
single symptom. It converges because the failures are heavy-tailed (few root causes cover most) and stalls
VISIBLY (rolled back + flagged) when it meets a cause with no template the weak LLM can't synthesize —
never thrashing.

## The loop (one cycle = one shared-cause cluster)

`run_failure_repair(failures)` builds one `RepairGoal` per batchable cluster and drives the existing
`improvement_loop.run_improvement_backlog`:

1. **execute** (deterministic template, optionally weak-LLM later): apply `repair_sync_contracts` to the
   cluster's test files, each gated by `assertion_preserving_edit` — a rewrite that would touch an
   assertion is refused.
2. **verify** (deterministic, NO model): run the cluster's impacted test ids.
3. **keep / rollback** (Git): a cluster the template does not fix is reverted, never left broken.
4. **safety**: a cluster whose files touch the control surface (`agent/twin_control_plane/…`) is
   `self_protected` → `NEEDS_APPROVAL`, not auto-applied.

All IO (file read/write, pytest, git, the repair transform) is injected, so it is unit-tested with stubs
and wires to real pytest/git in production. The only place a model could ever enter is a future
`synthesize_fn` for a drift whose shape the template does not match — and even then verify/rollback is the
authority.

## Status

`agent/twin_control_plane/failure_repair_loop.py` (+ `tests/test_failure_repair_loop.py`, 6 tests). The
plan_pool cluster has been driven through this exact shape: 28 tests fixed & merged, the rest rolled back
pending further chained-drift templates. No frontier was used.
