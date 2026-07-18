#!/usr/bin/env python3
"""ui.html から新UI (ui_next/) を生成する変換スクリプト。

設計: docs/ui_next_detailed_design.md
- レガシー UI (ui.html / web/) には一切書き込まない。
- DOM ID 契約を保存したままシェル (ヘッダ/ナビ) を新構造へ差し替える。
- インライン JS コアを ui_next/js/core.js へ抽出し、テーマ関連の最小パッチを適用する。
- 再実行可能 (冪等)。アンカーが見つからない場合は例外で失敗させ、黙って壊れた出力を作らない。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ui.html"
OUT_DIR = ROOT / "ui_next"
CORE_VERSION = "ui-next-1"

# ── 新テーマ定義 (core.js の UI_THEMES を置換する) ──────────────────────────
UI_THEMES_NEXT = """const UI_THEMES = {
  aurora: {
    label: 'Aurora',
    vars: {
      '--bg':'#0b0d13','--bg1':'#10131b','--bg2':'#161a24','--bg3':'#1f2432',
      '--border':'#262c3b','--border2':'#39415a',
      '--text':'#e7eaf3','--text2':'#8a92ad','--text3':'#535c78',
      '--accent':'#8b7cff','--accent-bg':'rgba(139,124,255,.10)','--accent-border':'rgba(139,124,255,.38)',
      '--accent-soft':'rgba(139,124,255,.14)','--accent-softer':'rgba(139,124,255,.07)','--accent-glow':'rgba(139,124,255,.40)',
      '--logo-accent':'var(--accent)','--logo-accent-strong':'#6d5bff','--logo-text':'#eef0ff',
      '--blue':'#5ea8ff','--blue-bg':'rgba(94,168,255,.12)',
      '--red':'#ff5d7e','--amber':'#f5b453'
    }
  },
  nocturne: {
    label: 'Nocturne',
    vars: {
      '--bg':'#071018','--bg1':'#0b1622','--bg2':'#101e2e','--bg3':'#17293e',
      '--border':'#21374e','--border2':'#325272',
      '--text':'#e4f0fa','--text2':'#8fa9c0','--text3':'#54708c',
      '--accent':'#3ec6ff','--accent-bg':'rgba(62,198,255,.10)','--accent-border':'rgba(62,198,255,.38)',
      '--accent-soft':'rgba(62,198,255,.14)','--accent-softer':'rgba(62,198,255,.07)','--accent-glow':'rgba(62,198,255,.38)',
      '--logo-accent':'var(--accent)','--logo-accent-strong':'#19a8e8','--logo-text':'#e9f7ff',
      '--blue':'#6ea9ff','--blue-bg':'rgba(110,169,255,.12)',
      '--red':'#ff6584','--amber':'#f0b45c'
    }
  },
  daylight: {
    label: 'Daylight',
    vars: {
      '--bg':'#f3f5fa','--bg1':'#ffffff','--bg2':'#e9edf6','--bg3':'#dfe5f2',
      '--border':'#d0d8e8','--border2':'#aab7d0',
      '--text':'#1c2333','--text2':'#4d5a75','--text3':'#8b96ad',
      '--accent':'#4f5df0','--accent-bg':'rgba(79,93,240,.09)','--accent-border':'rgba(79,93,240,.34)',
      '--accent-soft':'rgba(79,93,240,.12)','--accent-softer':'rgba(79,93,240,.06)','--accent-glow':'rgba(79,93,240,.30)',
      '--logo-accent':'var(--accent)','--logo-accent-strong':'#3948d6','--logo-text':'#232c56',
      '--blue':'#2f78e0','--blue-bg':'rgba(47,120,224,.10)',
      '--red':'#d6446b','--amber':'#b8862e'
    }
  }
};"""

THEME_OPTIONS_NEXT = (
    '          <option value="aurora">Aurora</option>\n'
    '          <option value="nocturne">Nocturne</option>\n'
    '          <option value="daylight">Daylight</option>'
)

# ── モードナビ用アイコン (feather 系 24px stroke) ────────────────────────────
_ICONS = {
    "chat": '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
    "atlas": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3"/>',
    "echo": '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>',
    "nexus": '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "forge": '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
    "portal": '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
}


def _icon(name: str) -> str:
    return (
        '<svg class="side-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        f"{_ICONS[name]}</svg>"
    )


_MODES = [
    ("chat", "Lumen", True),
    ("atlas", "Atlas", False),
    ("echo", "Echo", False),
    ("nexus", "Nexus", False),
    ("forge", "Forge", False),
    ("portal", "Portal", False),
]

_GEAR_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="3"/>'
    '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06-.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>'
)


def build_side_nav() -> str:
    buttons = []
    for mode, label, active in _MODES:
        cls = "mode-btn active" if active else "mode-btn"
        buttons.append(
            f'      <button class="{cls}" id="btn-{mode}" onclick="setMode(\'{mode}\')" title="{label}">'
            f"{_icon(mode)}<span class=\"side-label\">{label}</span></button>"
        )
    nav = "\n".join(buttons)
    return f"""<aside class="side-nav" id="side-nav" aria-label="Primary navigation">
  <div class="side-logo" aria-hidden="true">
    <svg viewBox="0 0 220 204" class="side-logo-mark"><g fill="none" stroke="url(#sideLogoGrad)" stroke-linecap="round" stroke-linejoin="round"><circle cx="110" cy="102" r="82" stroke-width="7"/><ellipse cx="107" cy="103" rx="77" ry="83" stroke-width="6" transform="rotate(-13 107 103)" opacity="0.95"/><ellipse cx="112" cy="101" rx="82" ry="71" stroke-width="6" transform="rotate(10 112 101)" opacity="0.9"/><circle cx="110" cy="102" r="46" stroke-width="6.4" opacity="0.85"/><circle cx="110" cy="102" r="24" stroke-width="6" opacity="0.8"/></g><defs><linearGradient id="sideLogoGrad" x1="30" y1="20" x2="200" y2="190" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="var(--logo-accent-strong, var(--accent))"/><stop offset="1" stop-color="var(--logo-accent, var(--accent))"/></linearGradient></defs></svg>
  </div>
  <nav class="side-modes">
{nav}
  </nav>
  <div class="side-bottom">
    <button class="hdr-icon-btn side-settings" id="settings-btn" onclick="openSettings()" title="Settings">{_GEAR_SVG}</button>
  </div>
