"""Shared-cause batch repair — turn "N failures" into "one shared cause × N dependents", safely.

The triage panel shows the failure set is heavy-tailed: a large fraction of failures live in a few
clusters that share ONE root cause (one changed contract, one renamed enum, one policy). Fixing the
shared cause once and propagating the template to its dependents is far cheaper than N bespoke fixes —
*if* the cluster genuinely has one cause and *if* the edit cannot weaken a test. This module supplies
the two deterministic, frontier-free guards that make that safe:

1. **single-source verification** (the over-merge guard): clustering by a masked root-cause signature
   collapses ``KeyError: 'plan_pool'`` ×83 to one signature — but ``assert X == X`` also collapses 37
   *different* value mismatches to one signature. ``extract_cause`` recovers the concrete cause key
   (the missing key, the renamed enum pair, the missing fields) and a cluster is only ``single_source``
   when its members AGREE on that key. A batch repair is offered only for single-source clusters; a
   heterogeneous look-alike is flagged for individual handling, never batch-edited.

2. **assertion preservation** (the safety gate): a test-debt fix may update a test's INPUT/fixture but
   must never remove or weaken an assertion (that would "fix" the failure by deleting the check).
   ``assertion_preserving_edit`` compares the assertions (AST) of the old and new test source and rejects
   any edit that drops one. This is what lets an autonomous loop touch tests at all.

Neither guard runs a model; both are pure analysis. The actual edit synthesis (e.g. building the
per-test ``plan_payload``) and execution stay behind these guards and an approval gate.
"""
from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from agent.twin_control_plane.failure_classifier import root_cause_signature

# Cause kinds, most-specific first. Each pattern is anchored at the start of the reason so a stray match
# deep in a rendered body cannot hijack the key (the same discipline the panel's _intent_head enforces).
_KEY_RE = re.compile(r"\s*KeyError:\s*'([^']*)'")
_FIELDS_RE = re.compile(r"\s*ValueError:\s*missing_required_fields:([^\n]+)")
_INVARIANT_RE = re.compile(r"\s*ValueError:\s*invariant_violation:(\w+)")
_POLICY_RE = re.compile(r"\s*ValueError:\s*([a-z_]+)=(?:false|true)\b")
_MISMATCH_RE = re.compile(r"\s*AssertionError:\s*assert '([^']*)' == '([^']*)'")
_SUBSTR_RE = re.compile(r"\s*AssertionError:\s*'([^']*)' not found in")
_EXC_RE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b")


def extract_cause(reason: str) -> tuple[str, str]:
    """Recover the concrete (kind, key) a failure is about, so a cluster's homogeneity can be checked.

    The key is the thing that must AGREE across a single-source cluster: the missing dict key, the
    renamed enum pair, the missing field list. Returns ``("other", "")`` when no specific cause is
    recognised (those clusters are never offered as a batch)."""
    r = str(reason or "")
    m = _KEY_RE.match(r)
    if m:
        return ("missing_key", m.group(1))
    m = _FIELDS_RE.match(r)
    if m:
        return ("missing_fields", ",".join(sorted(m.group(1).split(",")))[:80])
    m = _INVARIANT_RE.match(r)
    if m:
        return ("invariant", m.group(1))
    m = _POLICY_RE.match(r)
    if m:
        return ("policy", m.group(1))
    m = _MISMATCH_RE.match(r)
    if m:
        return ("value_mismatch", f"{m.group(1)[:30]}|{m.group(2)[:30]}")
    m = _SUBSTR_RE.match(r)
    if m:
        return ("missing_substring", m.group(1)[:40])
    m = _EXC_RE.match(r)
    if m:
        return ("exception", m.group(1).lower())
    return ("other", "")


@dataclass
class CauseCluster:
    signature: str
    kind: str
    key: str                       # the dominant concrete cause key
    members: list                  # [(test_id, reason)]
    single_source: bool            # members agree on the concrete cause key (not just the signature)
    homogeneity: float             # fraction of members sharing the dominant key
    batchable: bool                # single_source AND a recognised, non-generic cause

    @property
    def size(self) -> int:
        return len(self.members)


