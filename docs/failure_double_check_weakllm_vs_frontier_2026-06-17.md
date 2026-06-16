# The failure double-check without a frontier model — 2026-06-17

Concern (the user's): the failure-classification *double-check* — catching the cases the deterministic
rules mis-bucket (CRLF, platform-conditional, UI snapshot drift) — was done by a frontier model. If
that judgment can only be done by a frontier model, the system depends on one. It must be doable with
KasaneCore + the local 8080 weak model.

## Result: the weak model reproduces the frontier double-check

`failure_judge.judge_failure_with_llm` gives the local 8080 model the failure reason plus the
deterministic label as a prior, and asks for the same four buckets. On the 10 cases the frontier review
had reclassified (CRLF, runpod/cuda, UI drift) plus clear genuine bugs:

| Source | Agreement with frontier (ground truth) |
|---|---|
| Deterministic rules | **9 / 10** (missed a CRLF case — brittle string marker) |
| **Weak LLM (8080)** | **10 / 10** |
| Frontier | ground truth |

The weak model matched the frontier exactly — and was **more robust than the brittle string rules**,
correctly calling `'asset ready\r\n' == 'asset ready\n'` an *environment* (CRLF) failure where the
deterministic marker missed it. Most judgments returned in ~1 s.

## Conclusion

The double-check is **not** a frontier-only capability. The intended division of labor, all on
KasaneCore + 8080, with no frontier model in the loop:

1. **Deterministic rules** bucket the bulk instantly (and are the fallback).
2. **The weak LLM** is the second opinion on the residual/ambiguous — it caught what the rules missed.
3. Frontier is then optional: a periodic spot-check, not a dependency.

So the processes the frontier model was doing in this session — classify, double-check, refine — can
run inside KasaneCore with the weak model. `failure_judge` is the first such "frontier-independent
double-check"; the same pattern (deterministic-first, weak-LLM second opinion, frontier optional)
applies to the test/source triage judgments too.
