# Weak LLM Large-File Edit Hardening Plan

## Purpose

Weak local models can fail when asked to modify a large existing file because they try to re-emit the whole file as `proposed_content`. This can lead to long generations, malformed or truncated output, `llm_no_patch_content_generated`, or unsafe replacement of a large file with a partial fragment.

The goal of this plan is not to make weak models rewrite large files. The goal is to force weak models into a bounded, deterministic edit pipeline:

```text
large existing file
  -> weak/standard tier
  -> edit-only policy must fire
  -> model returns only small edits or SEARCH/REPLACE blocks
  -> Atlas applies edits deterministically
  -> slice fragments and raw full-file rewrites cannot be applied as full content
```

## Current status

Already implemented before this plan:

- `WeakLargeFileEditPolicy`
- edits-only directive and output cap for weak/standard large existing-file modify
- Aider-style `SEARCH/REPLACE` block parsing
- deterministic repair recipe for the WebGL canvas / 2D context conflict
- focused recovery old/new and line-range output caps
- Twin-style input slicing
- per-file split generation

The remaining problem is in the wiring between these mechanisms. Some paths can still bypass the policy or accidentally treat edit fragments as full file content.

---

# P0 fixes

## P0-1: Make WeakLargeFileEditPolicy fire inside per-file split

### Problem

`_weak_large_file_edit_policy(input_payload)` primarily reads target content from `input_payload["current_target_contents"]`.

However, `_single_file_input_payload()` intentionally clears the heavy map during per-file split:

```python
sub["current_target_contents"] = {}
item["current_file_content"] = content_for_model
item["target_file_exists"] = bool(entry.get("exists"))
```

Therefore the child generation payload can lose the original target size signal. The policy may not fire, so `max_output_tokens=1800` may not be passed into the main LLM call.

### Required implementation

Update `_weak_large_file_edit_policy()` so it also considers:

- `item.current_file_content`
- `item.current_file_original_chars`
- `item.current_file_original_lines`
- `item.current_file_content_sliced`
- `item.target_file_exists`

Recommended behavior:

```python
content = str((entry or {}).get("content") or "")
if not content:
    content = str(item.get("current_file_content") or "")

file_chars = int(item.get("current_file_original_chars") or len(content))
file_lines = int(item.get("current_file_original_lines") or ((content.count("\n") + 1) if content else 0))
file_exists = bool(content.strip()) or bool(item.get("target_file_exists"))

if item.get("current_file_content_sliced") and file_exists:
    # Treat sliced existing files as large/sensitive even if the slice is short.
    force edit-only.
```

Also update `_single_file_input_payload()` to preserve original size before slicing:

```python
item["current_file_original_chars"] = len(content)
item["current_file_original_lines"] = content.count("\n") + 1 if content else 0
```

### Acceptance criteria

- per-file split child generation still triggers edit-only policy for a large existing file.
- sliced existing content never becomes small-file exempt solely because the slice is short.
- policy verdict records a clear reason such as `large_existing_file` or `sliced_existing_file`.

---

## P0-2: Preserve edits through per-file split merge

### Problem

A child proposal may correctly return `metadata["edits"]`. But `_proposal_content_by_path()` represents edits by joining only the `new_string` values. `_generate_per_file_split()` can then synthesize a file change using that value as content:

```python
combined_changes.append({"path": target, "content": content, "change_type": "modify"})
```

This can convert a valid surgical edit into an unsafe full-file replacement containing only the replacement fragment.

### Required implementation

In `_generate_per_file_split()`, before using `_proposal_content_by_path(part)`, explicitly preserve edits:

```python
edits = pmeta.get("edits") if isinstance(pmeta.get("edits"), list) else []
if edits:
    combined_changes.append({
        "path": target,
        "action_type": "update",
        "content_mode": "edits",
        "edits": edits,
    })
    per_file_ok[target] = True
    continue
```

Apply the same protection to `_generate_per_file_items()` if it has the same merge behavior.

### Acceptance criteria

- A child proposal with `metadata.edits` produces a merged `file_changes` entry with `content_mode="edits"`.
- It must not produce `content: <joined new_string>` as if it were a full file.
- Safe apply receives the edits as edits.

---

## P0-3: Forbid focused full-content fallback for existing edit-only targets

### Problem

`_focused_edit_extraction()` currently tries:

1. old/new surgical edit
2. line-range op
3. full `proposed_content`

The first two recovery calls are capped, but the full-content fallback can still be reached for existing files. This reopens the original failure mode: weak model attempts to output the entire large file.

### Required implementation

When the target exists and `WeakLargeFileEditPolicy` says `edit_only=True`, do not run the full `proposed_content` fallback.

Suggested check:

```python
edit_policy = self._weak_large_file_edit_policy(payload)
if exists and edit_policy.get("edit_only"):
    proposal.warnings.append("focused_full_content_forbidden_under_edit_only")
    return False
```

New/empty file generation may still use full `proposed_content` because CREATE requires full content.

