"""Code exploration utilities: give the planner/patch-generator REAL code, not just file names.

Pillar C of the autonomous-agent roadmap. This is a small, dependency-free, read-only explorer over a
project directory. It reuses the AST/keyword patterns already proven in the repo-index adapter
but works directly on disk (no pre-built index required), so research-first and patch generation can
ground on actual source excerpts and symbols.

Everything here is best-effort and never raises: a weak local model benefits from concrete evidence,
and planning must still work when exploration finds nothing.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

_CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".json", ".md", ".txt", ".yaml", ".yml"}
_EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".mypy_cache", ".pytest_cache", "ca_data"}
_MAX_FILE_BYTES = 1_000_000


def _iter_project_files(root: Path, max_files: int = 4000):
    count = 0
    for p in root.rglob("*"):
        if count >= max_files:
            break
        if p.is_symlink() or not p.is_file():
            continue
        if any(part in _EXCLUDE_DIRS or part.startswith(".") for part in p.relative_to(root).parts[:-1]):
            continue
        if p.suffix.lower() not in _CODE_EXTS:
            continue
        count += 1
        yield p


def _safe_read(p: Path) -> str | None:
    try:
        if p.stat().st_size > _MAX_FILE_BYTES:
            return None
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None


def search_code_excerpts(project_path: str, terms: list[str], *, max_hits: int = 20, context_lines: int = 2) -> list[dict]:
    """Keyword search across the project; return real code excerpts (file:line + surrounding lines).

    Case-insensitive substring match on any term. Cheap and deterministic — a grep the LLM can rely on.
    """
    root = Path(project_path or "").expanduser()
    if not project_path or not root.is_dir():
        return []
    needles = [t.strip().lower() for t in (terms or []) if t and t.strip()]
    if not needles:
        return []
    hits: list[dict] = []
    for p in _iter_project_files(root):
        if len(hits) >= max_hits:
            break
        text = _safe_read(p)
        if text is None:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            low = line.lower()
            matched = next((n for n in needles if n in low), None)
            if matched is None:
                continue
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            excerpt = "\n".join(lines[start:end])
            hits.append({
                "file": p.relative_to(root).as_posix(),
                "line": i + 1,
                "term": matched,
                "excerpt": excerpt[:600],
            })
            if len(hits) >= max_hits:
                break
    return hits


def extract_symbols(project_path: str, *, target_files: list[str] | None = None, max_symbols: int = 60) -> list[dict]:
    """Extract function/class symbols (AST for Python, regex for JS/TS) from target files or the project.

    Returns [{file, name, kind, line, signature, docstring}]. If target_files is given, only those are
    scanned (useful for grounding a patch on the file being edited); otherwise the whole project.
    """
    root = Path(project_path or "").expanduser()
    if not project_path or not root.is_dir():
        return []
    if target_files:
        paths = []
        for rel in target_files:
            rp = Path(str(rel))
            if rp.is_absolute() or ".." in rp.parts:
                continue
            fp = (root / rp).resolve()
            try:
                fp.relative_to(root.resolve())
            except ValueError:
                continue
            if fp.is_file():
                paths.append(fp)
    else:
        paths = list(_iter_project_files(root))
    out: list[dict] = []
    for p in paths:
        if len(out) >= max_symbols:
            break
        text = _safe_read(p)
        if text is None:
            continue
        rel = p.relative_to(root).as_posix()
        if p.suffix == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    kind = "class" if isinstance(node, ast.ClassDef) else "function"
                    sig = _python_signature(node)
                    out.append({
                        "file": rel, "name": node.name, "kind": kind, "line": node.lineno,
                        "signature": sig, "docstring": (ast.get_docstring(node) or "")[:200],
                    })
                    if len(out) >= max_symbols:
                        break
        elif p.suffix.lower() in {".js", ".ts", ".tsx", ".jsx"}:
            for m in re.finditer(r"(?:function\s+([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\()", text):
                name = next((g for g in m.groups() if g), "")
                if not name:
                    continue
                line = text.count("\n", 0, m.start()) + 1
                out.append({"file": rel, "name": name, "kind": "function", "line": line, "signature": "", "docstring": ""})
                if len(out) >= max_symbols:
                    break
    return out


def _python_signature(node) -> str:
    try:
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(getattr(b, "id", getattr(b, "attr", "")) for b in node.bases)
            return f"class {node.name}({bases})" if bases else f"class {node.name}"
        args = [a.arg for a in node.args.args]
        if node.args.vararg:
            args.append("*" + node.args.vararg.arg)
        if node.args.kwarg:
            args.append("**" + node.args.kwarg.arg)
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)})"
    except Exception:
        return getattr(node, "name", "")


def find_related_tests(project_path: str, target_files: list[str], *, max_tests: int = 10) -> list[str]:
    """Find test files whose name relates to a target file's basename (e.g. app.py -> test_app.py)."""
    root = Path(project_path or "").expanduser()
    if not project_path or not root.is_dir() or not target_files:
        return []
    stems = {Path(str(t)).stem for t in target_files if str(t).strip()}
    if not stems:
        return []
    related: list[str] = []
    for p in _iter_project_files(root):
        rel = p.relative_to(root).as_posix()
        is_test = rel.startswith("tests/") or "/test_" in rel or p.name.startswith("test_") or p.name.endswith("_test.py") or p.stem.endswith(".test")
        if not is_test:
            continue
        name = p.stem.replace("test_", "").replace(".test", "")
        if any(s and (s in name or name in s) for s in stems):
            related.append(rel)
            if len(related) >= max_tests:
                break
    return related


