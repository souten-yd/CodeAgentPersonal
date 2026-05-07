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


def load_ui_contract_text(*, include_static_assets: bool = False) -> str:
    """Load the text used by UI contract tests.

    Today the UI contract source is the root ``ui.html`` file.  The optional
    static-asset path keeps this helper ready for a future split where
    ``web/css/**/*.css`` and ``web/js/**/*.js`` become part of the contract text
    without forcing each test to know where those files live.
    """
    parts = [_read_text(UI_HTML)]
    if include_static_assets:
        for path in _iter_static_asset_paths(WEB_CSS_ROOT, "**/*.css"):
            parts.append(_read_text(path))
        for path in _iter_static_asset_paths(WEB_JS_ROOT, "**/*.js"):
            parts.append(_read_text(path))
    return "\n".join(parts)