def cluster_shared_causes(failures: list, *, homogeneity_threshold: float = 0.9,
                          min_size: int = 5) -> list[CauseCluster]:
    """Group ``(test_id, reason)`` by root-cause signature, then verify each cluster is single-source by
    checking its members agree on the concrete ``extract_cause`` key. Returns clusters largest-first.

    ``batchable`` is True only for a single-source cluster of a RECOGNISED cause (not ``other``/generic
    ``exception``) at or above ``min_size`` — exactly the clusters where one templated fix safely
    addresses many dependents."""
    by_sig: dict[str, list] = defaultdict(list)
    for test_id, reason in failures:
        by_sig[root_cause_signature(reason)].append((test_id, reason))

    clusters: list[CauseCluster] = []
    for sig, members in by_sig.items():
        keys = Counter(extract_cause(r) for _t, r in members)
        (dom_kind, dom_key), n = keys.most_common(1)[0]
        homog = n / len(members)
        single = homog >= homogeneity_threshold
        recognised = dom_kind not in ("other", "exception")
        clusters.append(CauseCluster(
            signature=sig, kind=dom_kind, key=dom_key, members=members,
            single_source=single, homogeneity=round(homog, 3),
            batchable=bool(single and recognised and len(members) >= min_size),
        ))
    clusters.sort(key=lambda c: c.size, reverse=True)
    return clusters


# --- assertion-preservation safety gate -------------------------------------------------------------

_ASSERT_METHODS = ("assertEqual", "assertTrue", "assertFalse", "assertIn", "assertIs", "assertIsNone",
                   "assertIsNotNone", "assertRaises", "assertNotEqual", "assertNotIn", "assertGreater",
                   "assertLess", "assertAlmostEqual", "pytest.raises")


def _assertions(src: str) -> Optional[Counter]:
    """Multiset of the assertions in ``src`` (bare ``assert`` statements + unittest ``assert*`` calls).
    Returns None if the source does not parse (an unparseable edit is rejected outright)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    found: Counter = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            found[("assert", ast.dump(node.test))] += 1
        elif isinstance(node, ast.Call):
            name = ""
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in _ASSERT_METHODS:
                found[("call", name, ast.dump(ast.Tuple(elts=list(node.args), ctx=ast.Load())))] += 1
    return found


def assertion_preserving_edit(old_src: str, new_src: str) -> tuple[bool, list]:
    """True iff ``new_src`` keeps every assertion in ``old_src`` (input/fixture/setup may change freely,
    but no assertion may be removed or weakened). Returns ``(ok, removed_assertions)``.

    A removed/altered assertion is exactly how a test-debt "fix" can silently delete the check it was
    supposed to keep — this gate refuses such an edit so the autonomous loop can edit tests safely."""
    old_a = _assertions(old_src)
    new_a = _assertions(new_src)
    if old_a is None:
        return (False, [("error", "old source does not parse")])
    if new_a is None:
        return (False, [("error", "new source does not parse")])
    removed = old_a - new_a            # multiset difference: assertions present in old, missing in new
    return (len(removed) == 0, list(removed.elements()))


@dataclass
class BatchRepairPlan:
    total_failures: int
    batchable: list = field(default_factory=list)        # CauseCluster[] safe to template-fix
    needs_individual: list = field(default_factory=list)  # heterogeneous / unrecognised / small
    batchable_failures: int = 0
    individual_failures: int = 0

    def summary(self) -> dict:
        return {
            "total_failures": self.total_failures,
            "batchable_clusters": len(self.batchable),
            "batchable_failures": self.batchable_failures,
            "individual_failures": self.individual_failures,
            "batchable_pct": round(100 * self.batchable_failures / self.total_failures, 1)
            if self.total_failures else 0.0,
        }


def build_batch_repair_plan(failures: list, **kwargs) -> BatchRepairPlan:
    """Split ``failures`` into the single-source clusters a templated fix can address as a batch and the
    residual that needs individual handling — the deterministic, approval-ready repair plan. Does NOT
    edit anything; it reports WHAT a batch repair would cover and what it must not touch."""
    clusters = cluster_shared_causes(failures, **kwargs)
    batchable = [c for c in clusters if c.batchable]
    individual = [c for c in clusters if not c.batchable]
    return BatchRepairPlan(
        total_failures=len(failures),
        batchable=batchable,
        needs_individual=individual,
        batchable_failures=sum(c.size for c in batchable),
        individual_failures=sum(c.size for c in individual),
    )
