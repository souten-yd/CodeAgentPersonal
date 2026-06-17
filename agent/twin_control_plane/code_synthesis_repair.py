"""Weak-LLM code synthesis — the general fixer behind the deterministic gate.

Templated repair only handles known drifts; a generic logic bug (wrong operator, off-by-one, bad
arithmetic) has no template. This is the missing generator: given a LOCALIZED function (from
`cause_discovery`) and the FAILING TEST, the local weak LLM proposes a corrected version of *that one
function*, and the existing loop verifies it by running the test and rolls back on failure.

Safety is structural, not trust in the model:
- the synthesizer replaces ONLY the single localized function (AST-bounded) — never arbitrary code, so
  the blast radius is one function;
- the TEST is the oracle and is NEVER edited here, so the model cannot "fix" the failure by weakening the
  spec (the analogue of `assertion_preserving_edit` for product-code repair);
- a returned candidate is accepted only if it PARSES and still defines the same function — no
  half-written or signature-changed code is applied;
- the authority is the deterministic verify + Git-rollback in `failure_repair_loop`; this module only
  proposes the edit. Bounded retries; never raises.
"""
from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class FunctionSpan:
    name: str
    start: int      # 1-based first line (the `def`/decorator)
    end: int        # 1-based last line (inclusive)
    text: str


def extract_function(source: str, func_name: str) -> Optional[FunctionSpan]:
    """The source span of a MODULE-LEVEL function ``func_name`` (including decorators). None if absent."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    lines = source.splitlines()
    for node in tree.body:                       # module level only — bounded, predictable
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            end = node.end_lineno or node.lineno
            return FunctionSpan(func_name, start, end, "\n".join(lines[start - 1:end]))
    return None


def replace_function(source: str, func_name: str, new_func_text: str) -> Optional[str]:
    """Replace ``func_name``'s span with ``new_func_text``. Returns the new source only if it PARSES and
    still defines ``func_name`` (otherwise None — the edit is rejected, never applied half-formed)."""
    span = extract_function(source, func_name)
    if span is None:
        return None
    lines = source.splitlines()
    new_lines = lines[: span.start - 1] + new_func_text.rstrip("\n").splitlines() + lines[span.end:]
    candidate = "\n".join(new_lines) + ("\n" if source.endswith("\n") else "")
    check = extract_function(candidate, func_name)        # must parse AND still define the function
    return candidate if check is not None else None


_SYSTEM = "You repair a single Python function so a failing test passes. Return one JSON object only."
_INSTRUCTION = (
    "The function below fails the test below. Return the corrected FULL function (same name and "
    "signature), changing as little as possible. Do not change the test. Do not add imports or other "
    "functions.\nReturn {\"function\": \"<the complete corrected def ...>\"}."
)


def synthesize_function_fix(
    llm_json_fn: Callable[[str, str], Optional[dict]],
    *,
    func_text: str,
    func_name: str,
    failure_reason: str,
    test_text: str = "",
    code_context: str = "",
) -> Optional[str]:
    """Ask the weak LLM for a corrected version of ``func_text``. Returns new function source that PARSES
    and defines ``func_name``, else None (rejected). Never raises."""
    try:
        user = json.dumps({
            "task": _INSTRUCTION,
            "function": func_text[:2000],
            "failing_test": str(test_text)[:1500],
            "failure": str(failure_reason)[:400],
            "context": str(code_context)[:800],
        }, ensure_ascii=False)
        out = llm_json_fn(_SYSTEM, user) or {}
        cand = str(out.get("function") or "").strip()
        if not cand:
            return None
        # accept only a single, parseable function definition with the right name
        try:
            mod = ast.parse(cand)
        except SyntaxError:
            return None
        defs = [n for n in mod.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if len(defs) != 1 or defs[0].name != func_name:
            return None
        return cand
    except Exception:
        return None


def repair_file_with_synthesis(
    *,
    file_source: str,
    func_name: str,
    failure_reason: str,
    test_text: str,
    llm_json_fn: Callable[[str, str], Optional[dict]],
) -> Optional[str]:
    """End-to-end proposal: extract ``func_name`` → synthesize a fix → splice it back. Returns the new
    FILE source (parseable, same function present) or None if nothing safe could be produced. Does NOT
    write or verify — the caller (the repair loop) runs the test and keeps/rolls back."""
    span = extract_function(file_source, func_name)
    if span is None:
        return None
    new_func = synthesize_function_fix(
        llm_json_fn, func_text=span.text, func_name=func_name,
        failure_reason=failure_reason, test_text=test_text)
    if not new_func or new_func.strip() == span.text.strip():
        return None
    return replace_function(file_source, func_name, new_func)
