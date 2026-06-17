"""Causal verification — a passing test is NOT proof of a correct fix.

The real-suite run (PR #1933) produced a spurious "fix": for ``NameError: name 'threading' is not
defined`` the weak LLM edited an unrelated function (``normalize_action_type``, adding an arbitrary
``apply→update``) and the single test happened to pass. A single-test verify cannot tell a real fix from a
coincidental pass. This gate adds the missing check: **the patch must plausibly address the failure's
cause** — otherwise the pass is rejected as spurious even though the test is green.

Deterministic, frontier-free. The strongest signal is symbol-relatedness: when a failure NAMES a symbol
(``NameError: name 'threading'``, ``AttributeError: … 'foo'``, ``KeyError: 'plan_pool'``,
``No module named 'x'``), a genuine fix's diff almost always references that symbol. A patch whose diff
mentions none of the failure's symbols is spurious. (When the failure names no symbol — a bare value
mismatch — this gate abstains; the related-test bundle is the check there.)
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

_NAMEERR_RE = re.compile(r"name '([^']+)' is not defined")
_ATTRERR_RE = re.compile(r"has no attribute '([^']+)'")
_KEYERR_RE = re.compile(r"KeyError:\s*'([^']+)'")
_MODULE_RE = re.compile(r"No module named '([^']+)'")
_IMPORT_RE = re.compile(r"cannot import name '([^']+)'")
_UNRESOLVED_RE = re.compile(r"(?:missing_required_fields|invariant_violation)[:\s]+([A-Za-z0-9_,]+)")


def cause_symbols(failure_reason: str) -> set[str]:
    """The concrete symbol(s) a failure names — the thing a real fix must touch. Empty when the failure is
    a bare value mismatch (this gate then abstains)."""
    r = str(failure_reason or "")
    syms: set[str] = set()
    for rx in (_NAMEERR_RE, _ATTRERR_RE, _KEYERR_RE, _MODULE_RE, _IMPORT_RE):
        syms.update(m.group(1) for m in rx.finditer(r))
    for m in _UNRESOLVED_RE.finditer(r):
        syms.update(p for p in m.group(1).split(",") if p)
    # a dotted module/name -> also keep the leaf, so `import threading` matches `threading`
    leaves = {s.split(".")[-1] for s in syms}
    return {s for s in (syms | leaves) if s and len(s) > 1}


@dataclass
class CausalVerdict:
    causal: bool
    reason: str
    cause_symbols: set = field(default_factory=set)
    matched: set = field(default_factory=set)
    changed_symbols: set = field(default_factory=set)


def _diff_text(old_src: str, new_src: str) -> str:
    """The added/removed lines between two versions — what the patch actually changed."""
    out = []
    for line in difflib.unified_diff(str(old_src or "").splitlines(), str(new_src or "").splitlines(),
                                     lineterm="", n=0):
        if line[:1] in "+-" and not line.startswith(("+++", "---")):
            out.append(line[1:])
    return "\n".join(out)


def verify_causal(
    old_src: str,
    new_src: str,
    failure_reason: str,
    *,
    target_func: str = "",
    localized_func: str = "",
) -> CausalVerdict:
    """Decide whether a patch (``old_src`` → ``new_src``) plausibly addresses ``failure_reason``.

    Rejects when the failure names symbols but the patch's diff references none of them (the spurious case
    from #1933), or when the edited function is not the localized cause. Abstains (causal=True) when the
    failure names no symbol — there is nothing to key on deterministically."""
    if target_func and localized_func and target_func != localized_func:
        return CausalVerdict(False, "patch target differs from the localized cause",
                             changed_symbols={target_func})
    syms = cause_symbols(failure_reason)
    if not syms:
        return CausalVerdict(True, "no named symbol in the failure; causal gate abstains")
    diff = _diff_text(old_src, new_src)
    matched = {s for s in syms if re.search(rf"\b{re.escape(s)}\b", diff)}
    if matched:
        return CausalVerdict(True, "patch references the failure's symbol(s)", syms, matched)
    return CausalVerdict(False, "patch does not reference the failure's symbol(s) — likely spurious", syms)
