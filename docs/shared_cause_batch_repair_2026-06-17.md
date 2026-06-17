# Shared-cause batch repair — can Twin + weak LLM fix the failures generically?

2026-06-17. Question asked: can the failing tests be fixed *generically* by Twin + the weak LLM, or is
it a Twin capability gap? Judgment, and the first deterministic, frontier-free building block.

## Judgment

**Not yet generically — it is a capability gap, but the failure distribution makes it worth closing.**
75% of the actionable failures cluster by signature, but signature clustering over-merges (it collapses
37 *different* `assert X == Y` mismatches to one shape). What is actually needed:

1. a **single-source guard** that confirms a cluster has ONE concrete cause before any batch fix;
2. an **assertion-preservation gate** so a test-debt fix can change input/fixtures but never delete or
   weaken an assertion;
3. (next) a test-input/fixture repair generator + a context-fed judge.

`shared_cause_repair.py` delivers (1) and (2) — the two deterministic guards that make a safe batch
repair possible at all.

## What it does

- `extract_cause(reason)` recovers the concrete `(kind, key)` a failure is about: the missing dict key,
  the renamed enum pair, the missing field list, the policy flag. Anchored at the reason start so a
  rendered body cannot hijack the key.
- `cluster_shared_causes(failures)` groups by root-cause signature, then marks a cluster `single_source`
  only when its members AGREE on that concrete key (the over-merge guard), and `batchable` only when it
  is single-source, recognised, and large enough.
- `assertion_preserving_edit(old, new)` compares the assertions (AST) of two versions of a test and
  rejects any edit that drops or alters one — the safety gate that lets a loop touch tests.
- `build_batch_repair_plan(failures)` splits the set into batchable clusters and the residual that needs
  individual handling. It does NOT edit anything; the edit synthesis + execution stay behind these
  guards and an approval gate.

## Result on the real 440 actionable failures

**Safely batchable: 5 single-source clusters, 122 failures (28%)** — one templated fix each:

| n | kind | shared key |
|---:|---|---|
| 83 | missing_key | `plan_pool` (the async-contract drift) |
| 15 | value_mismatch | `app.api.voice` vs `main` (a route-owner rename) |
| 11 | missing_fields | `backend_authoritative,command_results,…` (a contract change) |
| 8 | policy | `apply_allowed` |
| 5 | invariant | `runtime_level` |

**Refused (over-merge guard), 318 (72%):** the `not found in …` clusters (×43 at 7% homogeneity, ×31 at
23%) share a signature SHAPE but are individual assertions; `assert X in X` / `IndexError` have no
concrete extractable key. These are correctly NOT batched.

## Honest bound

The earlier "75% batchable" was raw signature clustering. Demanding a TRUE single cause drops it to a
confident **28%** — the 47% gap is exactly the over-merging the guard prevents (a wrong batch edit
avoided). Growing the batchable share is a matter of teaching `extract_cause` more cause kinds (e.g.
`IndexError` downstream of `plan_pool`), not loosening the guard.

## Files

- `agent/twin_control_plane/shared_cause_repair.py` (+ `tests/test_shared_cause_repair.py`, 10 tests).

## Next (behind an approval gate)

For a batchable cluster: detect the single shared SOURCE change (git/contract diff), synthesise the
templated test-input fix, run it through `assertion_preserving_edit`, apply, and verify deterministically
via the `improvement_loop` (run impacted tests, Git-rollback on failure). All frontier-free.
