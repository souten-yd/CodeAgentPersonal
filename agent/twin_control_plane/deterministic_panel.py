"""Multi-perspective DETERMINISTIC classification — several independent priors vote, agreement settles a
failure with no model, disagreement is the precise set worth escalating.

The single marker classifier (`failure_classifier`) has one blind spot per design: a substring marker can
fire inside a huge rendered-HTML body and mislabel a UI assertion as ENVIRONMENT, and there is no second
opinion to catch it. The critique judge then *anchors* on that one (wrong) prior and suppresses the
model's correct dissent. The fix is the same idea the code-change `verification_panel` already uses:
look from SEVERAL independent angles and treat their DISAGREEMENT as the uncertainty signal.

Four complementary priors, each ABSTAINS when it has no signal (so a vote is always real, never a
default):

- ``marker_prior``    — substring markers (the existing engine, but abstaining instead of defaulting).
- ``exception_prior`` — the leading exception CLASS (``FileNotFoundError`` -> env, ``KeyError`` ->
  broken, ``DeprecationWarning`` -> debt). Type-level, blind to the assertion's contents.
- ``structure_prior`` — what the assertion is ABOUT (rendered ``<!doctype html>`` -> snapshot drift,
  a CRLF-only diff or cpu/cuda swap -> env, a cache-bust version token -> snapshot). Content-level,
  blind to the exception type.
- ``infra_prior``     — the test HARNESS (xdist worker crash, collection failure, INTERNALERROR,
  fixture/setup error) -> environment.

``classify_with_panel`` aggregates: unanimous among the non-abstaining priors -> SETTLED (trust it, no
model); split -> ESCALATE (the genuinely-uncertain residual). This replaces the brittle single anchor
with a quorum, and the escalation set is exactly where a weak LLM / frontier review earns its cost.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

from agent.twin_control_plane.failure_classifier import (
    ENVIRONMENT, GENUINELY_BROKEN, SNAPSHOT_DRIFT, TEST_DEBT,
    _DEBT_MARKERS, _ENV_MARKERS, _SNAPSHOT_MARKERS, root_cause_signature,
)

# A pytest assertion is ``<expected> (not) found in '<actual>'`` — the ``<actual>`` operand is often a
# whole rendered HTML/JS document. Substring markers must NOT scan that dump: an env-ish token deep in
# the rendered body (a path, the word "timeout") otherwise mislabels a UI assertion as ENVIRONMENT. This
# was the single classifier's blind spot AND, before this, all four priors shared it. ``_intent_head``
# keeps only the assertion's INTENT (the exception line + the expected operand), where a real env signal
# (the exception class, a FileNotFoundError path) lives; the document body is dropped for env/infra.
_IN_RE = re.compile(r"\b(?:not\s+)?(?:found\s+|present\s+)?in\s+['\"]", re.I)


def _intent_head(reason: str) -> str:
    m = _IN_RE.search(str(reason or ""))
    return str(reason or "")[: m.start()] if m else str(reason or "")


# --- prior 1: substring markers (abstains when nothing matches, unlike classify_failure_reason) ------


def marker_prior(reason: str) -> Optional[str]:
    r = _intent_head(reason).lower()        # env/snapshot/debt markers on the intent, not the dump
    if not r.strip():
        return None
    if any(m in r for m in _ENV_MARKERS):
        return ENVIRONMENT
    if any(m in r for m in _SNAPSHOT_MARKERS):
        return SNAPSHOT_DRIFT
    if any(m in r for m in _DEBT_MARKERS):
        return TEST_DEBT
    return None


# --- prior 2: the leading exception class -----------------------------------------------------------

_EXC_ENV = {
    "filenotfounderror", "modulenotfounderror", "importerror", "connectionerror",
    "connectionrefusederror", "connectionreseterror", "timeouterror", "permissionerror",
    "unicodedecodeerror", "unicodeencodeerror", "oserror", "brokenpipeerror", "environmenterror",
}
_EXC_BROKEN = {
    "assertionerror", "keyerror", "indexerror", "valueerror", "attributeerror", "typeerror",
    "runtimeerror", "nameerror", "zerodivisionerror", "notimplementederror", "stopiteration",
}
_EXC_RE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception|Warning))\b")


def exception_prior(reason: str) -> Optional[str]:
    r = str(reason or "")
    low = r.lower()
    # harness phrasings carry no exception class but are unambiguous infra/env.
    if "worker" in low and "crashed" in low:
        return ENVIRONMENT
    if low.strip() == "collection failure":
        return ENVIRONMENT
    m = _EXC_RE.match(r)
    if not m:
        return None
    e = m.group(1).lower()
    if e in _EXC_ENV:
        return ENVIRONMENT
    if e.endswith("warning") or "deprecat" in e:
        return TEST_DEBT
    if e in _EXC_BROKEN:
        return GENUINELY_BROKEN
    return None


# --- prior 3: what the assertion is structurally ABOUT ----------------------------------------------

_HTML_RE = re.compile(r"<!doctype html|<html\b", re.I)
_CACHE_BUST_RE = re.compile(r"app\.css\?v=|app\.js|atlas-dashboard-\d|cache_bust|\?v=atlas", re.I)
_CRLF_RE = re.compile(r"\\r\\n")


def structure_prior(reason: str) -> Optional[str]:
    r = str(reason or "")
    head = _intent_head(r).lower()                   # the compared values (CRLF / cuda live here)
    if _CRLF_RE.search(head) and "\\n" in head:      # difference is only the line ending
        return ENVIRONMENT
    if ("'cuda'" in head and "'cpu'" in head) or "runpod" in head:
        return ENVIRONMENT
    if _CACHE_BUST_RE.search(r):                      # cache-bust version token drifted (scan full)
        return SNAPSHOT_DRIFT
    if _HTML_RE.search(r):                            # asserting on / about a rendered HTML document
        return SNAPSHOT_DRIFT
    return None


# --- prior 4: the test harness ----------------------------------------------------------------------

_INFRA_MARKERS = (
    "worker", "crashed while running", "node down", "replacing crashed worker",
    "collection failure", "internalerror", "errorcollecting", "error collecting",
    "conftest", "fixture", "failed on setup", "failed on teardown",
)


def infra_prior(reason: str) -> Optional[str]:
    low = _intent_head(reason).lower()      # harness signal is in the intent, never in a rendered body
    if "worker" in low and "crash" in low:
        return ENVIRONMENT
    if any(m in low for m in ("collection failure", "internalerror", "error collecting",
                              "failed on setup", "failed on teardown")):
        return ENVIRONMENT
    return None


_PRIORS: tuple[tuple[str, Callable[[str], Optional[str]]], ...] = (
    ("marker", marker_prior),
    ("exception", exception_prior),
    ("structure", structure_prior),
    ("infra", infra_prior),
)


@dataclass
class PanelClassification:
    category: str                       # the settled label, or the majority best-guess when split
    agree: bool                         # all non-abstaining priors voted the same label
    escalate: bool                      # not unanimous (or no prior had a signal) -> needs a judge
    confidence: float                   # fraction of voting priors that backed ``category``
    votes: dict = field(default_factory=dict)   # {prior_name: label|None}
    voters: int = 0                     # number of priors that did NOT abstain
    focus: list = field(default_factory=list)   # the competing labels a judge should adjudicate between


def classify_with_panel(reason: str) -> PanelClassification:
    """Run all priors and aggregate. Unanimous among non-abstainers -> settled; split (or no signal at
    all) -> escalate, with the majority label as the best guess the judge will confirm or overturn.

    ``focus`` is the set of competing labels — for a split that is exactly the disagreement the judge must
    decide; for a settled failure it is the single agreed label."""
    votes = {name: fn(reason) for name, fn in _PRIORS}
    cast = [v for v in votes.values() if v is not None]
    if not cast:
        # no prior had a signal — genuinely unknown, default to broken but flag for a judge.
        return PanelClassification(GENUINELY_BROKEN, agree=False, escalate=True, confidence=0.0,
                                   votes=votes, voters=0, focus=[GENUINELY_BROKEN])
    counts = Counter(cast)
    label, n = counts.most_common(1)[0]
    distinct = len(set(cast))
    # focus: distinct candidates, most-supported first (so the judge sees the live alternatives).
    focus = [c for c, _ in counts.most_common()]
    return PanelClassification(
        category=label,
        agree=(distinct == 1),
        escalate=(distinct != 1),
        confidence=round(n / len(cast), 3),
        votes=votes,
        voters=len(cast),
        focus=focus,
    )


# --- focus-guided weak-LLM adjudication (absorbed from the earlier failure_signals ensemble) ---------

import json  # noqa: E402

_FOCUS_SYSTEM = "You adjudicate a test failure that automated signals disagree on. Return one JSON object."
_VALID = {ENVIRONMENT, SNAPSHOT_DRIFT, TEST_DEBT, GENUINELY_BROKEN}


def judge_with_focus(llm_json_fn: Callable[[str, str], Optional[dict]], reason: str, focus: list, *,
                     test_id: str = "", code_excerpt: str = "", votes: Optional[dict] = None) -> str:
    """Targeted weak-LLM adjudication GUIDED by the panel's disagreement. The model is shown ONLY the
    competing labels (``focus``) and each prior's vote, and asked to pick among the focus labels — a
    narrowed decision, not a blind re-classification. This is where the weak LLM earns its cost: the
    deterministic priors already ruled out everything except ``focus``. Falls back to the first focus
    label on any problem (never raises, never fabricates an out-of-focus answer)."""
    candidates = [c for c in (focus or []) if c in _VALID] or [GENUINELY_BROKEN]
    if len(candidates) == 1:
        return candidates[0]
    try:
        user = json.dumps({
            "task": ("Automated deterministic signals disagree. Choose the single correct category from "
                     "`focus`. Return {\"category\": \"<one of focus>\", \"why\": \"<short>\"}."),
            "test_id": test_id,
            "failure_reason": str(reason)[:500],
            "code_excerpt": str(code_excerpt)[:1500],
            "focus": candidates,
            "prior_votes": votes or {},
        }, ensure_ascii=False)
        out = llm_json_fn(_FOCUS_SYSTEM, user) or {}
        cat = str(out.get("category") or "").strip().lower()
        return cat if cat in candidates else candidates[0]
    except Exception:
        return candidates[0]


@dataclass
class PanelTriageResult:
    total: int
    settled: int = 0                    # unanimous priors, no model needed
    escalated: int = 0                  # failures whose priors disagreed
    clusters: int = 0                   # root-cause clusters within the escalation set
    llm_calls: int = 0
    panel_counts: dict = field(default_factory=dict)    # buckets after the panel (pre-judge best guess)
    final_counts: dict = field(default_factory=dict)    # buckets after judging the escalation clusters
    final: list = field(default_factory=list)           # [{test_id, reason, category, source, votes}]
    representatives: list = field(default_factory=list)
    reclassified: list = field(default_factory=list)    # reps the judge moved off the panel best-guess


def triage_with_panel(
    failures: list,
    *,
    judge_fn: Optional[Callable[[str, str, list], str]] = None,
) -> PanelTriageResult:
    """Classify every failure with the panel; settled failures are taken as-is, the disagreement residual
    is clustered by root cause and ONE representative per cluster is judged (if ``judge_fn`` given) and
    propagated. The model touches only the genuinely-contested clusters.

    ``judge_fn(reason, test_id, focus) -> category`` receives the competing labels (``focus``) so it can
    adjudicate the exact disagreement rather than re-guess from scratch."""
    records = []
    for test_id, reason in failures:
        pc = classify_with_panel(reason)
        records.append({"test_id": str(test_id), "reason": str(reason), "category": pc.category,
                        "panel": pc.category, "agree": pc.agree, "escalate": pc.escalate,
                        "signature": root_cause_signature(reason), "votes": pc.votes, "focus": pc.focus,
                        "source": "panel_unanimous" if pc.agree else "panel_split"})

    clusters: dict[str, list] = {}
    for rec in records:
        if rec["escalate"]:
            clusters.setdefault(rec["signature"], []).append(rec)

    representatives, reclassified, llm_calls = [], [], 0
    for sig, members in clusters.items():
        rep = members[0]
        entry = {"signature": sig, "test_id": rep["test_id"], "reason": rep["reason"],
                 "members": len(members), "panel_guess": rep["panel"], "category": rep["panel"],
                 "focus": rep["focus"]}
        if judge_fn is not None:
            verdict = judge_fn(rep["reason"], rep["test_id"], rep["focus"])
            llm_calls += 1
            entry["category"] = verdict
            if verdict != rep["panel"]:
                reclassified.append({**entry})
            for m in members:
                m["category"] = verdict
                m["source"] = "llm_cluster"
        representatives.append(entry)

    def _counts(key):
        c: dict = Counter(r[key] for r in records)
        return dict(c)

    return PanelTriageResult(
        total=len(records),
        settled=sum(1 for r in records if not r["escalate"]),
        escalated=sum(1 for r in records if r["escalate"]),
        clusters=len(clusters),
        llm_calls=llm_calls,
        panel_counts=_counts("panel"),
        final_counts=_counts("category"),
        final=records,
        representatives=representatives,
        reclassified=reclassified,
    )
