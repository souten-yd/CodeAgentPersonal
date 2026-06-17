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

import re
from collections import Counter, defaultdict
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


def propagation_key(reason: str) -> str:
    """A FINER grouping key than ``root_cause_signature`` for safe cluster propagation.

    ``root_cause_signature`` masks quoted literals (``KeyError: 'plan_pool'`` and ``KeyError: 'other'``
    both become ``KeyError: X``) — too coarse to propagate ONE verdict across, because a different key is
    a different cause. This keeps the distinguishing literals and masks only volatile numbers/addresses,
    so two failures share a key only when they are genuinely the same failure. Over-splitting is the safe
    bias (it just means more judgments); under-splitting is the dangerous one (a wrong verdict spreads)."""
    r = re.sub(r"0x[0-9a-fA-F]+", "H", str(reason or ""))
    r = re.sub(r"\b\d+\b", "N", r)
    return r[:120].strip()


@dataclass
class BatchTriageResult:
    total: int
    deterministic_counts: dict = field(default_factory=dict)
    final_counts: dict = field(default_factory=dict)
    clusters: int = 0
    escalated_clusters: int = 0
    llm_calls: int = 0
    propagated_clusters: int = 0   # clusters whose sampled reps AGREED -> verdict propagated to members
    contested_clusters: int = 0    # clusters whose reps disagreed -> every member judged individually
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
    samples_per_cluster: int = 1,
    full: bool = False,
) -> BatchTriageResult:
    """Triage ``failures`` (list of ``(test_id, reason)``).

    Every failure is classified deterministically first. Failures whose deterministic label is in
    ``escalate_labels`` AND whose confidence is "low" are clustered by ``propagation_key`` (a FINE key
    that keeps distinguishing literals, so a cluster is genuinely one failure). For each cluster the
    model judges up to ``samples_per_cluster`` representatives:

    - the sampled verdicts AGREE  -> propagate that verdict to every member (the fast path).
    - the sampled verdicts DISAGREE -> the cluster is contested; judge EVERY member individually so no
      wrong verdict is propagated across a non-uniform cluster.

    ``samples_per_cluster=1`` is the fast mode (one rep, always "agrees"). Raising it trades model calls
    for propagation safety; ``full=True`` judges every low-confidence item individually (most accurate,
    no propagation at all) — appropriate for a one-time initial import where accuracy outranks speed.
    ``judge_fn(reason, test_id) -> category`` is any model judge; ``judge_fn=None`` is a deterministic
    dry-run that reports how many clusters WOULD escalate."""
    records = []
    for test_id, reason in failures:
        det = classify_failure_reason(reason)
        conf = classification_confidence(reason)
        records.append({"test_id": str(test_id), "reason": str(reason),
                        "deterministic": det, "confidence": conf,
                        "signature": root_cause_signature(reason),
                        "prop_key": propagation_key(reason),
                        "category": det, "source": "deterministic"})

    # Cluster the low-confidence, escalation-eligible residual by the FINE propagation key.
    clusters: dict[str, list] = defaultdict(list)
    for rec in records:
        if rec["deterministic"] in escalate_labels and rec["confidence"] == "low":
            clusters[rec["prop_key"]].append(rec)

    representatives = []
    reclassified = []
    llm_calls = 0
    propagated = 0
    contested = 0

    def _assign(member, verdict, source):
        nonlocal reclassified
        member["category"] = verdict
        member["source"] = source
        if verdict != member["deterministic"]:
            reclassified.append({"test_id": member["test_id"], "reason": member["reason"][:160],
                                 "from": member["deterministic"], "to": verdict})

    for key, members in clusters.items():
        rep_entry = {"signature": key, "test_id": members[0]["test_id"],
                     "reason": members[0]["reason"], "members": len(members),
                     "category": members[0]["deterministic"]}
        representatives.append(rep_entry)
        if judge_fn is None:
            continue

        if full:
            # No propagation: judge every member directly.
            for m in members:
                _assign(m, judge_fn(m["reason"], m["test_id"]), "llm_direct")
                llm_calls += 1
            rep_entry["category"] = members[0]["category"]
            continue

        k = max(1, min(samples_per_cluster, len(members)))
        sample = members[:k]
        verdicts = []
        for m in sample:
            v = judge_fn(m["reason"], m["test_id"])
            llm_calls += 1
            verdicts.append(v)
        if len(set(verdicts)) == 1:
            # Reps agree -> safe to propagate to the whole cluster.
            verdict = verdicts[0]
            rep_entry["category"] = verdict
            propagated += 1
            for m in members:
                _assign(m, verdict, "llm_cluster")
        else:
            # Reps disagree -> contested cluster; judge every remaining member individually.
            contested += 1
            for m, v in zip(sample, verdicts):
                _assign(m, v, "llm_direct")
            for m in members[k:]:
                _assign(m, judge_fn(m["reason"], m["test_id"]), "llm_direct")
                llm_calls += 1
            rep_entry["category"] = "contested"

    return BatchTriageResult(
        total=len(records),
        deterministic_counts=_counts(records, "deterministic"),
        final_counts=_counts(records, "category"),
        clusters=len(clusters),
        escalated_clusters=len(clusters),
        llm_calls=llm_calls,
        propagated_clusters=propagated,
        contested_clusters=contested,
        final=records,
        representatives=representatives,
        reclassified=reclassified,
    )


def _eligible_count(failures: list, escalate_labels: tuple) -> int:
    return sum(1 for _t, r in failures
               if classify_failure_reason(r) in escalate_labels and classification_confidence(r) == "low")


def estimate_cost(failures: list, *, secs_per_call: float = 5.3, samples_per_cluster: int = 1,
                  escalate_labels: tuple = (GENUINELY_BROKEN,)) -> dict:
    """Deterministic dry-run: the model-call count and time the routed triage would take, vs the naive
    "judge every failure" cost — so feasibility is known before spending the calls. ``routed`` assumes
    every cluster's reps agree (the best case, ``samples_per_cluster`` calls per cluster); ``full`` is the
    most-accurate mode that judges every eligible item. The real cost lands between routed and full as
    contested clusters fall back to per-item judging."""
    res = triage_failures(failures, judge_fn=None, escalate_labels=escalate_labels)
    clusters = res.escalated_clusters
    eligible = _eligible_count(failures, escalate_labels)
    routed_calls = clusters * max(1, samples_per_cluster)
    naive_calls = len(failures)
    return {
        "failures": naive_calls,
        "escalated_clusters": clusters,
        "eligible_items": eligible,
        "routed_llm_calls": routed_calls,           # best case: all clusters agree
        "full_llm_calls": eligible,                 # most-accurate: judge every eligible item
        "naive_llm_calls": naive_calls,
        "reduction_x": round(naive_calls / routed_calls, 1) if routed_calls else float("inf"),
        "routed_secs": round(routed_calls * secs_per_call, 1),
        "full_secs": round(eligible * secs_per_call, 1),
        "naive_secs": round(naive_calls * secs_per_call, 1),
        "deterministic_counts": res.deterministic_counts,
    }
