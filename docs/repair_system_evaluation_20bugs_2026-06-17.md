# Evaluating the triage + repair loop on 20 injected bugs — 2026-06-17

A controlled experiment: 20 functions with passing tests, then ONE bug injected at a time (4 difficulty
tiers, 5 each), each run through the REAL tools — `deterministic_panel.classify_with_panel`,
`cause_discovery.diagnose`, `shared_cause_repair` — with known ground truth. Measures what the
frontier-free system does well and where it falls short. (Harness: `buggeval/` sandbox, isolated from the
main suite.)

## The bug set (tiers)

1. mechanical: typo→NameError, key rename→KeyError, off-by-one, operator swap, arithmetic.
2. contract/data: map value, dropped field, inverted invariant, inverted policy, wrong split.
3. needs-context: edge calc, clamp swap, branch threshold, deprecated method→AttributeError, modulo.
4. semantic/multi: accumulation, dict-merge order, inverted guard, key rename, order-of-operations.

## Scorecard

| stage | result | |
|---|---:|---|
| **reproduced** (bug → real failure) | **20 / 20** | sanity |
| **classification** (panel: genuine vs env/snapshot/debt) | **20 / 20 (100%)** | **strong** |
| **cause located** (origin found in source) | **7 / 20 (35%)** | **partial** |
| **auto-fixed** (loop produced a verified fix) | **0 / 20 (0%)** | **the gap** |

## What works well

**Classification is excellent and frontier-free.** Every genuine bug was bucketed `genuinely_broken`,
including ones designed to fool it: a list-mismatch (`['a, b ,, c'] == [...]`), an `invariant_violation`
ValueError, an `apply_allowed=false` policy ValueError — none were mis-flagged as environment or snapshot
drift. The multi-prior panel does the bulk classification reliably without a model.

## Gap A — localization splits cleanly by raise-vs-value (partially closed)

Signal-grep located exactly the 7 bugs whose signal is a **string literal in the source** — KeyError keys
(`'planpool'`, `'values'`), exception messages (`invariant_violation`, `apply_allowed`), a string constant
(`'B'`), an attribute (`capitalise`), a NameError name (`nam`).

Added this session: `locate_from_traceback` (ANSI-robust) parses the failure's deepest in-project frame.
But it revealed a sharper truth — **it only helps bugs that RAISE.** A value/logic bug
(`assert 8 == 9`, `assert None == 3.0`, `[1,2,3] == [1,3,6]`) lets the product function return normally
and fails on the assertion **inside the test**, so the traceback names the TEST line, not the product
line. Neither grep nor traceback can reach the buggy product code for those.

So localization is **~45% (the raising bugs)** and the residual **value bugs need a different technique**:
the failing test body names the function it calls (`s.f11_avg(...)`), and the Twin already has per-test
**coverage + a symbol graph** (`coverage_ingest`, `twinproof`) that maps a test to the product symbols it
exercises. Wiring that into `cause_discovery` would localize value bugs to their function — the Twin
capability exists; it just isn't connected to the diagnosis path yet.

## Gap B — no general code-fix synthesis (the dominant gap)

0/20 were auto-fixed. The repair templates (`sync_contract_repair`) are **contract-drift specific**; a
generic logic bug (wrong operator, off-by-one, bad arithmetic) has no template, so the loop has nothing to
apply. The `failure_repair_loop` correctly does nothing rather than thrash — but "self-heal any bug" needs
a **weak-LLM code-synthesis** step: given the located function (Gap A) + the failing assertion, propose a
minimal code edit, gated by the existing deterministic verify (run the test) + assertion-preservation +
Git-rollback. The safety rails are already built; the generator is the missing piece.

## On "peel through automatically"

The auto-peel loop (diagnose → fix → verify → repeat) works **today for chained drifts whose every layer
has a template** (the plan_pool→verification/run sync chain). This evaluation shows the general case is
blocked on Gap B: without a synthesize step, peeling stops at the first non-templated cause. With Gap A
(traceback location) + Gap B (weak-LLM synthesis) wired into `failure_repair_loop`, the loop would peel
arbitrary chains frontier-free, each step verified deterministically.

## Gap B closed — weak-LLM code synthesis fixes 18/20 (follow-up)

`code_synthesis_repair` adds the general fixer: given the LOCALIZED function + the failing test, the local
weak LLM (Mistral-Small @ :8080) proposes a corrected version of *that one function*, applied behind the
deterministic gate (run the test → keep, else Git-rollback). Safety is structural — it replaces only the
single AST-bounded function, never edits the test (the spec), and rejects any candidate that doesn't parse
or renames the function.

Re-run over the same 20 bugs (clean localization), **18/20 were fixed and verified** — T1 5/5, T2 4/5,
T3 5/5, T4 4/5 — up from **0/20**. The 2 misses (`b10-split`, `b20-multiop`) were safely rolled back (the
model's edit failed the test). So **given localization, the weak LLM is ~90% effective**, frontier-free,
each fix proven by the test.

This relocates the bottleneck back to **localization** (Gap A): the synthesis demo used a clean
test→function map; in the wild, value-bug localization still needs the Twin's coverage/symbol graph. The
fixer is no longer the gap — connecting localization to it is.

## Bottom line

The frontier-free system is **strong at triage/classification (100%)**, **partial at localization (~45%
— raising bugs via signal/traceback; value bugs need the Twin's coverage graph, not yet wired)**, and
**has no general fixer (0%)** — only templated contract-drift repair. Prioritized gaps:
1. **value-bug localization** — connect per-test coverage / the symbol graph (the Twin already has these)
   to map a failing test to the product function it exercises;
2. **weak-LLM code synthesis** — given the localized function + the failing assertion, propose a minimal
   edit behind the existing verify + assertion-preservation + Git-rollback gate (the safety rails exist;
   the generator is missing) — this is what makes the auto-peel loop close on arbitrary bugs, not just
   templated drifts.

Useful today as a triage + (raising-bug) localize + templated-repair engine; a general self-healer after
(1) and (2). The added `locate_from_traceback` is step one.
