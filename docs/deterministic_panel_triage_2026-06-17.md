# Multi-perspective deterministic classification — frontier-free triage of the full failure set

2026-06-17. Follows `full_suite_routed_triage_run_2026-06-17.md`. Goal: classify the whole ~500-failure
set **without a frontier model in the loop** — several independent *deterministic* priors vote, their
agreement settles a failure, only their disagreement is escalated, and the weak local LLM breaks the
ties. The frontier is used **once, as an auditor**, and its findings are absorbed into the priors so the
running system needs no frontier (the frontier-independence policy).

## Why a single prior was not enough

The single marker classifier has one structural blind spot: a pytest assertion is
`<expected> not found in '<actual>'`, and `<actual>` is often a whole rendered HTML/JS document. An
env-ish token deep in that body (a path, the word "timeout") fired `ENVIRONMENT` on what was really a UI
assertion. The critique judge then *anchored* on that one wrong prior and suppressed the model's correct
dissent — so 0/76 clusters were ever corrected. Increasing the number of deterministic priors fixes both
problems: agreement is a quorum (trustworthy), disagreement is the real uncertainty signal.

## The four priors (each ABSTAINS when it has no signal)

| Prior | Looks at | Example |
|---|---|---|
| `marker` | substring markers (env/snapshot/debt) | `connection refused` → env |
| `exception` | the leading exception **class** | `FileNotFoundError` → env; `KeyError` → broken |
| `structure` | what the assertion is **about** | `<!doctype html>` → snapshot; CRLF-only diff → env |
| `infra` | the test **harness** | xdist `worker crashed`, `collection failure` → env |

Crucial fix: `marker`/`infra` (and `structure`'s env checks) read only the assertion **intent**
(`_intent_head`, everything before `in '…'`), never the rendered-document dump. That removed the
env false-positives at the root — `environment` dropped **272 → 183** on the real set, with the UI
assertions correctly leaving the environment bucket.

## Result on the real 623-failure set

```
python -m agent.twin_control_plane.junit_triage .triage/full_suite.xml --panel --judge
```

| | value |
|---|---:|
| failures | 623 |
| **settled by prior agreement (NO model)** | **529 (85%)** |
| escalated (priors disagree) | 94 → **24 clusters** |
| weak-LLM tie-break calls | **24** |
| clusters the weak LLM moved off the best-guess | **9** |

Final buckets after the weak-LLM tie-break: **environment 186 · genuinely_broken 367 · snapshot_drift 70**.
The biggest correction: 43 UI-content assertions the panel best-guessed `genuinely_broken` were lifted to
`snapshot_drift` by the weak LLM — exactly the cases a single anchored prior got wrong before.

**The weak LLM now earns its keep.** Anchored on the single prior it moved 0/76; freed to *decide* the
panel's 24 disagreement clusters it corrected 9. The model is spent on 24 calls, not 623 (26× fewer), and
no frontier is involved.

## Frontier used once, as auditor (then absorbed)

A frontier (Opus) audit of the **settled 529** — the set no model checks — found them highly accurate:
`environment` (FileNotFound / xdist worker-crash) and `snapshot_drift` (rendered `<!doctype html>`) are
unambiguous; `genuinely_broken` are real (`KeyError: plan_pool`, value mismatches). The one soft spot is
assertions over a Python **source** body settling as `genuinely_broken` on a single `exception` vote —
defensible, noted, not corrected. The earlier env-body false-positive the audit/weak-LLM surfaced was
**absorbed into `_intent_head`**, so the steady-state classifier no longer needs the frontier to catch
it. This is the policy working: deterministic does the bulk, weak LLM does the tail, frontier verifies
once and the gap is folded back.

## Accuracy head-to-head vs the earlier signal ensemble (consolidation)

An earlier ensemble (`failure_signals`) prototyped the same idea. Measured on the same 623:

| | this panel | failure_signals |
|---|---:|---:|
| settled deterministically | **529 / 623 (85%)** | 204 / 623 (33%) |
| escalations (LLM cost) | 94 (24 clusters) | 419 |
| env false-positive on UI assertions (of 72) | **0** | 3 |

`failure_signals` settled fewer and still mislabeled UI assertions as environment, because its marker
signal classified the FULL reason (the rendered-HTML body), the exact blind spot `_intent_head` removes.
So the panel is both more accurate and cheaper. Its one genuinely better idea — a **focus-guided** LLM
adjudication that shows the model only the competing labels — was absorbed here as `judge_with_focus`,
and `failure_signals` is superseded (not committed).

## Files

- `agent/twin_control_plane/deterministic_panel.py` — the four priors + `classify_with_panel` /
  `triage_with_panel` + `judge_with_focus` (focus-guided weak-LLM tie-break)
  (+ `tests/test_deterministic_panel.py`).
- `agent/twin_control_plane/junit_triage.py` — `--panel` entrypoint.
