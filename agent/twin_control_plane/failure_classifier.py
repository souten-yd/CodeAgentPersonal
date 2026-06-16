"""Classify pytest failures so the real work is separable from the noise.

A full-suite run on a dev box produces hundreds of failures, most of which are NOT code regressions —
missing optional files/services, Windows encoding, an unbuilt browser. Triaging them by hand is what we
want to avoid. This buckets each failure deterministically from its reported reason:

- ENVIRONMENT  — missing file/service/dependency, encoding, browser: fix the environment, not the code.
- TEST_DEBT    — a stale expectation / xfail / deprecated assertion: update or retire the TEST.
- GENUINELY_BROKEN — a real logic failure (the residual): this is the actionable set.
- COLLECTION_ERROR — the test file could not even be imported (usually an environment cause).

The point is the big deterministic cut: remove ENVIRONMENT + COLLECTION noise so the residual
GENUINELY_BROKEN set — what actually needs fixing — is small and trustworthy. Pure string analysis.
"""
from __future__ import annotations

import re

ENVIRONMENT = "environment"
SNAPSHOT_DRIFT = "snapshot_drift"
TEST_DEBT = "test_debt"
GENUINELY_BROKEN = "genuinely_broken"
COLLECTION_ERROR = "collection_error"

# Reason substrings (lowercased) that mark an environment cause, not a code bug. The CRLF and
# platform (runpod/cuda/cpu) markers were added after a frontier double-check found them mis-bucketed
# as "genuinely broken" — exactly the kind of noise this is meant to remove.
_ENV_MARKERS = (
    "filenotfounderror", "no such file", "web\\atlas-next", "web/atlas-next",
    "unicodedecodeerror", "cp932", "codec can't",
    "connectionerror", "connection refused", "connectionrefused", "max retries",
    "timeout", "timed out",
    "no module named", "modulenotfounderror",
    "playwright", "chromium", "browser", "executable doesn't exist",
    "address already in use", "winerror", "permissionerror",
    "\\r\\n", "line ending", "carriage return",            # CRLF vs LF on Windows
    "runpod", "'cuda'", "'cpu'", "nvidia", "gpu detect",   # platform-conditional
)
# A test that asserts on a rendered UI / golden snapshot whose source legitimately changed = the stored
# expectation drifted; update the TEST, not the code.
_SNAPSHOT_MARKERS = (
    "<!doctype html", "<html", "data-atlas", 'id="atlas', "doctype html",
    "ui.html", "index.html", "snapshot", "golden",
)
# Markers that the TEST (not the code) is the thing to update.
_DEBT_MARKERS = (
    "deprecat", "xfail", "will be removed", "is deprecated", "no longer", "renamed",
)


def classify_failure_reason(reason: str) -> str:
    """Bucket a single failure from its reason text (the part after ``-`` on a pytest FAILED line, or a
    traceback excerpt)."""
    r = str(reason or "").lower()
    if not r.strip():
        return GENUINELY_BROKEN
    if any(m in r for m in _ENV_MARKERS):
        return ENVIRONMENT
    if any(m in r for m in _SNAPSHOT_MARKERS):
        return SNAPSHOT_DRIFT
    if any(m in r for m in _DEBT_MARKERS):
        return TEST_DEBT
    return GENUINELY_BROKEN


def root_cause_signature(reason: str) -> str:
    """Normalize a failure reason to a root-cause signature (literals/numbers/addresses masked) so the
    many failures that share ONE cause collapse to one signature. The residual GENUINELY_BROKEN set is
    almost always far fewer distinct bugs than failures — e.g. one missing dict key fails dozens of
    tests."""
    r = re.sub(r"'[^']*'", "X", str(reason or ""))
    r = re.sub(r"\d+", "N", r)
    r = re.sub(r"0x[0-9a-fA-F]+", "H", r)
    return r[:80].strip()


def cluster_root_causes(failures: list) -> list[tuple[str, int]]:
    """``[(signature, count)]`` most-common first, for a list of ``(test_id, reason)`` — the distinct
    root causes to actually fix, with how many tests each clears."""
    from collections import Counter
    c = Counter(root_cause_signature(reason) for _test, reason in failures)
    return c.most_common()


_FAILED_LINE = re.compile(r"^FAILED\s+(\S+?)\s+-\s+(.*)$")
_FAILED_NOREASON = re.compile(r"^FAILED\s+(\S+?)\s*$")
_COLLECT_ERR = re.compile(r"ERROR collecting\s+(\S+)")


def classify_pytest_output(text: str) -> dict:
    """Parse a pytest run's text (short-summary style) and bucket every FAILED/ERROR.

    Returns ``{category: [(test_id, reason), ...], "counts": {category: n}}``. Collection errors are
    their own bucket; FAILED lines are classified by reason."""
    buckets: dict[str, list] = {ENVIRONMENT: [], SNAPSHOT_DRIFT: [], TEST_DEBT: [], GENUINELY_BROKEN: [], COLLECTION_ERROR: []}
    seen_failed: set[str] = set()
    seen_collect: set[str] = set()
    for raw in text.splitlines():
        line = raw.strip()
        m = _FAILED_LINE.match(line)
        if m:
            test_id, reason = m.group(1), m.group(2)
            if test_id not in seen_failed:
                seen_failed.add(test_id)
                buckets[classify_failure_reason(reason)].append((test_id, reason[:160]))
            continue
        m2 = _FAILED_NOREASON.match(line)
        if m2 and "::" in m2.group(1):
            if m2.group(1) not in seen_failed:
                seen_failed.add(m2.group(1))
                buckets[GENUINELY_BROKEN].append((m2.group(1), ""))
            continue
        mc = _COLLECT_ERR.search(line)
        if mc and mc.group(1) not in seen_collect:
            seen_collect.add(mc.group(1))
            buckets[COLLECTION_ERROR].append((mc.group(1), "collection error (import-time)"))
    counts = {k: len(v) for k, v in buckets.items()}
    counts["total"] = sum(counts.values())
    return {**buckets, "counts": counts}
