# Automated cause discovery — the detective work, frontier-free

2026-06-17. Diagnosing the safe-apply drift by hand was a frontier-model loop: apply a fix, read the new
failure, grep the product code for the signal, read the gate, find the missing field, repeat
(`plan_pool` → `patch_content_missing` → `update_target_missing` → …). `cause_discovery.py` makes that
loop a Twin + weak-LLM capability.

## The insight that removes the frontier

A runtime failure signal — a warning token (`patch_content_missing`), an exception key, an
asserted-but-missing value — is a **literal string in the source that emits it**. So locating its origin
is **deterministic** (grep / the Twin's code index), not a model task. The only step needing judgment is
reading the small located snippet to say what would satisfy the gate — a bounded, local call for the weak
LLM, with a deterministic fallback ("emitted at file:line — inspect the check").

## Pieces

- `extract_failure_signals(text)` — deterministic: warning identifiers (`warnings: [...]`,
  `'X' in warnings`), the exception class/key, the actual value of an `==` mismatch (the actual is what
  the code produced — the thing to trace).
- `locate_in_source(token)` — deterministic: where the literal appears in product code (tests excluded),
  with context.
- `explain_requirement(signal, origins, llm_json_fn)` — weak LLM reads the located check and states what
  satisfies it; no-model fallback points at the origin.
- `diagnose(failure_text)` — composes the three into a ranked list of `Diagnosis` (located first).

## Demonstrated on the real safe-apply signals

Deterministic locate (no model) correctly traced the gates I had found by hand:
`patch_content_missing` → `agent/atlas_patch_proposal_service.py` / `atlas_plan_item_patchability.py`;
`update_target_missing` → `agent/atlas_file_safe_apply_executor.py`. With the local weak LLM
(Mistral-Small @ :8080) reading the located check: *"The patch content must be generated and available
(field: patch_content_available)"* — the same conclusion, no frontier.

## Where it fits

This is the missing diagnostic step of the autonomous repair loop: when a templated fix peels one failure
and `verify` surfaces the next, `cause_discovery.diagnose` names the next root cause and where it lives —
so the loop (and a future synthesize step) can target it without a frontier model. Files:
`agent/twin_control_plane/cause_discovery.py` (+ `tests/test_cause_discovery.py`, 7 tests).
