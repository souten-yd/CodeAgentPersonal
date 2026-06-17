"""Turn a real pytest ``--junit-xml`` report into the routed batch triage — the bridge from "a full
suite ran and produced N failures" to "every failure is classified, with the model touching only the
genuinely-uncertain handful".

The pieces already exist: ``failure_classifier`` buckets a reason deterministically and
``failure_triage_batch`` does the routing (deterministic-classify ALL -> cluster the low-confidence
residual by root cause -> judge ONE representative per cluster -> propagate). What was missing is the
ingest: a real run writes its failures to a junit XML, not to a list of ``(test_id, reason)`` tuples.
This parses that XML into exactly that list, so the whole evaluation runs on the actual suite output.

``parse_junit_failures`` reads both ``<failure>`` and ``<error>`` (collection errors are environment,
not code) and reconstructs a reason string the classifier can read (the ``message`` attribute carries
the exception's first line — ``KeyError: 'plan_pool'`` — and the body carries the traceback markers like
CRLF / runpod / doctype). ``run_junit_triage`` wires that into the batch triage with an optional judge.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Callable, Optional

from agent.twin_control_plane.failure_triage_batch import (
    BatchTriageResult, estimate_cost, triage_failures,
)


def _reason_from_node(node: ET.Element) -> str:
    """Reason string for a ``<failure>``/``<error>`` element.

    The ``message`` attribute is preferred: pytest puts the exception summary there (``KeyError:
    'plan_pool'``, and for assertions the rewritten comparison incl. CRLF markers), which is exactly what
    both ``classify_failure_reason`` and ``root_cause_signature`` read — using the full traceback body
    would over-split the clusters (every test has a distinct traceback). The body is only a fallback for
    nodes with no message (some collection errors), so no failure is left reason-less."""
    message = str(node.get("message") or "").strip()
    body = str(node.text or "").strip()
    return message or body


def parse_junit_failures(xml_path: str) -> list[tuple[str, str]]:
    """Parse a pytest junit-xml file into ``[(test_id, reason)]`` for every failed/errored testcase.

    ``test_id`` is ``classname::name`` (the pytest node id shape). Passed/skipped cases are ignored —
    only the actionable set is returned. Never raises on a missing child; a testcase with neither a
    ``<failure>`` nor an ``<error>`` is simply not a failure."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
    out: list[tuple[str, str]] = []
    for suite in suites:
        for case in suite.findall("testcase"):
            problem = case.find("failure")
            if problem is None:
                problem = case.find("error")
            if problem is None:
                continue
            classname = str(case.get("classname") or "").strip()
            name = str(case.get("name") or "").strip()
            test_id = f"{classname}::{name}" if classname else name
            out.append((test_id, _reason_from_node(problem)))
    return out


def run_junit_triage(
    xml_path: str,
    *,
    judge_fn: Optional[Callable[[str, str], str]] = None,
) -> tuple[BatchTriageResult, dict]:
    """Parse ``xml_path`` and run the routed batch triage over it.

    Returns ``(result, cost)`` where ``cost`` is the deterministic dry-run estimate (routed vs naive
    model calls) — always computed so feasibility is reported even when ``judge_fn`` is None."""
    failures = parse_junit_failures(xml_path)
    cost = estimate_cost(failures)
    result = triage_failures(failures, judge_fn=judge_fn)
    return result, cost


def _build_judge(base_url: str, model: str):
    """Wire the local weak-LLM critique judge into the ``judge_fn(reason, test_id) -> category`` shape the
    (non-panel) batch triage expects. Imported lazily so the parse path has no LLM dependency."""
    from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
    from agent.twin_control_plane.critique_judge import judge_failure_with_critique

    adapter = AtlasLLMJsonAdapter(base_url=base_url, model=model)

    def judge_fn(reason: str, test_id: str) -> str:
        return judge_failure_with_critique(adapter, reason, test_id=test_id).category

    return judge_fn


def run_panel_triage(xml_path: str, *, judge_fn: Optional[Callable[[str, str], str]] = None):
    """Parse ``xml_path`` and run the MULTI-PERSPECTIVE deterministic panel: several independent priors
    vote, unanimous failures are settled with no model, only the disagreement residual is judged. Returns
    a ``PanelTriageResult``."""
    from agent.twin_control_plane.deterministic_panel import triage_with_panel

    return triage_with_panel(parse_junit_failures(xml_path), judge_fn=judge_fn)


def _format_report(result: BatchTriageResult, cost: dict) -> str:
    lines = [
        f"failures parsed:        {result.total}",
        f"root-cause clusters:    {result.clusters} (low-confidence residual)",
        "",
        "cost (routed vs naive):",
        f"  naive model calls:    {cost['naive_llm_calls']}",
        f"  routed model calls:   {cost['routed_llm_calls']}  ({cost['reduction_x']}x fewer)",
        f"  routed time:          {cost['routed_secs']}s   (naive: {cost['naive_secs']}s)",
        "",
        "deterministic buckets:",
    ]
    for cat, n in sorted(result.deterministic_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {cat:<18} {n}")
    if result.llm_calls:
        lines += ["", "after model judgment:", f"  model calls made:     {result.llm_calls}",
                  f"  clusters reclassified:{len(result.reclassified)}", "", "final buckets:"]
        for cat, n in sorted(result.final_counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {cat:<18} {n}")
        for rc in result.reclassified:
            lines.append(f"  reclassified [{rc['members']:>3}x] {rc['signature']} -> {rc['category']}")
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Routed batch triage over a pytest junit-xml report.")
    parser.add_argument("xml_path", help="path to a pytest --junit-xml report")
    parser.add_argument("--judge", action="store_true", help="judge cluster reps with the local weak LLM")
    parser.add_argument("--panel", action="store_true",
                        help="use the multi-perspective deterministic panel (settle by prior agreement)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--model", default="")
    args = parser.parse_args(argv)

    if args.panel:
        # panel escalates only prior-disagreement; a focus-guided judge adjudicates the competing labels.
        judge_fn = None
        if args.judge:
            from agent.atlas_llm_json_adapter import AtlasLLMJsonAdapter
            from agent.twin_control_plane.deterministic_panel import judge_with_focus
            adapter = AtlasLLMJsonAdapter(base_url=args.base_url, model=args.model)

            def judge_fn(reason, test_id, focus):
                return judge_with_focus(adapter, reason, focus, test_id=test_id)
        res = run_panel_triage(args.xml_path, judge_fn=judge_fn)
        print(f"failures parsed:        {res.total}")
        print(f"settled by prior agreement (no model): {res.settled}")
        print(f"escalated (priors disagree): {res.escalated} -> {res.clusters} clusters, {res.llm_calls} model calls")
        print(f"\npanel best-guess buckets: {res.panel_counts}")
        if res.llm_calls:
            print(f"final buckets (after tie-break): {res.final_counts}")
            print(f"clusters moved off best-guess: {len(res.reclassified)}")
        return 0

    judge_fn = _build_judge(args.base_url, args.model) if args.judge else None
    result, cost = run_junit_triage(args.xml_path, judge_fn=judge_fn)
    print(_format_report(result, cost))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
