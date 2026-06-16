# 50-test triage: deterministic Twin feature vs frontier — 2026-06-17

A concrete run of the shipped triage feature (`triage_runner` over real per-test coverage) on a ~50+
test sample, judged against a frontier model that reads each test. This is the decisive evaluation of
which classifications the deterministic engine can own and which genuinely need a model.

## Setup

- Sample: 64 tests with coverage across `test_text_normalizer_jp_extra.py`,
  `test_decomposition_policy.py`, `test_coverage_triage.py`, `test_twin_test_management.py`,
  `test_reference_check.py`.
- Coverage collected with `pytest --cov=agent --cov=app --cov-context=test` (12 s); triage 13.5 s
  (dominated by the one-time snapshot load; the classification itself is sub-second).
- Deterministic engine = `coverage_triage` with **line-level** redundancy signatures.

## Result by classification

| Classification | Deterministic verdict | Frontier judgment | Verdict |
|---|---|---|---|
| **RE-RUN (impacted)** | tests covering the changed symbol | same | ✅ deterministic correct |
| **STALE** | 0 (no test covers only removed symbols) | none stale in sample | ✅ correct |
| **COVERAGE_GAP** | symbols with no covering test | correct *given the sampled coverage* | ✅ (needs full-suite coverage to be complete) |
| **REDUNDANT / consolidate** | **22 / 64 flagged** (all in the normalizer file) | **~21 are false positives** | ❌ deterministic over-flags |

## Why REDUNDANT over-flags — reading the 22

The 22 flagged tests share an identical *line* signature because they all execute the normalizer's
main path — but with **different input data guarding different regressions**, so they are NOT
redundant:

- `test_decimal_gb_not_broken` (GB→ギガバイト) vs `test_decimal_khz_not_broken` (kHz→キロヘルツ) — different units.
- `test_dictionary_katakana_{github_docker, gpu_vram, python_fastapi, runpod…}` — different dictionary terms.
- `test_power_unit_readable` (kW), `test_voltage_unit_readable` (V), `test_version_not_broken` (v1.2),
  `test_no_notation_kept_readable` (No.1), `test_markdown_cleanup…`, `test_url_removed…` — each a distinct behavior.

Only `test_keeps_sentence_period_separator` vs `test_period_kept_between_sentences` are near-duplicates
(both assert exact period preservation) — ~1 genuine consolidation candidate.

**Deterministic REDUNDANT precision on this sample ≈ 1/22 ≈ 5%.** The frontier model, reading the
inputs/assertions, is far more accurate, because redundancy is about *what the test asserts*, which
line coverage cannot see (same code path ≠ same test).

## Conclusion — what is deterministic, what needs a model

- **RE-RUN / STALE / COVERAGE_GAP: deterministic (Twin + coverage), no model.** These are "which
  symbols", which coverage decides exactly and fast.
- **REDUNDANT / consolidate: needs a model.** Coverage (even line-level) cannot tell a parametric
  guard from a duplicate. The right pattern is **Twin narrows, model confirms**: line signatures group
  *candidate* duplicates (cheap, deterministic), then a model judges only that small narrowed set by
  reading the assertions. RETIRE/CONSOLIDATE are already approval-gated, so a human (or model) is in
  the loop before anything is deleted — the engine must NOT auto-consolidate on the line-signature
  alone.

This refines the earlier reports: line-level beats symbol-level redundancy, but at sample scale it
still over-flags parametric tests, so consolidation is the one classification where a model earns its
place. Everything else is deterministic.

## Action taken

`build_test_management_plan` already marks CONSOLIDATE (and RETIRE) `approval_required=True` and never
auto-deletes — consistent with this finding (a line-signature group is a *candidate*, not a decision).
The follow-up is to route only that narrowed candidate set to a model for the final redundancy call.