### Acceptance criteria

- Existing large weak/standard target cannot reach the full-content focused recovery call.
- New file recovery still works.
- Failure is bounded and clearly labeled.

---

## P0-4: Never turn sliced content into full proposed_content

### Problem

When Twin input slicing is active, `item.current_file_content` is a slice, not the full file. If line-range recovery applies to that slice and stores the result as `proposal.metadata["proposed_content"]`, the slice can later be treated as a complete replacement file.

### Required implementation

If `item.current_file_content_sliced` is true:

- allow old/new edits only,
- skip line-range -> `proposed_content`,
- skip full `proposed_content` fallback for existing files.

Recommended warning/reason:

```text
line_range_forbidden_on_sliced_content
```

### Acceptance criteria

- No sliced content can be saved as full `proposed_content`.
- Sliced existing files can still succeed via exact old/new edits or SEARCH/REPLACE edits.
- If no safe edit can be extracted, failure remains bounded and explanatory.

---

# P1 fixes

## P1-1: Reject raw proposed_content under edit-only policy

### Problem

The patch proposal schema still allows `proposed_content` even in edit-only mode. `_build_proposal_from_output()` can convert a whole-file output into edits via `_full_content_to_edits()`, but if conversion fails, the raw full content can survive with only a warning.

### Required implementation

When `edit_policy.edit_only=True`, only these are valid:

- structured `edits`,
- edits harvested from `SEARCH/REPLACE`,
- full content converted into small surgical edits by `_full_content_to_edits()`.

If raw `proposed_content` remains after conversion attempts, reject it with a reason such as:

```text
full_content_forbidden_under_edit_only
```

This can be implemented in validation or during proposal building, but the result must trigger retry rather than applying full content.

### Acceptance criteria

- edit-only mode cannot pass raw `proposed_content` unless it was converted into edits.
- retry note instructs the model to return edits only.
- logs identify this as an edit-only policy violation.

---

## P1-2: Extend deterministic repair recipes for non-dead WebGL/2D conflicts

The existing recipe safely removes dead 2D context acquisition from a WebGL canvas. If the 2D context is actually used, the recipe currently returns options instead of guessing.

Future improvement:

- Ask weak LLM only to choose A/B/C:
  - A: separate overlay canvas
  - B: DOM overlay
  - C: remove 2D usage
- Then apply the selected transformation deterministically where possible.

This is not required for the P0 hardening but should remain a follow-up.

---

# Required tests

Add or update tests for the following cases.

## Test 1: per-file split payload triggers edit-only policy

Input:

- `current_target_contents = {}`
- `item.current_file_content` contains large existing content, around 22KB
- `target_file_exists=True`
- `size_tier="weak"`

Expected:

```python
policy["edit_only"] is True
policy["max_output_tokens"] == 1800
```

## Test 2: sliced content still triggers edit-only policy

Input:

- `current_file_content` is a short slice
- `current_file_content_sliced=True`
- `target_file_exists=True`
- original size metadata, if implemented, indicates a large file

Expected:

```python
policy["edit_only"] is True
```

## Test 3: per-file split preserves edits

Fake child proposal:

```python
metadata = {
    "edits": [{"old_string": "a", "new_string": "b"}]
}
```

Expected merged file change:

```python
{
    "path": target,
    "content_mode": "edits",
    "edits": [{"old_string": "a", "new_string": "b"}],
}
```

It must not become:

```python
{"content": "b"}
```

## Test 4: sliced content blocks line-range proposed_content

Input:

- `current_file_content_sliced=True`
- old/new extraction fails
- line-range would otherwise succeed

Expected:

- no `proposal.metadata["proposed_content"]` from the slice,
- warning or reason `line_range_forbidden_on_sliced_content`.

## Test 5: existing edit-only focused recovery does not call full-content fallback

Input:

- target exists
- edit-only policy true
- old/new fails
- line-range fails

Expected:

- full `proposed_content` LLM call is not made,
- warning or reason `focused_full_content_forbidden_under_edit_only`.

---

# Weak LLM live verification using port 8080

The user will prepare a weak LLM server on port 8080.

Assume an OpenAI-compatible endpoint:

```text
http://127.0.0.1:8080/v1
```

Use the existing KasaneCore/Atlas LLM configuration mechanism. Do not invent new config if an existing env/config path already exists. Inspect current adapter/startup code to determine the correct variables.

Suggested Atlas-related flags:

```bash
export ATLAS_PATCHGEN_PER_FILE_SPLIT=1
export ATLAS_PATCHGEN_INPUT_SLICE=1
export ATLAS_PATCHGEN_INPUT_SLICE_MAX_CHARS=8000
```

## Live scenario

Create or use a reproduction project with:

- at least one existing JavaScript file over 20KB,
- `target_file_exists=True`,
- modify task,
- ideally a WebGL canvas / HUD / `getContext` scenario similar to the previous failure.

Run patch generation with the weak model on port 8080.

