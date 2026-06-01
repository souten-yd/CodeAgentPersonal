from __future__ import annotations

# Pre-approval plan-depth gate. Rejects "おざなり" (shallow) plans BEFORE they are approved /
# applied, so the autopilot does not run on a plan with no implementation items, items without
# target files, or one-line step descriptions. Quality findings here are blocking only when the
# Features set quality_gate_enforcement="block"; otherwise they are surfaced as warnings.

_IMPLEMENTATION_ITEM_TYPES = {"implementation", "documentation"}
MIN_DESCRIPTION_CHARS = 20


def _item_description(item) -> str:
    md = getattr(item, "metadata", {}) or {}
    parts = [
        str(getattr(item, "description", "") or ""),
        str(getattr(item, "goal", "") or ""),
        str(md.get("proposed_fix") or ""),
    ]
    return " ".join(p for p in parts if p).strip()


def evaluate_plan_depth(pool, *, min_description_chars: int = MIN_DESCRIPTION_CHARS) -> dict:
    """Inspect the built plan pool for substance.

    Returns {ok, reasons, warnings, detail} where ``reasons`` are the depth deficiencies. The
    caller decides whether to block (quality_gate_enforcement="block") or only warn.
    """
    reasons: list[str] = []
    detail: list[str] = []
    items = list(getattr(pool, "items", []) or [])
    impl_items = [it for it in items if str(getattr(it, "item_type", "")).lower() in _IMPLEMENTATION_ITEM_TYPES]

    if not impl_items:
        reasons.append("no_implementation_items")
        detail.append("plan has no implementation/documentation items")
        return {"ok": False, "reasons": reasons, "warnings": list(reasons), "detail": detail}

    for it in impl_items:
        item_id = str(getattr(it, "item_id", "") or "")
        if not list(getattr(it, "target_files", []) or []):
            reasons.append(f"item_missing_target_files:{item_id}")
            detail.append(f"item {item_id} has no target_files")
        if len(_item_description(it)) < min_description_chars:
            reasons.append(f"item_description_too_shallow:{item_id}")
            detail.append(f"item {item_id} description is shorter than {min_description_chars} chars")

    ok = not reasons
    return {"ok": ok, "reasons": reasons, "warnings": list(reasons), "detail": detail}