def build_research_evidence(project_path: str, *, query_terms: list[str], goal: str) -> dict:
    """Assemble real-code evidence for the planner: symbol overview + keyword excerpts + project layout.

    Returns a dict with compact, model-facing text. Empty/degraded when project_path is missing.
    """
    root = Path(project_path or "").expanduser()
    out: dict = {"available": False, "text": "", "symbols": [], "excerpts": [], "file_count": 0}
    if not project_path or not root.is_dir():
        return out
    terms = [t for t in (query_terms or []) if t]
    if goal:
        terms = terms + [w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", goal)][:6]
    excerpts = search_code_excerpts(str(root), terms, max_hits=12) if terms else []
    symbols = extract_symbols(str(root), max_symbols=40)
    files = list(_iter_project_files(root, max_files=200))
    out["available"] = True
    out["file_count"] = len(files)
    out["symbols"] = symbols
    out["excerpts"] = excerpts
    out["text"] = _format_evidence_text(root, files, symbols, excerpts)
    return out


def _format_evidence_text(root: Path, files: list[Path], symbols: list[dict], excerpts: list[dict]) -> str:
    lines: list[str] = []
    if files:
        sample = [f.relative_to(root).as_posix() for f in files[:40]]
        lines.append("Project files (sample):")
        lines.extend(f"- {s}" for s in sample)
    if symbols:
        lines.append("")
        lines.append("Defined symbols (file:line — signature):")
        for s in symbols[:30]:
            sig = s.get("signature") or f"{s.get('kind','')} {s.get('name','')}"
            lines.append(f"- {s['file']}:{s['line']} — {sig}")
    if excerpts:
        lines.append("")
        lines.append("Relevant code excerpts (keyword matches):")
        for e in excerpts[:10]:
            lines.append(f"# {e['file']}:{e['line']} (matched '{e['term']}')")
            lines.append(e["excerpt"])
            lines.append("")
    return "\n".join(lines)[:8000]


class ProjectIntelligenceCodeExplorerAdapter:
    """Compatibility adapter for best-effort read-only code exploration."""

    def search_code_excerpts(self, project_path: str, terms: list[str], *, max_hits: int = 20, context_lines: int = 2) -> list[dict]:
        return search_code_excerpts(project_path, terms, max_hits=max_hits, context_lines=context_lines)

    def extract_symbols(self, project_path: str, *, target_files: list[str] | None = None, max_symbols: int = 60) -> list[dict]:
        return extract_symbols(project_path, target_files=target_files, max_symbols=max_symbols)

    def find_related_tests(self, project_path: str, target_files: list[str], *, max_tests: int = 10) -> list[str]:
        return find_related_tests(project_path, target_files, max_tests=max_tests)

    def build_research_evidence(self, project_path: str, *, query_terms: list[str], goal: str) -> dict:
        return build_research_evidence(project_path, query_terms=query_terms, goal=goal)
