"""Safe-edit briefing: turn a Twin ImpactResult into model-facing "how to change this without
breaking callers" guidance.

When the autonomous codegen path is about to edit an existing symbol/file in a large repository
(the self-improvement case), the Twin's impact assessment already knows who depends on it — callers,
side effects, and the tests that must stay green. This module renders that into a concise advisory
the generator receives, so the model preserves the public interface its dependents rely on instead
of editing blindly. It is pure (duck-typed over the ImpactResult shape), advisory only, and degrades
to an empty string when there is no impact evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Cap how many dependents/tests we list so the briefing stays a bounded prompt section even on a
# symbol with a huge fan-in (a frequently-called helper in a large codebase).
_MAX_PER_SECTION = 12

# Twin impact traversal can surface INTERNAL graph nodes — a callee's local variables / nested defs
# (e.g. ``var://...#caller/mode``, ``def://...#caller/L161:x``) — alongside the real symbol that
# depends on the target. Those are noise in a "who depends on this" briefing (and an artifact observed
# while evaluating the Twin against a frontier reading of the repo), so we keep only real source-symbol
# refs and drop these internal-node schemes.
_INTERNAL_REF_PREFIXES = ("var://", "def://")


def _is_dependent_ref(ref: str) -> bool:
    """A real source symbol/file that depends on the target — not an internal variable / nested-def
    node of some caller."""
    return bool(ref) and not ref.startswith(_INTERNAL_REF_PREFIXES)


@dataclass
class SafeEditBriefing:
    target_refs: list[str] = field(default_factory=list)
    callers: list[dict] = field(default_factory=list)        # dependents that must keep working
    side_effects: list[dict] = field(default_factory=list)
    tests: list[dict] = field(default_factory=list)
    uncertain: list[dict] = field(default_factory=list)      # low-confidence / inferred links

    @property
    def is_empty(self) -> bool:
        return not (self.callers or self.side_effects or self.tests)

    def dependent_files(self) -> list[str]:
        """Repo-relative file paths of the dependents (callers + side effects), so generation can load
        and rank the symbols of the files that actually depend on the change."""
        out: list[str] = []
        seen: set[str] = set()
        for d in [*self.callers, *self.side_effects]:
            ref = str(d.get("ref", ""))
            if not ref.startswith("py://") or "#" not in ref:
                continue
            path = ref[len("py://"):].split("#", 1)[0]
            if path and path not in seen:
                seen.add(path)
                out.append(path)
        return out

    def to_dict(self) -> dict:
        return {
            "target_refs": list(self.target_refs),
            "caller_count": len(self.callers),
            "side_effect_count": len(self.side_effects),
            "test_count": len(self.tests),
            "uncertain_count": len(self.uncertain),
            "dependent_files": self.dependent_files(),
        }


def _item(obj) -> dict:
    return {
        "ref": str(getattr(obj, "canonical_ref", "") or ""),
        "type": str(getattr(obj, "item_type", "") or ""),
        "confidence": float(getattr(obj, "confidence", 0.0) or 0.0),
        "reason": str(getattr(obj, "reason", "") or ""),
    }


def build_safe_edit_briefing(impact, *, target_refs=(), uncertain_below: float = 0.5) -> SafeEditBriefing:
    """Project an ImpactResult into a SafeEditBriefing. ``uncertain_below`` routes low-confidence
    dependents into the ``uncertain`` bucket (reported with honest doubt rather than as fact)."""
    if impact is None:
        return SafeEditBriefing(target_refs=[str(r) for r in target_refs])

    callers: list[dict] = []
    uncertain: list[dict] = []
    seen: set[str] = set()
    for obj in [*(getattr(impact, "direct_impacts", []) or []), *(getattr(impact, "transitive_impacts", []) or [])]:
        d = _item(obj)
        if not _is_dependent_ref(d["ref"]) or d["ref"] in seen:
            continue
        seen.add(d["ref"])
        (uncertain if d["confidence"] < uncertain_below else callers).append(d)

    side_effects = [_item(o) for o in (getattr(impact, "side_effects", []) or []) if _is_dependent_ref(str(getattr(o, "canonical_ref", "")))]
    tests = [_item(o) for o in (getattr(impact, "recommended_tests", []) or []) if _is_dependent_ref(str(getattr(o, "canonical_ref", "")))]

    # Most-confident dependents first; bound each section.
    callers.sort(key=lambda d: d["confidence"], reverse=True)
    return SafeEditBriefing(
        target_refs=[str(r) for r in target_refs],
        callers=callers[:_MAX_PER_SECTION],
        side_effects=side_effects[:_MAX_PER_SECTION],
        tests=tests[:_MAX_PER_SECTION],
        uncertain=uncertain[:_MAX_PER_SECTION],
    )


SAFE_EDIT_HEADER = (
    "[Twin Safe-Edit Briefing — these existing parts depend on what you are changing. Change the "
    "behavior as required, but keep the target's PUBLIC INTERFACE (name, signature, return shape) "
    "stable for the dependents below; if the interface must change, update every listed call site in "
    "the SAME change and keep the listed tests green.]"
)


def render_safe_edit_briefing(briefing: SafeEditBriefing) -> str:
    """Render the briefing as a bounded advisory section. Returns "" when there is nothing to say
    (no dependents/tests), so it never adds noise on a brand-new or leaf symbol."""
    if briefing is None or briefing.is_empty:
        return ""

    def _lines(items: list[dict]) -> list[str]:
        out = []
        for d in items:
            tail = f" — {d['reason']}" if d.get("reason") else ""
            out.append(f"  - {d['ref']} ({d['type']}, confidence {d['confidence']:.2f}){tail}")
        return out

    parts = [SAFE_EDIT_HEADER]
    if briefing.callers:
        parts.append("Callers / dependents that must keep working:")
        parts.extend(_lines(briefing.callers))
    if briefing.side_effects:
        parts.append("Side effects to preserve:")
        parts.extend(_lines(briefing.side_effects))
    if briefing.tests:
        parts.append("Tests that must stay green:")
        parts.extend(_lines(briefing.tests))
    if briefing.uncertain:
        parts.append("Low-confidence / inferred links (verify before relying on them):")
        parts.extend(_lines(briefing.uncertain))
    return "\n".join(parts)
