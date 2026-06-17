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


def _classify_symbols(failure_reason: str) -> tuple[set[str], set[str]]:
    """``(code_symbols, key_symbols)``. CODE symbols (NameError/AttributeError/import names) are
    identifiers a real fix uses as code; KEY symbols (KeyError keys, missing field names) legitimately
    appear as string literals (``d['plan_pool']``). They are matched differently so that stripping
    strings to defeat gaming does not also reject a genuine KeyError fix."""
    r = str(failure_reason or "")
    code: set[str] = set()
    keys: set[str] = set()
    for rx in (_NAMEERR_RE, _ATTRERR_RE, _MODULE_RE, _IMPORT_RE):
        code.update(m.group(1) for m in rx.finditer(r))
    for m in _KEYERR_RE.finditer(r):
        keys.add(m.group(1))
    for m in _UNRESOLVED_RE.finditer(r):
        keys.update(p for p in m.group(1).split(",") if p)
    code |= {s.split(".")[-1] for s in code}        # leaf, so `import threading` matches `threading`
    return ({s for s in code if s and len(s) > 1}, {s for s in keys if s})


def cause_symbols(failure_reason: str) -> set[str]:
    """All symbols a failure names — the thing a real fix must touch. Empty for a bare value mismatch."""
    code, keys = _classify_symbols(failure_reason)
    return code | keys


@dataclass
class CausalVerdict:
    causal: bool
    reason: str
    cause_symbols: set = field(default_factory=set)
    matched: set = field(default_factory=set)
    changed_symbols: set = field(default_factory=set)


_STRING_LIT_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_COMMENT_RE = re.compile(r"#.*$", re.M)


def _diff_text(old_src: str, new_src: str) -> str:
    """The added/removed lines between two versions, with STRING LITERALS and COMMENTS stripped — so a
    patch that merely *mentions* the failure symbol inside a string/comment (the gaming the weak LLM tried:
    ``if value == "threading"``) does not count as addressing it. Only the symbol as real CODE matters."""
    out = []
    for line in difflib.unified_diff(str(old_src or "").splitlines(), str(new_src or "").splitlines(),
                                     lineterm="", n=0):
        if line[:1] in "+-" and not line.startswith(("+++", "---")):
            out.append(line[1:])
    text = "\n".join(out)
    text = _STRING_LIT_RE.sub("''", text)        # blank out string contents
    text = _COMMENT_RE.sub("", text)             # and comments
    return text


def _raw_diff_text(old_src: str, new_src: str) -> str:
    """Added/removed lines WITHOUT stripping strings — for KeyError-style symbols that are string keys."""
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
    code_syms, key_syms = _classify_symbols(failure_reason)
    syms = code_syms | key_syms
    if not syms:
        return CausalVerdict(True, "no named symbol in the failure; causal gate abstains")
    code_diff = _diff_text(old_src, new_src)                          # strings/comments stripped
    raw_diff = _raw_diff_text(old_src, new_src)                       # keys legitimately are strings
    matched = {s for s in code_syms if re.search(rf"\b{re.escape(s)}\b", code_diff)}
    matched |= {s for s in key_syms if re.search(rf"\b{re.escape(s)}\b", raw_diff)}
    if matched:
        return CausalVerdict(True, "patch references the failure's symbol(s) as code", syms, matched)
    return CausalVerdict(False, "patch does not reference the failure's symbol(s) as code — likely spurious",
                         syms)
