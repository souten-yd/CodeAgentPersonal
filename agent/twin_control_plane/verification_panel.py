"""Multi-perspective verification — score a change from several angles, then aggregate.

A single signal ("the tests pass", "the model says ok") is a brittle basis for keeping or rolling back
a change. This evaluates a change from several INDEPENDENT perspectives, each producing a score in
[0, 1] plus findings, and aggregates the scores into one verdict. The perspectives are ordered cheap →
expensive and a GATING perspective short-circuits: if the code does not even parse there is no point
running the tests.

Deterministic perspectives (no model):
- ``syntax`` (構文検証): every changed file parses / compiles. Gating — a SyntaxError is a hard reject.
- ``reference`` (参照検証): generated code does not import/call a project symbol that does not exist
  (reuses ``reference_check`` against the Twin's symbol index).
- ``semantic`` (意味検証): the baseline-comparison verdict on the impacted tests
  (``baseline_verify``) — PASS=1.0, AMBIGUOUS=0.5, FAIL=0.0, UNVERIFIABLE=abstain.

Aggregation yields ACCEPT / REJECT / REVIEW. REVIEW is the residual the deterministic panel cannot
settle on its own (middling score, or every perspective abstained); only that residual is handed to the
weak-LLM critique pass — so the model is used minimally, on what the machine genuinely cannot decide.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

from agent.twin_control_plane.baseline_verify import (
    AMBIGUOUS as _V_AMBIGUOUS, FAIL as _V_FAIL, PASS as _V_PASS, UNVERIFIABLE as _V_UNVERIFIABLE,
    VerificationVerdict,
)
from agent.twin_control_plane.reference_check import check_project_references

ACCEPT = "accept"   # high combined score, no gate failed — keep
REJECT = "reject"   # a gate failed, or the combined score is below the review floor — roll back
REVIEW = "review"   # middling / abstained — the deterministic panel cannot settle it (-> LLM critique)


@dataclass
class Perspective:
    name: str
    score: Optional[float]      # 0..1; None = abstained (this angle could not be evaluated)
    weight: float = 1.0
    gating: bool = False        # if True and score < gate_threshold -> hard reject, short-circuit
    findings: list = field(default_factory=list)
    detail: str = ""


@dataclass
class PanelVerdict:
    decision: str
    confidence: float                       # weighted mean of the non-abstaining scores (0 if none)
    perspectives: list[Perspective] = field(default_factory=list)
    gate_failed: str = ""                   # name of the gating perspective that failed, if any
    abstained: list[str] = field(default_factory=list)
    reason: str = ""


def syntax_perspective(changed_files: Mapping[str, str], *, weight: float = 1.0) -> Perspective:
    """構文検証 — every changed Python file must parse. Gating: one SyntaxError fails the change."""
    bad: list[dict] = []
    checked = 0
    for path, content in (changed_files or {}).items():
        if not str(path).endswith(".py"):
            continue
        checked += 1
        try:
            ast.parse(content or "")
        except SyntaxError as exc:
            bad.append({"path": str(path), "reason": f"{exc.msg} (line {exc.lineno})"})
    if checked == 0:
        return Perspective("syntax", None, weight, gating=True, detail="no python files to parse")
    score = 0.0 if bad else 1.0
    return Perspective("syntax", score, weight, gating=True, findings=bad,
                       detail=("syntax ok" if not bad else f"{len(bad)} file(s) do not parse"))


def reference_perspective(changed_files: Mapping[str, str], *, modules: set[str],
                          module_symbols: set[str], weight: float = 2.0) -> Perspective:
    """参照検証 — generated code must not reference project symbols that do not exist. Abstains when
    there is no project import to check (nothing to score)."""
    findings: list[dict] = []
    any_project_import = False
    for path, content in (changed_files or {}).items():
        if not str(path).endswith(".py"):
            continue
        f = check_project_references(content or "", modules=modules, module_symbols=module_symbols)
        if f:
            findings.extend({**item, "path": str(path)} for item in f)
        # detect whether there was any project import at all (so we can abstain when there is none)
        try:
            tree = ast.parse(content or "")
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "") in modules and not node.level:
                any_project_import = True
            elif isinstance(node, ast.Import) and any(
                a.name in modules or a.name.split(".", 1)[0] in {m.split(".", 1)[0] for m in modules}
                for a in node.names
            ):
                any_project_import = True
    if not any_project_import:
        return Perspective("reference", None, weight, detail="no project imports to verify")
    score = 0.0 if findings else 1.0
    return Perspective("reference", score, weight, findings=findings,
                       detail=("all project references resolve" if not findings
                               else f"{len(findings)} invented reference(s)"))


_SEMANTIC_SCORE = {_V_PASS: 1.0, _V_AMBIGUOUS: 0.5, _V_FAIL: 0.0, _V_UNVERIFIABLE: None}


def semantic_perspective(verdict: VerificationVerdict, *, weight: float = 3.0) -> Perspective:
    """意味検証 — the baseline-comparison verdict on the impacted tests. UNVERIFIABLE abstains (no
    covering test could confirm the change)."""
    score = _SEMANTIC_SCORE.get(verdict.decision, 0.5)
    return Perspective("semantic", score, weight,
                       findings=list(verdict.new_failures),
                       detail=f"baseline verdict={verdict.decision}: {verdict.reason}")


def aggregate(perspectives: Iterable[Perspective], *, gate_threshold: float = 0.5,
              accept_threshold: float = 0.999, review_floor: float = 0.5) -> PanelVerdict:
    """Combine perspective scores into one verdict.

    1. A GATING perspective scored below ``gate_threshold`` is a hard REJECT (short-circuit).
    2. Otherwise the confidence is the weighted mean of the scored (non-abstaining) perspectives.
       >= ``accept_threshold`` -> ACCEPT; < ``review_floor`` -> REJECT; in between -> REVIEW.
    3. If every perspective abstained there is nothing to go on -> REVIEW (hand to the critique pass)."""
    ps = list(perspectives)
    for p in ps:
        if p.gating and p.score is not None and p.score < gate_threshold:
            return PanelVerdict(REJECT, 0.0, ps, gate_failed=p.name,
                                abstained=[q.name for q in ps if q.score is None],
                                reason=f"gating perspective '{p.name}' failed: {p.detail}")
    scored = [p for p in ps if p.score is not None and p.weight > 0]
    abstained = [p.name for p in ps if p.score is None]
    if not scored:
        return PanelVerdict(REVIEW, 0.0, ps, abstained=abstained,
                            reason="every perspective abstained; nothing could be verified")
    total_w = sum(p.weight for p in scored)
    confidence = sum((p.score or 0.0) * p.weight for p in scored) / total_w
    if confidence >= accept_threshold:
        decision = ACCEPT
        reason = "all perspectives agree the change is safe"
    elif confidence < review_floor:
        decision = REJECT
        reason = f"combined score {confidence:.2f} below review floor {review_floor:.2f}"
    else:
        decision = REVIEW
        reason = f"combined score {confidence:.2f} is inconclusive; needs a context judgment"
    return PanelVerdict(decision, confidence, ps, abstained=abstained, reason=reason)


def evaluate_change(changed_files: Mapping[str, str], semantic_verdict: VerificationVerdict, *,
                    modules: Optional[set[str]] = None, module_symbols: Optional[set[str]] = None,
                    **agg_kwargs) -> PanelVerdict:
    """Build the standard deterministic panel (syntax + reference + semantic) and aggregate it."""
    perspectives = [syntax_perspective(changed_files)]
    if modules is not None and module_symbols is not None:
        perspectives.append(reference_perspective(changed_files, modules=modules,
                                                   module_symbols=module_symbols))
    perspectives.append(semantic_perspective(semantic_verdict))
    return aggregate(perspectives, **agg_kwargs)
