# Multi-perspective verification — scoring instead of a single signal (2026-06-17)

A change was being kept/rolled-back on a single signal ("the tests pass", "the model says ok"). That is
brittle: the tests may not cover the change, the model may be wrong on the first try. The user asked for
two things — evaluate from MULTIPLE perspectives and use the SCORES, and let the LLM judgment take a
critical/alternative viewpoint rather than deciding in one shot. Both are now implemented, frontier-free.

## Layer 1 — deterministic multi-perspective panel (`verification_panel.py`, no model)

A change is scored from independent angles; each perspective returns a score in [0,1] + findings.

| Perspective | 観点 | Check | Score | Role |
|---|---|---|---|---|
| `syntax` | 構文検証 | every changed `.py` parses (`ast.parse`) | 1.0 / 0.0 | **gating** — a SyntaxError short-circuits to REJECT; no point running tests on code that does not parse |
| `reference` | 参照検証 | no import/call of a project symbol that does not exist (`reference_check` vs the Twin index) | 1−invented | abstains when there is no project import |
| `semantic` | 意味検証 | the baseline-comparison verdict on impacted tests (`baseline_verify`) | PASS 1.0 / AMBIGUOUS 0.5 / FAIL 0.0 / UNVERIFIABLE abstain | highest weight |

`aggregate()`: a gating perspective below threshold = hard REJECT (short-circuit). Otherwise the
confidence is the weighted mean of the non-abstaining perspectives → **ACCEPT** (≥ accept threshold) /
**REJECT** (< review floor) / **REVIEW** (in between, or everything abstained). Default weights
syntax 1 · reference 2 · semantic 3, so e.g. an invented reference with otherwise-passing tests scores
(1+0+3)/6 ≈ 0.67 → REVIEW, not a silent accept.

The point: the machine settles ACCEPT and REJECT on its own; only the genuinely inconclusive **REVIEW**
residual is escalated — so the weak LLM is used minimally, exactly per the standing policy.

## Layer 2 — critique-based weak-LLM judge (`critique_judge.py`, 2 calls, deterministic reconcile)

For the residual, the model does not decide in one shot:

1. **propose** — `failure_judge.judge_failure_with_llm` classifies (with the deterministic prior).
2. **critique** — the model is shown its own proposal and asked for the strongest argument it is WRONG
   plus a single alternative (批判的意見 / 別観点) — an adversarial second viewpoint.
3. **reconcile** — deterministic, no third call: agreement → high confidence; on dissent the candidate
   matching the deterministic prior wins (a tie-break the model cannot skew); if proposal, critique and
   prior all disagree it is marked **CONTESTED** (low confidence) and anchored on the prior.

Two model calls, deterministic reconciliation, never raises (falls back to the deterministic label).

## Why this respects the frontier-independence policy

- Deterministic-first: three machine perspectives settle most changes with no model at all.
- Minimal weak-LLM: only the REVIEW residual is judged, and even then the reconcile step is mechanical.
- Robust to a wrong weak-model answer: the critique can overturn it, and the deterministic prior is the
  anchor when the model is unsure — so a single bad generation does not flip the verdict.

Modules: `agent/twin_control_plane/verification_panel.py`, `agent/twin_control_plane/critique_judge.py`.
Tests (deterministic, with negative controls): `tests/test_verification_panel.py`,
`tests/test_critique_judge.py`, `tests/test_baseline_verify.py`.
