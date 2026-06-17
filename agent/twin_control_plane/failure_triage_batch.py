"""Batch triage for a whole failure set — make "judge all N failures" feasible without N model calls.

Running the weak LLM (let alone the 2-pass critique judge) on every one of ~500 failures is slow and
wasteful. Two facts make it unnecessary:

1. The deterministic classifier settles every failure that matches a strong marker (CRLF, runpod,
   doctype, deprecation) with HIGH confidence. Only the residual that falls through to
   ``genuinely_broken`` with NO marker is genuinely uncertain — that is the only set worth a model.
2. The residual clusters hard by root cause (``root_cause_signature``): hundreds of failures collapse to
   a few dozen distinct causes. Judging ONE representative per cluster and propagating to its members
   replaces hundreds of model calls with a few dozen.

So the routing is: deterministic-classify ALL (instant) → escalate only the low-confidence residual →
judge one representative per ROOT-CAUSE CLUSTER → propagate. The model touches a handful of items, the
whole set is classified. This is the function that makes evaluating the full failure list practical.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from agent.twin_control_plane.failure_classifier import (
    GENUINELY_BROKEN, _DEBT_MARKERS, _ENV_MARKERS, _SNAPSHOT_MARKERS, classify_failure_reason,
    root_cause_signature,
)

# A failure is HIGH-confidence deterministic iff some marker matched; LOW iff it defaulted to
# genuinely_broken with nothing matching (or had no reason text).
_ALL_MARKERS = tuple(_ENV_MARKERS) + tuple(_SNAPSHOT_MARKERS) + tuple(_DEBT_MARKERS)


def classification_confidence(reason: str) -> str:
    """``"high"`` if the reason matched a classifier marker (settled deterministically); ``"low"`` if it
    fell through to ``genuinely_broken`` with no marker (a model second opinion is worth it)."""
    r = str(reason or "").lower()
    if r.strip() and any(m in r for m in _ALL_MARKERS):
        return "high"
    return "low"


@dataclass
class BatchTriageResult:
    total: int
    deterministic_counts: dict = field(default_factory=dict)
    final_counts: dict = field(default_factory=dict)
    clusters: int = 0
    escalated_clusters: int = 0
    llm_calls: int = 0
    final: list = field(default_factory=list)            # [{test_id, reason, category, source, signature}]
    representatives: list = field(default_factory=list)   # [{signature, test_id, reason, members, category}]
    reclassified: list = field(default_factory=list)      # reps the model moved off the deterministic label


def _counts(items, key) -> dict:
    out: dict = defaultdict(int)
    for it in items:
        out[it[key]] += 1
    return dict(out)


def triage_failures(
    failures: list,
    *,
    judge_fn: Optional[Callable[[str, str], str]] = None,
    escalate_labels: tuple = (GENUINELY_BROKEN,),
) -> BatchTriageResult:
    """Triage ``failures`` (list of ``(test_id, reason)``).

    Every failure is classified deterministically first. Failures whose deterministic label is in
    ``escalate_labels`` AND whose confidence is "low" are clustered by root-cause signature; if
    ``judge_fn`` is given, ONE representative per cluster is judged and the result propagated to the
    whole cluster. ``judge_fn(reason, test_id) -> category`` is any model judge (single-shot or the
    2-pass critique). With ``judge_fn=None`` the function does the deterministic-only triage and reports
    how many clusters WOULD be escalated (the cost estimate)."""
    records = []
    for test_id, reason in failures:
        det = classify_failure_reason(reason)
        conf = classification_confidence(reason)
        records.append({"test_id": str(test_id), "reason": str(reason),
                        "deterministic": det, "confidence": conf,
                        "signature": root_cause_signature(reason),
                        "category": det, "source": "deterministic"})

    # Cluster the low-confidence, escalation-eligible residual by root cause.
    clusters: dict[str, list] = defaultdict(list)
    for rec in records:
        if rec["deterministic"] in escalate_labels and rec["confidence"] == "low":
            clusters[rec["signature"]].append(rec)

    representatives = []
    reclassified = []
    llm_calls = 0
    for sig, members in clusters.items():
        rep = members[0]
        rep_entry = {"signature": sig, "test_id": rep["test_id"], "reason": rep["reason"],
                     "members": len(members), "category": rep["deterministic"]}
        if judge_fn is not None:
            verdict = judge_fn(rep["reason"], rep["test_id"])
            llm_calls += 1
            rep_entry["category"] = verdict
            if verdict != rep["deterministic"]:
                reclassified.append({**rep_entry})
            for m in members:
                m["category"] = verdict
                m["source"] = "llm_cluster"
        representatives.append(rep_entry)

    return BatchTriageResult(
        total=len(records),
        deterministic_counts=_counts(records, "deterministic"),
        final_counts=_counts(records, "category"),
        clusters=len(clusters),
        escalated_clusters=len(clusters),
        llm_calls=llm_calls,
        final=records,
        representatives=representatives,
        reclassified=reclassified,
    )


def estimate_cost(failures: list, *, secs_per_call: float = 5.3,
                  escalate_labels: tuple = (GENUINELY_BROKEN,)) -> dict:
    """Deterministic dry-run: how many model calls the routed triage would make, and the time, vs the
    naive "judge every failure" cost — so feasibility is known before spending the calls."""
    res = triage_failures(failures, judge_fn=None, escalate_labels=escalate_labels)
    routed_calls = res.escalated_clusters
    naive_calls = len(failures)
    return {
        "failures": naive_calls,
        "routed_llm_calls": routed_calls,
        "naive_llm_calls": naive_calls,
        "reduction_x": round(naive_calls / routed_calls, 1) if routed_calls else float("inf"),
        "routed_secs": round(routed_calls * secs_per_call, 1),
        "naive_secs": round(naive_calls * secs_per_call, 1),
        "deterministic_counts": res.deterministic_counts,
    }