## Verify and log

Record the following in logs or test output:

- policy verdict: `edit_only`, `max_output_tokens`, `reason`
- whether per-file split was used
- whether input slice was used
- whether the main LLM call received the cap
- output mode:
  - `edits`
  - `search_replace`
  - `converted_edits`
  - `rejected_full_content`
- whether focused recovery was used
- whether full-content fallback was blocked
- final safe-apply result

## Expected live behavior

Success means the weak model is contained. It does not necessarily mean the generated patch is semantically perfect.

Acceptable outcomes:

- valid edits generated and safely applied,
- valid SEARCH/REPLACE generated and safely applied,
- raw full content rejected under edit-only policy,
- bounded failure such as `anchor_missing`, `full_content_forbidden_under_edit_only`, or `line_range_forbidden_on_sliced_content`.

Unacceptable outcomes:

- 5000+ token runaway on an existing large file,
- `llm_no_patch_content_generated` after unbounded full-file rewrite attempt,
- slice fragment saved as full `proposed_content`,
- `new_string` fragment applied as whole file content,
- per-file split bypassing edit-only cap.

---

# Completion criteria

This task is complete when:

1. P0-1 through P0-4 are implemented.
2. Tests for the above edge cases pass.
3. Existing weak large-file, focused extraction, edit format, and repair recipe tests still pass.
4. At least one live weak-LLM run against port 8080 is performed.
5. The live run demonstrates bounded behavior: either successful small-edit application or clear bounded rejection.
6. No path remains where weak/standard tier can freely rewrite a large existing file as raw `proposed_content`.

## Core design principle

Do not try to make the weak model better at rewriting large files.

Instead, remove output freedom:

```text
weak model: choose or describe the smallest edit
Atlas: applies, validates, and gates deterministically
```

---

# Completion evidence

## P0 fixes — completed 2026-06-25

Completed package: P0 weak LLM large-file edit hardening
Status: completed; ready for item PR publication and merge
Changed modules/files: `agent/atlas_patch_proposal_service.py`, `tests/test_atlas_weak_large_file_edit_policy_contract.py`, `tests/test_atlas_focused_patch_extraction.py`, `tests/test_atlas_per_file_split_edits.py`, this plan
Behavior implemented:
- `_weak_large_file_edit_policy()` now reads per-file child payload metadata (`current_file_content`, original char/line counts, sliced flag, target existence) even when `current_target_contents` was intentionally cleared.
- `_single_file_input_payload()` preserves original size metadata before slicing.
- per-file item and split merges preserve child `metadata.edits` as `file_changes[{content_mode: "edits"}]` instead of converting `new_string` fragments into full-file replacement content.
- focused recovery forbids line-range-to-`proposed_content` on sliced existing content and forbids full-content fallback when edit-only policy is active for an existing target.
Focused tests: `python -m pytest -q tests/test_atlas_weak_large_file_edit_policy_contract.py tests/test_atlas_focused_patch_extraction.py tests/test_atlas_per_file_split_edits.py` -> 30 passed
Affected tests: `python -m pytest -q tests/test_atlas_weak_large_file_edit_policy_contract.py tests/test_atlas_focused_patch_extraction.py tests/test_atlas_per_file_split_edits.py tests/test_atlas_edit_format_contract.py tests/test_atlas_repair_recipes_contract.py` -> 45 passed
Syntax checks: `python -m py_compile agent/atlas_patch_proposal_service.py tests/test_atlas_weak_large_file_edit_policy_contract.py tests/test_atlas_focused_patch_extraction.py tests/test_atlas_per_file_split_edits.py` -> passed
Real model evidence: localhost:8080 served `Qwen3.6-35B-A3B-UD-IQ4_XS.gguf`. Live sliced-existing run against a temporary 32,232-byte / 856-line `js/main.js` recorded policy `{edit_only: true, max_output_tokens: 1800, reason: sliced_existing_file}`; the OpenAI-compatible request carried `max_tokens=1800`; the model returned 2 edits, no `proposed_content`; Safe Apply in the temporary workspace returned `applied`; post-apply content no longer contained `getContext('2d')` or `fillText`.
Bounded rejection evidence: a full-content-input live run also stayed capped at `max_tokens=1800` and ended as `semantic_validation_failed:content_missing,semantic_evidence_missing` without `proposed_content`, confirming no full-file token runaway.
Unavailable checks: no production workspace apply; live Safe Apply was limited to a temporary reproduction workspace.
Safety invariants: weak/standard large existing-file generation remains edit-only; sliced content is never promoted to full `proposed_content`; per-file split edits stay surgical; no Proposal / Safe Apply / Verification authority is bypassed.
Remaining gaps: P1-1 raw `proposed_content` rejection under edit-only policy; P1-2 non-dead WebGL/2D deterministic repair option selection.
Next package: P1-1 raw `proposed_content` rejection under edit-only policy
Blocker: none
Proof level: `runtime_bounded_edit_verified`