</aside>"""


def build_topbar(logo_div: str, hdr_tail: str) -> str:
    return f"""<div class="main-col" id="main-col">
<header class="topbar">
  {logo_div}
  <div class="hdr-right">
{hdr_tail}
  </div>
</header>"""


def main() -> None:
    html = SRC.read_text(encoding="utf-8")

    # 1) インライン JS コアを抽出
    m = re.search(r"<script(?![^>]*src=)[^>]*>(.*?)</script>", html, re.S)
    if not m:
        raise SystemExit("anchor not found: inline script block")
    core = m.group(1)

    # core.js パッチ P1: UI_THEMES を新テーマへ置換
    tm = re.search(r"const UI_THEMES = \{.*?\n\};", core, re.S)
    if not tm:
        raise SystemExit("anchor not found: UI_THEMES block")
    core = core[: tm.start()] + UI_THEMES_NEXT + core[tm.end():]

    # core.js パッチ P2: テーマ保存キーをレガシーと分離
    if "const THEME_STORAGE_KEY = 'kc_theme';" not in core:
        raise SystemExit("anchor not found: THEME_STORAGE_KEY")
    core = core.replace(
        "const THEME_STORAGE_KEY = 'kc_theme';",
        "const THEME_STORAGE_KEY = 'kc_theme_next';",
    )

    # core.js パッチ P3: 既定テーマ/フォールバック/旧名マッピング
    old_normalize = "const normalized = themeName === 'daylight' ? 'kasane' : themeName;"
    if old_normalize not in core:
        raise SystemExit("anchor not found: setTheme normalize line")
    core = core.replace(
        old_normalize,
        "const _legacyThemeMap = {cyber:'aurora', midnight:'nocturne', kasane:'daylight'};\n"
        "  const normalized = _legacyThemeMap[themeName] || themeName;",
    )
    fallback = "const chosen = UI_THEMES[normalized] ? normalized : 'cyber';"
    if fallback not in core:
        raise SystemExit("anchor not found: setTheme fallback line")
    core = core.replace(
        fallback, "const chosen = UI_THEMES[normalized] ? normalized : 'aurora';"
    )
    init_default = "const saved = localStorage.getItem(THEME_STORAGE_KEY) || 'cyber';"
    if init_default not in core:
        raise SystemExit("anchor not found: initTheme default line")
    core = core.replace(
        init_default,
        "const saved = localStorage.getItem(THEME_STORAGE_KEY) || 'aurora';",
    )

    # 2) head: フォント差し替え + CSS 追加
    old_fonts = re.search(r'<link href="https://fonts\.googleapis\.com[^"]*"[^>]*>', html)
    if not old_fonts:
        raise SystemExit("anchor not found: google fonts link")
    new_fonts = (
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
        "&family=Space+Grotesk:wght@500;600;700"
        '&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">'
    )
    html = html[: old_fonts.start()] + new_fonts + html[old_fonts.end():]

    css_link = re.search(r'<link rel="stylesheet" href="/static/css/app\.css[^"]*">', html)
    if not css_link:
        raise SystemExit("anchor not found: app.css link")
    html = html[: css_link.end()] + (
        f'\n<link rel="stylesheet" href="/ui-next/css/tokens.css?v={CORE_VERSION}">'
        f'\n<link rel="stylesheet" href="/ui-next/css/next.css?v={CORE_VERSION}">'
    ) + html[css_link.end():]

    # 3) 旧ヘッダを新シェルへ置換 (ロゴと右側ステータス群は原本から回収して温存)
    h_start = html.find("<header>")
    h_end = html.find("</header>", h_start)
    if h_start < 0 or h_end < 0:
        raise SystemExit("anchor not found: legacy <header> block")
    header_block = html[h_start : h_end + len("</header>")]

    logo_m = re.search(r'<div class="logo">.*?</svg>\s*<span class="logo-text">[^<]*</span>\s*</div>', header_block, re.S)
    if not logo_m:
        raise SystemExit("anchor not found: logo div inside header")
    logo_div = logo_m.group(0)

    # 右側ステータス: mode-wrap と settings-btn を除いた要素 (model-badge / sdot / stext)
    keep = []
    for pat, name in [
        (r'<span id="model-badge".*?</span>', "model-badge"),
        (r'<div class="sdot" id="sdot"></div>', "sdot"),
        (r'<span class="stext" id="stext">[^<]*</span>', "stext"),
    ]:
        km = re.search(pat, header_block, re.S)
        if not km:
            raise SystemExit(f"anchor not found: {name} in header")
        keep.append("    " + km.group(0))
    hdr_tail = "\n".join(keep)

    html = html[:h_start] + build_side_nav() + "\n" + build_topbar(logo_div, hdr_tail) + html[h_end + len("</header>"):]

    # 4) main-col を </body> 直前で閉じる
    if "</body>" not in html:
        raise SystemExit("anchor not found: </body>")
    html = html.replace("</body>", "</div><!-- /main-col -->\n</body>", 1)

    # 5) テーマ選択肢を新テーマ名へ
    opt = re.search(
        r'\s*<option value="cyber">Cyber</option>\s*\n\s*<option value="midnight">Midnight</option>\s*\n\s*<option value="kasane">Kasane</option>',
        html,
    )
    if not opt:
        raise SystemExit("anchor not found: theme select options")
    html = html[: opt.start()] + "\n" + THEME_OPTIONS_NEXT + html[opt.end():]

    # 6) インライン script を core.js 参照へ置換
    m2 = re.search(r"<script(?![^>]*src=)[^>]*>.*?</script>", html, re.S)
    if not m2:
        raise SystemExit("anchor not found: inline script for replacement")
    html = html[: m2.start()] + f'<script src="/ui-next/js/core.js?v={CORE_VERSION}"></script>' + html[m2.end():]

    # 7) 書き出し
    (OUT_DIR / "js").mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "css").mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "js" / "core.js").write_text(core, encoding="utf-8")
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print(f"ui_next generated: index.html={len(html)} bytes, core.js={len(core)} bytes")


if __name__ == "__main__":
    main()
