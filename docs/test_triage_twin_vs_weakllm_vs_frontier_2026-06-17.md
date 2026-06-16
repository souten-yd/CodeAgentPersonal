# Test triage: deterministic Twin vs Twin+weak-LLM vs frontier — 2026-06-17

After the end-to-end triage runner (#1908) landed, the three triage strategies were compared on the
same tests, as requested: the **deterministic** Twin triage (real per-test coverage, no model), the
**Twin + weak LLM** combination (the 8080 Mistral-Small-24B judging with the Twin's coverage facts),
and a **frontier** model (reading the test code = ground truth).

## Method

The hardest classification is REDUNDANT (re-run/stale/coverage-gap are direct set operations). So the
comparison focuses there, on `tests/test_text_normalizer_jp_extra.py` — six tests that all call the
same `_normalize`, which the naive symbol-coverage heuristic flags as redundant. Each strategy judges
whether two such tests are truly redundant (one could be deleted):

- **Deterministic**: redundant only if the two tests have the IDENTICAL line-coverage signature
  (`coverage_ingest` + `coverage_triage` with `redundancy_signatures`).
- **Twin + weak LLM**: the 8080 model judges from the two test bodies (Twin coverage facts available).
- **Frontier**: reads the assertions — these test distinct behaviors (period kept / no joining / emoji
  removal / URL removal / punctuation collapse), so they are NOT redundant.

## Result

| Pair (vs `test_keeps_sentence_period_separator`) | Deterministic (line) | Weak LLM (8080) | Frontier (truth) |
|---|---|---|---|
| `test_no_unnatural_sentence_joining` | not redundant ✅ | **redundant ✗** | not redundant |
| `test_emoji_removed_with_sentence_pause_kept` | not redundant ✅ | not redundant ✅ | not redundant |
| `test_url_removed_without_breaking_sentence_boundary` | not redundant ✅ | not redundant ✅ | not redundant |
| `test_repeated_punctuation_collapses_naturally` | not redundant ✅ | not redundant ✅ | not redundant |

| Strategy | Agreement w/ frontier | Speed |
|---|---|---|
| **Deterministic (Twin line coverage)** | **4 / 4** | whole-suite triage **0.04 s**, no model |
| **Twin + weak LLM (8080)** | 3 / 4 (one false "redundant") | ~1 s / pairwise judgment (≈17 min for the suite) |
| Frontier | ground truth | minutes of reasoning |

## Conclusion

- For judgments that **coverage can decide** (re-run, stale, coverage-gap, and redundancy at line
  granularity), the **deterministic Twin triage matches the frontier model and is ~10³–10⁵× faster
  with no model**. Adding a weak LLM here *reduces* accuracy (it invented one false redundancy) and is
  far slower.
- The weak LLM (and even the frontier model) is therefore **not needed for the bulk of the triage**.
  Reserve a model only for the genuinely ambiguous tail — two tests with *identical* line coverage
  whose *intent* still differs — which line coverage alone cannot separate. That residual is small.
- This confirms the design: **deterministic-first** (Twin + real coverage), model only for the
  ambiguous remainder. "Triage the suite with the Twin and as little LLM as possible" is achieved, and
  the data shows *less* LLM is actually *more* accurate here.

## Caveat

Coverage-gap and full redundancy counts are only meaningful over **full-suite** coverage; the runner's
`collect_coverage` should be run across the suite once (CI) and updated incrementally. The per-query
triage over the resulting data is sub-second.

## Reproduction

- Deterministic: `triage_runner.run_test_triage(...)` on a coverage file from
  `pytest --cov=agent --cov=app --cov-context=test`.
- Weak LLM: `AtlasLLMJsonAdapter(base_url="http://127.0.0.1:8080", model="Mistral-Small-3.2-24B-Instruct-2506-Q3_K_S.gguf")` judging each pair.
- Frontier: reading the assertions in `tests/test_text_normalizer_jp_extra.py`.
