# End-to-end staged repair on REAL failures — with frontier verification — 2026-06-17

Ran the staged repair loop (Twin + weak LLM, frontier-free) on **15 real genuine, non-test-debt failures**
from the suite (`.triage/full_suite.xml`), then had the frontier (Opus) verify each kept fix. This is the
reality check the sandbox could not give.

## Result: 1/15 passed the test — but it was a SPURIOUS fix → 0/15 correct

| outcome | n | meaning |
|---|---:|---|
| fixed (test passed) | 1 | **rejected by frontier review — bogus** (see below) |
| rolled_back | 11 | coverage found candidates, synthesis tried 3 each, none passed → reverted |
| skipped | 3 | no localizable function (doc-content assertions) |
| **frontier-verified correct** | **0** | |

### The single "fix" was a false positive — why frontier verification is essential

Failure: `NameError: name 'threading' is not defined`. The weak LLM's accepted edit:

```diff
 def normalize_action_type(action_type):
     if value in {"write", "add"}: return "create"
+    if value in {"apply"}: return "update"
     return ""
```

It edited a **completely unrelated** function (`normalize_action_type`) with an arbitrary `apply→update`
mapping that has nothing to do with the `threading` NameError — yet the one test passed. **A single-test
deterministic verify cannot tell a real fix from a coincidental pass.** Only the frontier review caught
that the edit was bogus. This validates the standing instruction to keep a frontier (dev-time) verifier:
the weak LLM + single-test gate produces false positives.

## The sandbox→real gap

The 19/20 sandbox result did NOT transfer. Real failures are not clean single-function logic bugs:
- **test-debt downstream** (`IndexError` after the plan_pool fallback) — editing product code to satisfy a
  stale test is *wrong*; the loop correctly rolled these back (10 of the 11);
- **doc/content assertions** (`'PR-ATLAS-PIPE-55' in <doc>`) — nothing to synthesize (skipped);
- **config/routing** (`assert 404 == 200`) — multi-file/registration, not one function.

Static localization also failed on every layered test (the test calls `client.post(...)`, not a product
function), so Stage A localized nothing; coverage (Stage B) found functions but the candidates were
broad/unrelated.

## Timing (per process type — measured)

15 failures, **338s total (~22s/failure avg**, range 2s–87s):

| step | per-op | calls | notes |
|---|---:|---:|---|
| static localize (Stage A) | ~ms | 15 | negligible; found nothing on layered tests |
| **coverage localize (Stage B)** | **5.1s avg** | 15 | up to **23s** on a heavy test (runs the test under coverage) |
| **weak-LLM synthesis** | **4.6s/call** | 35 | ~3 candidate attempts per residual |
| **verify (single pytest)** | **2.3s/run** | 34 | one test in isolation |

So the cost per failure ≈ coverage(5s) + 3×[synth(4.6s)+verify(2.3s)] ≈ 25s. The staging worked as
designed (coverage paid once per failure, not per candidate; static-first kept the cheap path cheap), but
the dominant cost is the 3 synth+verify attempts, and they rarely succeed on real failures.

## Honest conclusion

Frontier-free, the system is a **strong classifier (100%) + a localizer + a synthesizer that excels on
clean single-function bugs (sandbox 19/20)** — but on the REAL suite it fixed **0/15 correctly**, because:
1. real failures are dominated by test-debt / doc / config / multi-file causes, not single-function bugs;
2. layered tests defeat static localization; coverage localizes but with noisy candidates;
3. **a single-test verify admits spurious fixes** — frontier (or a stronger gate: require the edit to
   reference the failure's symbol, and re-run the broader impacted set) is required before trusting a fix.

Net: the machine is real and safe (it rolled back / skipped 14/15 and the frontier rejected the 15th), but
it is **not yet a real-world auto-fixer**. The next investments are (a) a stronger acceptance gate than
"one test passes", and (b) test-debt-aware handling (most real failures want a TEST update or human
judgment, not product-code synthesis).
