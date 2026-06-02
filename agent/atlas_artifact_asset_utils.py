"""Shared helpers for resolving the external CSS/JS assets a local HTML artifact links to.

Both the static visual contract verifier (AtlasVisualArtifactVerifier) and the Playwright
smoke verifier (AtlasPlaywrightSmokeVerifier) need to reason about the files an entry HTML
references — generated apps routinely split logic into ``js/*.js`` and ``css/*.css`` rather
than inlining everything. Keeping the resolution logic here avoids two slightly-different
copies drifting apart.

All resolution is sandboxed to the HTML's parent directory: no absolute paths, no ``..``
traversal, no scheme/protocol-relative URLs.
"""
from __future__ import annotations

import re
from pathlib import Path

# Caps to keep combined-content scanning bounded on pathological inputs.
_MAX_ASSET_FILES = 50
_MAX_ASSET_BYTES = 200_000

_SCRIPT_TAG_RE = re.compile(r"<script\b([^>]*)>", re.IGNORECASE)
_LINK_TAG_RE = re.compile(r"<link\b([^>]*)>", re.IGNORECASE)
_SRC_ATTR_RE = re.compile(r"\bsrc\s*=\s*(['\"])(.*?)\1", re.IGNORECASE)
_HREF_ATTR_RE = re.compile(r"\bhref\s*=\s*(['\"])(.*?)\1", re.IGNORECASE)
_REL_ATTR_RE = re.compile(r"\brel\s*=\s*(['\"])(.*?)\1", re.IGNORECASE)
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def safe_child_path(root: Path, ref: str) -> Path | None:
    """Resolve ``ref`` relative to ``root``, returning None for anything outside ``root``
    or that names a scheme (http:, data:, etc.) or protocol-relative (//) URL."""
    try:
        if not ref or _SCHEME_RE.match(ref) or ref.startswith("//"):
            return None
        clean = ref.split("#", 1)[0].split("?", 1)[0]
        if not clean:
            return None
        target = (root / clean.lstrip("/")).resolve()
        target.relative_to(root.resolve())
        return target
    except Exception:  # noqa: BLE001 — any resolution error means "not a safe local child"
        return None


def linked_script_refs(html_content: str) -> list[str]:
    """Return the de-duplicated, local ``<script src=...>`` references in document order."""
    refs: list[str] = []
    for attrs in _SCRIPT_TAG_RE.findall(html_content):
        m = _SRC_ATTR_RE.search(attrs)
        if not m:
            continue
        src = m.group(2).strip()
        if src and not _SCHEME_RE.match(src) and not src.startswith("//"):
            refs.append(src)
    return list(dict.fromkeys(refs))


def linked_stylesheet_refs(html_content: str) -> list[str]:
    """Return the de-duplicated, local ``<link rel="stylesheet" href=...>`` references."""
    refs: list[str] = []
    for attrs in _LINK_TAG_RE.findall(html_content):
        rel_m = _REL_ATTR_RE.search(attrs)
        if rel_m and "stylesheet" not in rel_m.group(2).lower():
            continue
        href_m = _HREF_ATTR_RE.search(attrs)
        if not href_m:
            continue
        href = href_m.group(2).strip()
        if href and not _SCHEME_RE.match(href) and not href.startswith("//"):
            refs.append(href)
    return list(dict.fromkeys(refs))


def collect_linked_asset_text(html_path: Path, html_content: str) -> str:
    """Concatenate the text of every local CSS/JS asset the HTML links to, plus any
    sibling ``js/*.js`` / ``css/*.css`` files next to the artifact.

    Best-effort: unreadable files are skipped, reads are size-capped, and the number of
    files scanned is bounded. Returns "" when nothing local resolves.
    """
    root = html_path.parent
    targets: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path | None) -> None:
        if path is None or path in seen or not path.exists() or not path.is_file():
            return
        seen.add(path)
        targets.append(path)

    for ref in (*linked_script_refs(html_content), *linked_stylesheet_refs(html_content)):
        _add(safe_child_path(root, ref))

    for sub, pattern in (("js", "*.js"), ("css", "*.css")):
        sub_dir = root / sub
        if sub_dir.is_dir():
            for path in sorted(sub_dir.glob(pattern)):
                _add(path)

    chunks: list[str] = []
    for path in targets[:_MAX_ASSET_FILES]:
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace")[:_MAX_ASSET_BYTES])
        except Exception:  # noqa: BLE001 — a single unreadable asset must not abort scanning
            continue
    return "\n".join(chunks)
