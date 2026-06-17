"""Automated cause discovery — turn a test failure into "which product code produced this, and what it
requires", without a frontier model.

This automates the detective work a human (or a frontier model) does by hand when a fix peels back one
failure and reveals the next: read the new failure, find where in the PRODUCT code that signal comes
from, read the surrounding check to learn what would satisfy it, repeat. The key insight that makes it
frontier-free: a runtime failure signal — a warning token like ``patch_content_missing``, an exception
message, an asserted-but-missing value — is a LITERAL STRING in the source, so locating its origin is
DETERMINISTIC (grep / the Twin's code index). The only step that needs judgment is reading the small
located snippet to say what condition satisfies the gate, and that is a bounded, local call for the weak
LLM (with a deterministic fallback that just reports the origin).

Pieces:
- ``extract_failure_signals`` — deterministic: pull the discriminating tokens from a failure (warning
  identifiers, the exception class/key, the expected-vs-actual mismatch).
- ``locate_in_source`` — deterministic: find where a signal literal is produced in the product code
  (excludes tests), with a few lines of context.
- ``explain_requirement`` — weak LLM (optional): read the located check and state what satisfies it;
  falls back to "see origin" with no model.
- ``diagnose`` — compose the three into a ranked list of ``Diagnosis`` for one failure.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional


@dataclass
class CauseSignal:
    kind: str            # "warning" | "exception" | "missing_value" | "mismatch"
    token: str           # the literal discriminating string to locate in source
    detail: str = ""


# warning/identifier tokens (snake_case words), exception classes, quoted literals
_WARNING_LIST_RE = re.compile(r"warnings['\"]?\s*[:=]\s*\[([^\]]*)\]", re.I)
_IN_WARNINGS_RE = re.compile(r"['\"]([a-z][a-z0-9_]+)['\"]\s+in\s+[^\n]*warnings", re.I)
_EXC_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b(?::\s*'?([^'\n]{0,60})'?)?")
_KEYERR_RE = re.compile(r"KeyError:\s*'([^']+)'")
_MISMATCH_RE = re.compile(r"assert\s+'([^']*)'\s*==\s*'([^']*)'")


def extract_failure_signals(failure_text: str) -> list[CauseSignal]:
    """Deterministically pull the locatable signals from a failure: warning identifiers, the exception
    class / missing key, and the actual!=expected value of an equality assertion (the actual value is
    what the code produced — the thing to trace)."""
    text = str(failure_text or "")
    signals: list[CauseSignal] = []
    seen: set[tuple] = set()

    def _add(kind: str, token: str, detail: str = "") -> None:
        token = token.strip()
        if token and (kind, token) not in seen:
            seen.add((kind, token))
            signals.append(CauseSignal(kind, token, detail))

    for m in _WARNING_LIST_RE.finditer(text):
        for w in re.findall(r"['\"]([a-z][a-z0-9_]+)['\"]", m.group(1)):
            _add("warning", w, "from a warnings list")
    for m in _IN_WARNINGS_RE.finditer(text):
        _add("warning", m.group(1), "asserted to be in warnings")
    for m in _KEYERR_RE.finditer(text):
        _add("exception", m.group(1), "missing key")
    for m in _MISMATCH_RE.finditer(text):
        actual, expected = m.group(1), m.group(2)
        # the ACTUAL value is what the code produced — trace it to learn why
        _add("mismatch", actual, f"actual value (expected '{expected}')")
    for m in _EXC_RE.finditer(text):
        # AssertionError detail is the assert expression — handled by _MISMATCH_RE, skip here as noise.
        if m.group(2) and m.group(1) != "AssertionError" and not m.group(2).lstrip().startswith("assert"):
            _add("exception", m.group(2), f"{m.group(1)} detail")
    return signals


@dataclass
class CauseOrigin:
    token: str
    file: str
    line: int
    snippet: str


def _iter_source_files(repo_root: str, include: Iterable[str], exclude_dirs: Iterable[str]):
    root = Path(repo_root)
    excl = tuple(exclude_dirs)
    for prefix in include:
        base = root / prefix
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            rel = p.relative_to(root).as_posix()
            if any(seg in rel for seg in excl):
                continue
            yield p, rel


def locate_in_source(
    token: str,
    *,
    repo_root: str = ".",
    include: Iterable[str] = ("app/", "agent/"),
    exclude_dirs: Iterable[str] = ("/tests/", "test_", "__pycache__", "venv", "ca_data"),
    context: int = 3,
    max_hits: int = 8,
) -> list[CauseOrigin]:
    """Find where ``token`` literally appears in the PRODUCT source (tests excluded), with surrounding
    context. Deterministic — this is the step that needs no model (a runtime signal is a literal string
    in the code that emits it)."""
    tok = str(token or "")
    if not tok:
        return []
    origins: list[CauseOrigin] = []
    for path, rel in _iter_source_files(repo_root, include, exclude_dirs):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            if tok in line:
                lo = max(0, i - context)
                hi = min(len(lines), i + context + 1)
                origins.append(CauseOrigin(tok, rel, i + 1, "\n".join(lines[lo:hi])))
                if len(origins) >= max_hits:
                    return origins
    return origins


_TRACE_FILE_RE = re.compile(r'File "([^"]+)", line (\d+)')
_TRACE_SHORT_RE = re.compile(r'^\s*([\w./\\-]+\.py):(\d+):', re.M)
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')


def locate_from_traceback(
    traceback_text: str,
    *,
    include: Iterable[str] = ("app/", "agent/"),
    exclude_dirs: Iterable[str] = ("/tests/", "test_", "__pycache__", "venv", "ca_data"),
) -> Optional[CauseOrigin]:
    """The deepest in-project frame named by a pytest traceback — exact file:line, no grep needed.

    A failure's traceback already pins the failing product line; relying only on grepping a signal string
    leaves that on the table (it misses value/logic bugs whose symptom is not a source literal). This
    parses both ``File "...", line N`` and ``path/x.py:N:`` frames and returns the LAST one under
    ``include`` and not excluded — the product code that actually failed."""
    text = _ANSI_RE.sub("", str(traceback_text or ""))   # pytest colorizes paths; strip ANSI first
    frames = [(m.group(1), int(m.group(2))) for m in _TRACE_FILE_RE.finditer(text)]
    frames += [(m.group(1), int(m.group(2))) for m in _TRACE_SHORT_RE.finditer(text)]
    incl = tuple(p.replace("\\", "/") for p in include)
    best: Optional[CauseOrigin] = None
    for raw, line in frames:
        rel = raw.replace("\\", "/")
        if any(seg in rel for seg in exclude_dirs):
            continue
        if incl and not any(s in rel for s in incl):
            continue
        best = CauseOrigin("<traceback>", rel, line, f"{rel}:{line}")   # keep the last (deepest) frame
    return best


def localize_from_test_calls(
    test_source: str,
    *,
    repo_root: str = ".",
    include: Iterable[str] = ("app/", "agent/"),
    exclude_dirs: Iterable[str] = ("/tests/", "test_", "__pycache__", "venv", "ca_data"),
    only_test: str = "",
) -> list[CauseOrigin]:
    """The product functions a (failing) test EXERCISES, by static call analysis — for value/logic bugs
    that raise nothing, so the traceback only names the test line.

    Parses ``test_source``, collects the names it calls (``s.f()``, ``f()``), and locates each ``def
    name(`` in the product source. This is the deterministic, run-free localizer that hands a function
    name to ``code_synthesis_repair``. ``only_test`` restricts the analysis to one test function."""
    try:
        tree = ast.parse(test_source)
    except SyntaxError:
        return []
    scope = tree
    if only_test:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == only_test:
                scope = node
                break
    names: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if name and name not in seen and not name[0].isupper():   # skip class/constructor calls
                seen.add(name)
                names.append(name)
    origins: list[CauseOrigin] = []
    def_re = {n: re.compile(rf"^\s*(?:async\s+)?def\s+{re.escape(n)}\s*\(") for n in names}
    for path, rel in _iter_source_files(repo_root, include, exclude_dirs):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            for n in names:
                if def_re[n].match(line):
                    origins.append(CauseOrigin(n, rel, i + 1, n))
    return origins


def _functions_covering(source: str, executed_lines: set) -> list[tuple[str, int]]:
    """Module-level functions whose body contains at least one executed line — ``[(name, lineno)]``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = range(node.lineno, (node.end_lineno or node.lineno) + 1)
            if any(ln in executed_lines for ln in span):
                out.append((node.name, node.lineno))
    return out


def localize_by_coverage(
    test_node_id: str,
    *,
    repo_root: str = ".",
    include: Iterable[str] = ("app/", "agent/"),
    exclude_dirs: Iterable[str] = ("/tests/", "test_", "__pycache__", "venv", "ca_data"),
    run_coverage_fn: Optional[Callable[[str], dict]] = None,
    read_fn: Optional[Callable[[str], str]] = None,
    max_candidates: int = 8,
) -> list[CauseOrigin]:
    """The product functions a failing test actually EXECUTES — for layered code (test → API → service →
    fn) where neither the traceback nor the test's static calls reach the buggy function.

    Runs the one test under coverage (``run_coverage_fn(node) -> {abs_file: {lines}}``), maps executed
    lines to the enclosing functions, and returns them ranked fewest-executed-lines first (a specific leaf
    is a likelier bug site than a broad orchestrator). Heavier than the static localizer, so it is the
    ESCALATION step — used only on failures the cheap path could not fix. Injectable for tests; the
    default runs ``coverage`` in a subprocess."""
    runner = run_coverage_fn or (lambda nid: _default_coverage(nid, repo_root))
    read = read_fn or (lambda p: (Path(repo_root) / p).read_text(encoding="utf-8", errors="replace"))
    try:
        executed = runner(test_node_id) or {}
    except Exception:
        return []
    incl = tuple(p.replace("\\", "/") for p in include)
    cands: list[tuple[int, CauseOrigin]] = []
    for abs_file, lines in executed.items():
        rel = str(abs_file).replace("\\", "/")
        if repo_root not in ("", ".") and rel.startswith(str(Path(repo_root).as_posix())):
            rel = rel[len(str(Path(repo_root).as_posix())):].lstrip("/")
        if any(seg in rel for seg in exclude_dirs):
            continue
        if incl and not any(s in rel for s in incl):
            continue
        try:
            src = read(rel)
        except Exception:
            continue
        for name, line in _functions_covering(src, set(lines)):
            cands.append((len(lines), CauseOrigin(name, rel, line, name)))
    cands.sort(key=lambda c: c[0])                 # fewest executed lines in the file first
    return [o for _n, o in cands[:max_candidates]]


def _default_coverage(test_node_id: str, repo_root: str) -> dict:
    import subprocess
    import sys
    import tempfile
    import coverage  # type: ignore
    datafile = str(Path(tempfile.gettempdir()) / f"_cov_{abs(hash(test_node_id))}.dat")
    subprocess.run([sys.executable, "-m", "coverage", "run", "--data-file", datafile,
                    "-m", "pytest", test_node_id, "-p", "no:cacheprovider", "-q"],
                   cwd=repo_root, capture_output=True, text=True)
    data = coverage.CoverageData(basename=datafile)
    data.read()
    return {f: set(data.lines(f) or []) for f in data.measured_files()}


_SYSTEM = "You read a code check that emitted a test-failure signal and state what would satisfy it."
_INSTRUCTION = (
    "A test failed with signal '{signal}'. Below is the product code that emits it. In one sentence, say "
    "what condition the code requires (e.g. which field/value must be present) so the signal would NOT "
    "fire. Return {{\"requirement\": \"<short>\", \"field\": \"<the field or value, if any>\"}}."
)


def explain_requirement(signal: CauseSignal, origins: list[CauseOrigin],
                        llm_json_fn: Optional[Callable[[str, str], Optional[dict]]] = None) -> str:
    """What satisfies the gate that emitted ``signal``. With ``llm_json_fn`` the weak LLM reads the
    located snippet (bounded, local); without it, returns a deterministic pointer to the origin."""
    if not origins:
        return f"signal '{signal.token}' not found in product source; likely a test-only or dynamic value"
    origin = origins[0]
    if llm_json_fn is None:
        return f"emitted at {origin.file}:{origin.line} — inspect the surrounding check"
    try:
        user = json.dumps({
            "task": _INSTRUCTION.format(signal=signal.token),
            "signal_kind": signal.kind,
            "origin": f"{origin.file}:{origin.line}",
            "code": origin.snippet[:1500],
        }, ensure_ascii=False)
        out = llm_json_fn(_SYSTEM, user) or {}
        req = str(out.get("requirement") or "").strip()
        field = str(out.get("field") or "").strip()
        if req:
            return f"{req}" + (f" (field: {field})" if field else "") + f" [{origin.file}:{origin.line}]"
    except Exception:
        pass
    return f"emitted at {origin.file}:{origin.line} — inspect the surrounding check"


@dataclass
class Diagnosis:
    signal: CauseSignal
    origins: list = field(default_factory=list)
    requirement: str = ""
    located: bool = False


def diagnose(
    failure_text: str,
    *,
    repo_root: str = ".",
    traceback_text: str = "",
    llm_json_fn: Optional[Callable[[str, str], Optional[dict]]] = None,
    locate_fn: Optional[Callable[[str], list]] = None,
) -> list[Diagnosis]:
    """Full cause discovery for one failure: extract signals → locate each in product source → explain
    what satisfies it. Frontier-free (deterministic locate; weak-LLM only for the local requirement
    read). ``locate_fn(token) -> [CauseOrigin]`` is injectable for tests.

    If ``traceback_text`` is given, the exact failing frame (file:line) is added as a high-priority
    ``traceback`` diagnosis — this localizes value/logic bugs that have no greppable signal string."""
    loc = locate_fn or (lambda t: locate_in_source(t, repo_root=repo_root))
    out: list[Diagnosis] = []
    tb = locate_from_traceback(traceback_text) if traceback_text else None
    if tb is not None:
        out.append(Diagnosis(signal=CauseSignal("traceback", tb.file, "failing frame"),
                             origins=[tb], located=True,
                             requirement=f"failure occurs at {tb.file}:{tb.line}"))
    for sig in extract_failure_signals(failure_text):
        origins = loc(sig.token)
        out.append(Diagnosis(
            signal=sig, origins=origins, located=bool(origins),
            requirement=explain_requirement(sig, origins, llm_json_fn)))
    # rank: located signals first, warnings/exceptions before generic mismatches
    order = {"traceback": -1, "warning": 0, "exception": 1, "missing_value": 2, "mismatch": 3}
    out.sort(key=lambda d: (not d.located, order.get(d.signal.kind, 9)))
    return out
