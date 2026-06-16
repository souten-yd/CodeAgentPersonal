# Full-suite triage of KasaneCore — tests + source bloat — 2026-06-17

The whole suite was run once with per-test coverage (`pytest --cov=agent --cov=app
--cov-context=test`, 4 h 21 m: 4,947 passed / 559 failed / 31 errors — failures are
environment-dependent and do not affect the coverage data), then triaged deterministically with the
shipped engine. Source-code bloat was triaged from the AST in the same pass. **No model.**

## Test triage (deterministic, ~14 s after the one-time Twin load)

| Classification | Count | Notes |
|---|---|---|
| Tests with source coverage | **3,874** | of 4,936 measured contexts (the rest exercise no `agent/app` symbol) |
| Source symbols (existing) | 6,114 | function/method/class nodes in the Twin |
| **REDUNDANT / consolidate** (I/O signature) | **59** | tests with an identical input/output signature to another — genuine consolidation candidates |
| **STALE / retire** | 22 | **mostly snapshot drift** — see caveat |
| **COVERAGE_GAP / add test** | **1,764 / 6,114 (29%)** | source symbols no test exercises |

- REDUNDANT uses the **I/O signature** (#1912), so the parametric false positives (line coverage gave
  hundreds) are gone — 59 is the real, small set.
- All retire/consolidate actions are **approval-gated**; nothing is auto-deleted.

## Source-code bloat (duplicate functions)

| Metric | Count |
|---|---|
| Duplicate-structure groups | **261** |
| …cross-file (real reimplementation) | **165** |

Top reimplemented helpers (same AST structure across many files) — clear consolidation wins:

| Helper | Reimplemented in | Verdict |
|---|---|---|
| `_utc_now_iso` (timestamp) | **109 files** | consolidate to one shared util |
| `_ensure_under` (bound check) | 44 | consolidate |
| `_profile_id` / `_session_id` / … (id accessors) | 23 | consolidate to a generic accessor |
| `load_*` checkpoint loaders | 20 | factory |
| `get_*_provider` (FastAPI DI) | 31 | boilerplate — judgment needed (distinct deps) |
| `get_policies` / `policies` | 16 | factory |

`_utc_now_iso` × 109 is the standout: a one-line timestamp helper copied into ~every schema file —
exactly the "same function built again" bloat. Consolidating it to a single util removes ~108 copies.

## How decisions map (wire / delete / consolidate / fix)

- **Duplicate** → CONSOLIDATE (approval): merge to one implementation; `project_intelligence/consolidation`
  provides the safe consumer-cutover mechanism once decided.
- **Dead** (defined ∧ no static caller ∧ never executed ∧ not entry/public/Protocol/decorated) → DELETE
  (approval) or, if recently added and meant to be used, **WIRE**. Requires the fresh Twin + this
  full-suite coverage together (the static "no caller" signal alone over-flags ~35%).
- **Coverage gap** → ADD a focused test (autonomous).
- **Redundant test** → CONSOLIDATE (approval).

## Caveats (honest)

1. **Snapshot drift inflates STALE / COVERAGE_GAP.** The Twin snapshot used here was built earlier in
   the session, before several modules added during it (`coverage_ingest`, `coverage_triage`,
   `source_triage`, …). Tests covering those new symbols look "stale", and the new symbols look
   "uncovered". For a trustworthy stale/gap count, rebuild the Twin against the exact coverage revision
   and re-run — the engine is the same; only the inputs need to be co-revisioned.
2. Some duplicate groups (`get_*_provider`, `get_policies`) are structurally identical **boilerplate**
   with distinct intent; the structure hash surfaces *candidates*, and consolidation for those needs a
   judgment call (which is why CONSOLIDATE is approval-gated, not automatic).
3. Coverage was collected with `not real_model`; service/browser-dependent tests that errored are not
   represented in the coverage and so are excluded from this triage.

## Bottom line

The whole suite is triaged deterministically in seconds. The high-confidence, immediately-actionable
findings: **59 redundant-test consolidation candidates**, **~29% coverage gap**, and **165 cross-file
duplicate-function groups led by `_utc_now_iso` (109 copies)**. Stale/dead need a co-revisioned Twin to
be trustworthy; the mechanism is in place.
