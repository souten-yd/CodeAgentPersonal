"""End-to-end autonomous code-repair loop — localize → synthesize → verify → keep/rollback.

Closes the self-heal loop frontier-free by composing the pieces the evaluation validated:
- LOCALIZE the buggy product function for a failing test (`cause_discovery.localize_from_test_calls` for
  value bugs that only point at the test line; the traceback frame for raising bugs);
- SYNTHESIZE a fix for that one function with the weak LLM (`code_synthesis_repair`);
- VERIFY deterministically by running the test; KEEP on pass, Git-rollback on fail.

The deterministic verify is the authority (the weak LLM only proposes). Safety: a candidate function in the
control surface (``self_protected``) is never auto-edited; only the single localized function is touched;
the test is never edited. A test may exercise several functions — each candidate is tried until one
synthesis passes the test, so the model's proposal is always grounded by the suite. All IO is injected for
unit testing and wires to real pytest/git/LLM in production.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from agent.twin_control_plane.causal_verification import verify_causal
from agent.twin_control_plane.cause_discovery import localize_from_test_calls
from agent.twin_control_plane.code_synthesis_repair import repair_file_with_synthesis
from agent.twin_control_plane.improvement_loop import KEPT, NEEDS_APPROVAL, ROLLED_BACK, SKIPPED
from agent.twin_control_plane.failure_repair_loop import _CONTROL_PREFIXES, _node_id, _test_file_of

SPURIOUS = "spurious"        # passed the test but the patch did not address the failure's cause


@dataclass
class SynthResult:
    test_id: str
    outcome: str
    func: str = ""
    file: str = ""
    detail: str = ""
    candidates: list = field(default_factory=list)


def _default_read(p: str, repo_root: str) -> str:
    return (Path(repo_root) / p).read_text(encoding="utf-8")


def _default_write(p: str, s: str, repo_root: str) -> None:
    (Path(repo_root) / p).write_text(s, encoding="utf-8")


def _default_run_test(node_id: str, repo_root: str) -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", node_id, "-p", "no:cacheprovider", "-q", "--timeout=120"],
        cwd=repo_root, capture_output=True, text=True)
    return proc.returncode == 0


def _default_git_checkout(path: str, repo_root: str) -> None:
    subprocess.run(["git", "checkout", "--", path], cwd=repo_root, check=False)


def repair_one(
    test_id: str,
    reason: str,
    *,
    llm_json_fn: Callable[[str, str], Optional[dict]],
    repo_root: str = ".",
    include=("app/", "agent/"),
    read_fn: Optional[Callable[[str], str]] = None,
    write_fn: Optional[Callable[[str, str], None]] = None,
    run_test_fn: Optional[Callable[[str], bool]] = None,
    git_checkout_fn: Optional[Callable[[str], None]] = None,
    localize_fn: Optional[Callable[[str, str], list]] = None,
    approved: bool = False,
) -> SynthResult:
    """Localize → synthesize → verify for ONE failing test. Tries each exercised function until one fix
    passes the test; rolls back any candidate that does not. Never raises."""
    read = read_fn or (lambda p: _default_read(p, repo_root))
    write = write_fn or (lambda p, s: _default_write(p, s, repo_root))
    run_test = run_test_fn or (lambda nid: _default_run_test(nid, repo_root))
    git_checkout = git_checkout_fn or (lambda p: _default_git_checkout(p, repo_root))

    test_file = _test_file_of(test_id)
    test_name = str(test_id).split("::", 1)[1] if "::" in str(test_id) else ""
    nid = _node_id(test_id)
    try:
        test_src = read(test_file)
    except Exception as exc:  # noqa: BLE001
        return SynthResult(test_id, SKIPPED, detail=f"cannot read test: {type(exc).__name__}")

    localize = localize_fn or (lambda src, tn: localize_from_test_calls(
        src, repo_root=repo_root, include=include, only_test=tn))
    candidates = localize(test_src, test_name)
    cand_names = [f"{o.file}::{o.token}" for o in candidates]
    if not candidates:
        return SynthResult(test_id, SKIPPED, detail="no product function localized", candidates=cand_names)

    # safety: never auto-edit the control surface without approval
    if any(o.file.startswith(p) for o in candidates for p in _CONTROL_PREFIXES) and not approved:
        return SynthResult(test_id, NEEDS_APPROVAL, detail="candidate touches the control surface",
                           candidates=cand_names)

    saw_spurious = False
    for o in candidates:
        try:
            src = read(o.file)
            new_src = repair_file_with_synthesis(
                file_source=src, func_name=o.token, failure_reason=reason,
                test_text=test_src, llm_json_fn=llm_json_fn)
        except Exception:  # noqa: BLE001
            new_src = None
        if not new_src:
            continue
        write(o.file, new_src)
        if run_test(nid):
            # a passing test is NOT proof of a correct fix — reject a patch that does not address the
            # failure's cause (the #1933 spurious-pass class).
            verdict = verify_causal(src, new_src, reason, target_func=o.token, localized_func=o.token)
            if verdict.causal:
                return SynthResult(test_id, KEPT, func=o.token, file=o.file,
                                   detail="synthesized fix verified (causal)", candidates=cand_names)
            saw_spurious = True
            git_checkout(o.file)                 # passed but spurious -> reject, try the next candidate
            continue
        git_checkout(o.file)                     # this candidate did not fix it — revert, try the next
    if saw_spurious:
        return SynthResult(test_id, SPURIOUS,
                           detail="a candidate passed the test but did not address the cause",
                           candidates=cand_names)
    return SynthResult(test_id, ROLLED_BACK, detail="no candidate fix passed the test", candidates=cand_names)


def run_synthesis_repair(
    failures: list,
    *,
    llm_json_fn: Callable[[str, str], Optional[dict]],
    repo_root: str = ".",
    include=("app/", "agent/"),
    max_repairs: int = 50,
    approved: bool = False,
    **io,
) -> list[SynthResult]:
    """Autonomously repair ``failures`` (``[(test_id, reason)]``) by localized weak-LLM synthesis, each
    fix verified by running its test. Bounded by ``max_repairs``. Frontier-free."""
    out: list[SynthResult] = []
    for test_id, reason in list(failures)[: max(0, max_repairs)]:
        out.append(repair_one(test_id, reason, llm_json_fn=llm_json_fn, repo_root=repo_root,
                              include=include, approved=approved, **io))
    return out
