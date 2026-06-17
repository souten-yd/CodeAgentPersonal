# plan_pool cluster — templated batch repair, deterministically verified — 2026-06-17

Acting on the shared-cause plan: actually fix the largest failure cluster (`KeyError: 'plan_pool'`, 77
failures, the async-contract drift) with **Twin + a templated source transform**, where the authoritative
verification is **deterministic** (run the affected tests, Git-rollback on failure) — no frontier in the
loop.

## The loop, run for real

For each of the 18 plan_pool-failing test files:
1. `plan_pool_contract_repair.repair_plan_pool_source` rewrites the test INPUT — adds `?sync=1` and a
   `plan_payload` to the `/api/atlas/plan-pools` POST (template fix for the drift).
2. `assertion_preserving_edit` gate: confirm no assertion was changed (only input changed).
3. **deterministic verify**: run that file's plan_pool test ids; KEEP on pass, `git checkout` (rollback)
   on fail.

## Result

| outcome | files | meaning |
|---|---:|---|
| **KEPT (verified)** | **5 (13 tests)** | template fixed them, tests pass |
| ROLLED BACK | 10 | template alone insufficient — reverted, nothing left broken |
| skipped (no match) | 3 | a different helper shape |

13 plan_pool failures are now green: `test_atlas_approval_api`, `test_atlas_auto_safe_apply_api`,
`test_atlas_auto_safe_apply_service`, `test_atlas_automation_policy_api`, `test_atlas_change_snapshot_service`.

## The verify loop surfaced a real product bug

After the template cleared the `KeyError`, the verification-flow tests hit
`NameError: name 'threading' is not defined` at `app/api/atlas_pipeline.py:2629` — `threading.Thread(...)`
in the verification-run endpoint, while `import threading` existed only inside two *other* functions
(lines 1001, 3498). A genuine missing module-level import the test-debt KeyError had been masking. Fixed
by adding `import threading` at module scope (broad `test_atlas_api_pipeline` + the 5 kept files: 49
passed).

## Why the 10 were correctly rolled back

They depend on a **chained, multi-endpoint** async drift: after plan-pools, the verification-run endpoint
also went async (`status: 'running'` where the test expects the synchronous `'blocked'`). The
plan-pools-only template cannot fix those; the deterministic gate refused them rather than leave a wrong
"fix". They need the sync template extended to `verification/run` (and `safe-apply`) — a known,
characterised follow-up, still frontier-free.

## Takeaway

The shared-cause loop works end-to-end and is honest: it fixed the 13 it could verify, found and fixed a
real latent product bug, and refused the 10 it could not — all deterministically, no frontier. Files:
`agent/twin_control_plane/plan_pool_contract_repair.py` (+ tests).

## Generalized: the template was one-off; the PATTERN is not (2026-06-17, follow-up)

The plan-pools template was hardcoded (one-off). But the drift KIND is generic: an endpoint that went
async is fixed by adding `?sync=1` to the `.post` call — and `/verification/run`, `/debug-review/run`,
`/safe-apply/execute` all expose the same `sync: int = Query(0)`. So the transform was generalized into
`sync_contract_repair.repair_sync_contracts(src, endpoints)` — parameterized over an endpoint map, scoped
to `.post()` calls only (never a URL inside an assertion / route-set literal). `plan_pool_contract_repair`
is now a thin specialisation of it.

Re-running the batch with the multi-endpoint transform fixed **3 more files / 15 tests**
(`verification_gate_api` ×7, `patch_proposal_planitem_debug_review_flow` ×6, `…verification_flow` ×2)
deterministically — no weak LLM needed, because the drift was the SAME shape. `debug_review_api` was
correctly **assertion-gate-blocked** (the transform would have touched a route-existence assertion). The
remaining safe-apply-flow files have further chained drift and stay rolled back.

**Answer to "is the template generic?":** the specific template is one-off, but the pattern generalizes
deterministically by parameterization. The weak LLM is only needed when a cluster's drift is NOT this
shape (the transform changes nothing, or its change fails verification) — that is the signal to synthesize
a new template; here it was not needed.
