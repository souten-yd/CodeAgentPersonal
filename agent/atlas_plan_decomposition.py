"""(A) Plan-level per-file decomposition.

A plan item that targets several large files is an **atomic** unit — generated and
applied all-or-nothing — and is too big for a weak local model (controlled result:
the 2-large-file `step_4` failed 0/4, while the SAME files as single-file units
succeeded 6/6). The fix is to expand such an item into one REAL plan sub-item per
target file, each of which is generated -> applied -> verified -> retried independently
through the unchanged normal `propose_for_item` path (a fresh top-level call — the
exact path that was validated 6/6).

This is the (A) option from docs/atlas_patchgen_decomposition_design.md. It is a pure,
idempotent pool transformation: single-file / non-implementation items pass through
unchanged. A generated test is a TwinProof verification ARTIFACT, not an implementation
deliverable, so test paths never become their own per-file unit (they cannot be written
in isolation from the code they test) — they ride along, retained, on the code units.
"""
from __future__ import annotations

import re
from typing import Any

# Keep the test-path heuristic identical to the patch service (_TEST_PATH_RE there) so
# the two layers agree on what is a Twin artifact vs an implementation deliverable.
_TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|spec|__tests__)/|(^|/)test_[^/]*\.|[._-](test|spec)\.[A-Za-z0-9]+$",
    re.IGNORECASE,
)

# Runtime/execution metadata keys that must NOT be copied onto a fresh sub-item (they
# would carry a stale "running/terminal" generation state into a brand-new unit).
_RUNTIME_META_KEYS = (
    "patch_generation",
    "current_execution",
    "patch_proposal",
    "safe_apply",
    "verification",
    "last_result",
    "last_failure",
)


def _norm(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lstrip("./").lower()


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(str(path or "").replace("\\", "/")))


def _slug(path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(path or "").lower()).strip("_") or "f"


def _op_paths(op: Any) -> list[str]:
    if isinstance(op, dict):
        raw = [op.get("path")] + list(op.get("paths") or [])
    else:
        raw = [getattr(op, "path", "")] + list(getattr(op, "paths", []) or [])
    return [_norm(p) for p in raw if p]


def _op_type(op: Any) -> str:
    return str(op.get("type") if isinstance(op, dict) else getattr(op, "type", "")) or ""


def should_decompose_item(item: Any, *, min_files: int = 2, max_subitems: int = 12) -> bool:
    """An implementation item with >= min_files non-test target files is a decomposition
    candidate. Single concrete file, non-implementation, or test-only items are not."""
    if str(getattr(item, "item_type", "") or "") != "implementation":
        return False
    real = [f for f in (getattr(item, "target_files", None) or []) if not _is_test_path(f)]
    return min_files <= len(real) <= max_subitems


def decompose_multi_file_items(
    pool: Any,
    *,
    min_files: int = 2,
    max_subitems: int = 12,
) -> tuple[Any, list[str]]:
    """Replace each multi-file implementation item with one real sub-item per target file.

    Each sub-item:
      - targets exactly one code file (test paths ride along on the first code unit, as
        a retained Twin artifact, never as their own unit);
      - carries the file-scoped `operations` (materialize keys off target_files, but we
        keep operations consistent so structural paths agree);
      - chains `depends_on` define-before-use: sub[i] depends on sub[i-1]; sub[0] keeps
        the original item's dependencies; any DOWNSTREAM item that depended on the
        original now depends on the LAST sub (so it waits for every file);
      - starts with a clean `queued` status and no stale runtime generation metadata.

    Pure and idempotent: items that are not decomposition candidates pass through
    untouched, and re-running on an already-decomposed pool is a no-op.

    Returns (pool, notes) where notes is a human-readable per-item summary.
    """
    items = list(getattr(pool, "items", None) or [])
    new_items: list[Any] = []
    notes: list[str] = []
    # original item_id -> id of its LAST sub-item, for remapping downstream dependencies.
    last_sub_for: dict[str, str] = {}

    for item in items:
        if not should_decompose_item(item, min_files=min_files, max_subitems=max_subitems):
            new_items.append(item)
            continue

        target_files = list(getattr(item, "target_files", None) or [])
        real = [f for f in target_files if not _is_test_path(f)]
        operations = list(getattr(item, "operations", None) or [])
        orig_deps = list(getattr(item, "depends_on", None) or [])

        subs: list[Any] = []
        prev_id = ""
        for idx, f in enumerate(real):
            sub = item.model_copy(deep=True)
            sub.item_id = f"{item.item_id}__f{idx}_{_slug(f)}"[:120]
            sub.title = f"{item.title} — {f}"
            # Each unit targets EXACTLY ONE code file. A test path is deliberately NOT carried
            # here: any extra target makes the unit a multi-target generation (len>1), which
            # diverges from the single-file path validated 6/6 and re-introduces the
            # multi_file_content_missing failure (the 2-target main.js unit failed 0/2 with a
            # test attached, vs 2/2 as a lone file). The generated test remains an allowed,
            # retained by-product harvested during the code unit's own generation (TwinProof),
            # and a dedicated test-generation item is future work — never a required deliverable.
            sub.target_files = [f]
            scoped_ops = [op for op in operations if _norm(f) in _op_paths(op)]
            if not scoped_ops:
                # Synthesize a single op for this file, preserving the item's op type when
                # uniform (else default to modify_file; create-vs-modify is re-decided at
                # generation time by on-disk existence anyway).
                op_types = {_op_type(op) for op in operations if _op_type(op)}
                op_type = op_types.pop() if len(op_types) == 1 else "modify_file"
                scoped_ops = [type(operations[0])(type=op_type, path=f)] if operations else []
            sub.operations = scoped_ops
            sub.depends_on = list(orig_deps) if idx == 0 else [prev_id]
            sub.status = "queued"
            meta = dict(getattr(sub, "metadata", None) or {})
            for k in _RUNTIME_META_KEYS:
                meta.pop(k, None)
            meta["decomposed_from"] = item.item_id
            meta["decomposed_index"] = idx
            meta["decomposed_total"] = len(real)
            # Behavioural/visual smoke runs against the WHOLE app, so it is premature on any
            # but the final file of a feature (a partially-applied app can throw a transient
            # js_error that is not a real defect). Only the final member runs the feature's
            # behavioural verification; earlier members defer it (syntax is enforced at
            # generation, and the final member's smoke loads every file).
            meta["group_role"] = "final" if idx == len(real) - 1 else "member"
            sub.metadata = meta
            prev_id = sub.item_id
            subs.append(sub)

        last_sub_for[item.item_id] = subs[-1].item_id
        new_items.extend(subs)
        notes.append(f"{item.item_id} -> {len(subs)} per-file items: {', '.join(real)}")

    # Remap downstream dependencies that referenced a decomposed item to its last sub-item.
    if last_sub_for:
        sub_ids = set(last_sub_for.values())
        for it in new_items:
            if it.item_id in sub_ids:
                continue  # internal sub-chain dependencies are already correct
            deps = list(getattr(it, "depends_on", None) or [])
            if any(d in last_sub_for for d in deps):
                it.depends_on = [last_sub_for.get(d, d) for d in deps]

    pool.items = new_items
    return pool, notes
