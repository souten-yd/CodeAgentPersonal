# Triaging the 559 full-suite failures — 2026-06-17

The full-suite run produced 559 failures + 31 collection errors. Triaging them by hand is exactly the
work we want to avoid, so they are bucketed deterministically (`failure_classifier`) into the four
kinds the user named, then the residual real failures are clustered by root cause. A frontier model
double-checked the buckets (its intended role) and the misses it found were folded back into the
classifier.

## Buckets (deterministic, 590 classified)

| Bucket | Count | Meaning / action |
|---|---:|---|
| **ENVIRONMENT** | **113** | missing file/service, CRLF vs LF, cp932, runpod/cuda-conditional, browser — fix the env, not the code |
| **COLLECTION_ERROR** | 31 | the test file could not be imported (missing `web/atlas-next`, encoding) — environment |
| **SNAPSHOT_DRIFT** | 44 | asserts on a rendered UI / `index.html` / `<!doctype html>` whose source changed — update the TEST |
| **TEST_DEBT** | 0 | (no deprecation/xfail markers in this run) |
| **GENUINELY_BROKEN** | **401** | real logic failures — the actionable set |

So **188 / 590 (32%) are not code regressions** (environment + collection + snapshot drift) and should
not be "fixed" in code.

## The genuine 401 are far fewer real bugs — root-cause clusters

Clustering the 401 by normalized root-cause signature: **120 distinct root causes**, heavily clustered:

| Count | Root-cause signature |
|---:|---|
| 82 | `KeyError: X` (almost all `'plan_pool'` — one shared fixture/contract) |
| 75 | `AssertionError: assert X == X` (varied) |
| 27 | `IndexError: list index out of range` |
| 11 | `ValueError: missing_required_fields:proposed_commands,command_results,…` (one contract change) |
| 8 | `ValueError: apply_allowed=false patch cannot be approved` (one policy) |
| 8 | `assert True is False` |
| 7 | `ValueError: low quality acknowledgment is required …` |
| 5 | `ValueError: invariant_violation:runtime_level` |

The single `KeyError: 'plan_pool'` cluster fails ~82 tests — fixing that one cause clears them all. The
top ~10 clusters cover a large fraction of the 401, so the real fix list is short.

## The frontier double-check (its intended role)

The first deterministic pass over-counted GENUINELY_BROKEN at 452. A frontier review of the residual
samples found three mis-bucketed causes, which were added to the classifier:

- `'asset ready\r\n' == 'asset ready\n'` → **CRLF / line ending** (Windows) → ENVIRONMENT.
- `'cpu' == 'cuda'`, `runpod skips profile detection` → **platform-conditional** → ENVIRONMENT.
- `id="atlas-…"`, `data-atlas-plan-card`, `<!DOCTYPE html>` asserts → **UI snapshot drift** → SNAPSHOT_DRIFT.

After folding these in, GENUINELY_BROKEN dropped 452 → 401 and SNAPSHOT_DRIFT/ENVIRONMENT rose
accordingly. This is the deterministic-engine + frontier-double-check loop working as intended: the
machine does the bulk classification fast, the frontier catches the misses, the rules improve.

## Bottom line

559 failures → **113 environment + 31 collection + 44 snapshot-drift (= 188 not-a-code-bug)** + **401
genuine, which are only ~120 distinct root causes** dominated by a handful of clusters (`KeyError:
plan_pool` ×82, `missing_required_fields` ×11, …). The actionable fix list is the top clusters, not 559
individual failures. Reusable: `agent/twin_control_plane/failure_classifier.py`.
