# Test triage: deterministic (Twin, no-LLM) vs frontier judgment — 2026-06-17

Goal: triage the KasaneCore test suite (re-run / retire-stale / consolidate-redundant / add-coverage)
with the **Twin and no LLM**, as fast as possible; then evaluate whether it is usable by comparing
its judgments against a frontier model's.

## What was built

- `coverage_triage.build_coverage_triage(coverage_map, existing_symbols, changed_symbols)` — a pure,
  deterministic classifier: from a `{test -> covered source symbols}` map it computes IMPACTED (re-run),
  STALE, REDUNDANT, COVERAGE_GAP by set operations, and chains into the approval-gated
  test-management plan (`#1899`/`#1905`). No model.
- Coverage source for this evaluation: the **Twin static call graph** (a test "covers" the source
  symbols it calls, depth ≤ 2). `coverage` / `pytest-cov` are not installed, so this is the available
  no-LLM source; it is a *static* proxy for runtime coverage (see limitations).

## Measured on the cleaned KasaneCore Twin (216,033 nodes)

| Step | Result |
|---|---|
| Snapshot load (once, cached) | 46 s |
| Static coverage map build | < 1 s (3,411 of 6,772 test fns call ≥1 agent/app source symbol) |
| **Deterministic triage** | **0.04 s** (no LLM) |
| IMPACTED (re-run, per change) | reliable — e.g. changing `decomposition_policy.py` → `test_decomposition_policy.py` (4 files / 1027) |
| STALE candidates | **0** |
| REDUNDANT candidates | 2,220 |
| COVERAGE_GAP | 4,355 / 6,114 source symbols (71%) |

Speed vs an LLM judging each of ~1,027 tests (~seconds each → hours): the deterministic pass is
**~0.04 s for the whole suite** — about five orders of magnitude faster, and exact.

## Frontier comparison (frontier = reading the actual test code)

| Classification | Deterministic (static Twin) | Frontier judgment | Agreement |
|---|---|---|---|
| **IMPACTED / re-run** | tests that call the changed symbol | same set (call-graph is exhaustive) | ✅ agree |
| **STALE** | 0 (static graph has no edges to *removed* symbols) | cannot be derived statically either | — (both blind) |
| **REDUNDANT** | 2,220 (tests sharing a covered symbol) | **mostly NOT redundant** | ❌ disagree |
| **COVERAGE_GAP** | 71% uncovered | overstated (static misses indirect/fixture coverage) | ❌ disagree |

Concrete REDUNDANT false positives — `tests/test_text_normalizer_jp_extra.py`, all flagged because
they call the same `_normalize()`:

- `test_keeps_sentence_period_separator` — asserts the sentence period is kept
- `test_no_unnatural_sentence_joining` — asserts sentences are not joined
- `test_emoji_removed_with_sentence_pause_kept` — emoji removal
- `test_url_removed_without_breaking_sentence_boundary` — URL removal
- `test_repeated_punctuation_collapses_naturally` — punctuation collapse
- `test_markdown_cleanup_heading_and_bullets` — markdown cleanup

Frontier verdict: **distinct behavioral cases of one function — not redundant.** Static coverage
flags them only because "covers the same symbol" ≠ "asserts the same behavior".

## Verdict — is it usable?

- **IMPACTED / re-run: usable today, no LLM, fast and accurate.** This is the highest-value, most
  frequent operation ("run these 4, not all 1027"). The Twin static call graph is sufficient and
  matches the frontier/grep ground truth.
- **STALE / REDUNDANT / COVERAGE_GAP: not usable from the static graph.** Static coverage = "calls the
  symbol", which cannot see removed-symbol coverage (stale), conflates behavioral cases (redundant
  false positives), and misses indirect coverage (gap overstated). Here a frontier model, reading the
  assertions, beats the static heuristic.

Net: the no-LLM deterministic engine is correct and ~10⁵× faster than an LLM — but its **accuracy is
bounded by the quality of the coverage input**. With a *static* proxy it is trustworthy only for re-run.

## Recommendation

1. **Ship deterministic re-run selection now** (no LLM, no coverage.py) — it is accurate and fast.
2. **Ingest real per-test runtime coverage** (coverage.py test contexts → map covered lines to Twin
   symbols). With true coverage, STALE / REDUNDANT / COVERAGE_GAP become accurate AND stay
   deterministic — still no LLM, still sub-second per query, the suite run amortized in CI.
3. **Use a frontier/weak LLM only for the residual** — e.g. deciding whether two tests with identical
   *runtime* coverage are *semantically* redundant (the one judgment a coverage set cannot make).

So "judge with as little LLM as possible, fast" is achievable: deterministic for everything coverage
can decide, LLM only for the genuinely ambiguous tail.

## Reproduction

- Classifier: `agent/twin_control_plane/coverage_triage.py` + `tests/test_coverage_triage.py`.
- Static coverage map: for each test symbol node, the resolved `py://agent|app/...#sym` targets of its
  `calls`/`imports` edges (depth ≤ 2) on the cleaned KasaneCore Twin.
