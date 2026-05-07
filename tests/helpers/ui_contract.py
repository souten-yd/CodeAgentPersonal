from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UI_HTML = ROOT / "ui.html"
WEB_ROOT = ROOT / "web"
WEB_CSS_ROOT = WEB_ROOT / "css"
WEB_JS_ROOT = WEB_ROOT / "js"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _iter_static_asset_paths(root: Path, pattern: str) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.glob(pattern) if path.is_file())


def load_root_ui_html_text() -> str:
    """Load only the repository-root ``ui.html`` file."""
    return _read_text(UI_HTML)


def load_ui_contract_text(*, include_static_assets: bool = True) -> str:
    """Load the text used by UI contract tests.

    The contract source includes the root ``ui.html`` file plus static assets
    under ``web/css/**/*.css`` and ``web/js/**/*.js`` by default so tests keep
    finding UI strings after CSS/JS are split out of the root HTML.  Set
    ``include_static_assets`` to ``False`` or call ``load_root_ui_html_text``
    when a test needs to inspect only ``ui.html``.
    """
    parts = [load_root_ui_html_text()]
    if include_static_assets:
        for path in _iter_static_asset_paths(WEB_CSS_ROOT, "**/*.css"):
            parts.append(_read_text(path))
        for path in _iter_static_asset_paths(WEB_JS_ROOT, "**/*.js"):
            parts.append(_read_text(path))
    return "\n".join(parts)
