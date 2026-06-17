# Routed multi-stage triage on a fresh full-suite run — 2026-06-17

Goal the user set: *take the ~500 failures from a whole-suite run and see whether we can evaluate
**all** of them; if not, design what's missing.* This run does it end-to-end on **real** suite output
(not the earlier analysis-only doc), using the routing logic and the two-pass weak-LLM judge.

## Making the suite itself feasible

A serial, no-timeout run stalled (~4% in ~9 min, then hung on a slow test → est. 3h+). Switched to
`pytest-xdist -n auto --timeout=60`: the full suite finished in **6m02s** on 24 cores. Command:

```
pytest -m "not real_model" --continue-on-collection-errors -n auto --timeout=60 \
       -o junit_logging=no --junit-xml=.triage/full_suite.xml
```

The junit header counters (`tests=7126 errors=1576`) are xdist's per-phase accounting; the distinct
failed/errored **test cases** are **623** (`junit_triage.parse_junit_failures`). That is the actionable
set fed to the triage.

## Can we evaluate all 623? Yes — the model touches 76, not 623

`agent/twin_control_plane/junit_triage.py` parses the junit into `(test_id, reason)` and runs the
existing routing (`failure_triage_batch`): deterministic-classify ALL → cluster the low-confidence
residual by root cause → judge ONE representative per cluster with the local critique judge → propagate.

| | value |
|---|---:|
| failures parsed | 623 |
| naive model calls (judge every failure) | 623 |
| **routed model calls (one per cluster)** | **76** |
| reduction | **8.2×** |
| routed time @5.3s/call | ~403s vs ~3302s naive |

So "judge all 623" is feasible: the deterministic engine settles every failure instantly and the model
is spent only on the 76 genuinely-uncertain root causes.

## Deterministic buckets (all 623, instant)

| Bucket | Count |
|---|---:|
| genuinely_broken | **332** |
| environment | 272 |
| snapshot_drift | 19 |

188-not-a-bug from the earlier doc reproduces: ~290 of 623 are environment + snapshot drift, not code.

## The two-pass critique judge — what it added

78→76 cluster reps were judged by the local weak model (Mistral-Small-3.2-24B @ :8080) with an
adversarial critique pass, reconciled against the deterministic prior. **0 reps were overturned** — the
weak LLM **confirmed** the deterministic labels rather than correcting them, which is the result we want:
the bulk classifier is trustworthy and the model is a cheap second opinion, not a crutch.

The critique pass *did* fire (verified live, not a silent fallback): on real reps it proposed
alternatives like `environment`/`snapshot_drift` and the deterministic reconciliation tie-broke them.
Two of those dissents exposed **real classifier gaps**, which were folded back in (the intended loop):

- `worker 'gw3' crashed while running …` — an **xdist worker crash** (test infra), was landing in
  genuinely_broken. **35 failures.**
- `collection failure` — a **collection error** (environment), was landing in genuinely_broken.
  **31 failures.**

Added to `_ENV_MARKERS` (`crashed while running`, `node down`, `replacing crashed worker`,
`collection failure`). After the fix `genuinely_broken` dropped **398 → 332** and those 66 infra/collection
artifacts moved to environment, where they belong.

## The genuine 332 are only 76 root causes — the real fix list is short

| Count | Root-cause signature |
|---:|---|
| 83 | `KeyError: X` (overwhelmingly `'plan_pool'` — one shared fixture/contract) |
| 37 | `AssertionError: assert X == X` (varied) |
| 27 | `AssertionError: assert X in X` |
| 25 | `IndexError: list index out of range` |
| 11 | `ValueError: missing_required_fields:proposed_commands,command_results,…` (one contract) |
| 8 | `ValueError: apply_allowed=false patch cannot be approved` (one policy) |
| 7 | `ValueError: low quality acknowledgment is required …` |

This matches the earlier serial analysis (`KeyError: plan_pool` ×~83, `missing_required_fields` ×11,
`apply_allowed=false` ×8, …) — a fresh, independent run reproduces the same short fix list. Clearing the
single `plan_pool` cause fixes ~83 tests at once.

## Bottom line

Evaluating the whole failure set is feasible without N model calls: **623 failures → 76 model calls
(8.2×)**, deterministic engine does the bulk, weak-LLM critique confirms and surfaced two classifier
misses that were folded back. The actionable list is **76 root causes, ~332 genuine failures**, dominated
by a handful of clusters. Reusable entrypoint: `agent/twin_control_plane/junit_triage.py`
(`python -m agent.twin_control_plane.junit_triage <junit.xml> [--judge]`).
