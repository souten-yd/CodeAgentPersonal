#!/usr/bin/env python3
"""ui_next スモークテスト (Playwright)。

起動中の実サーバー (既定 http://127.0.0.1:8000) の /ui-next/ を開き、
6 モードすべてを遷移してルート要素の表示とコンソールエラー無しを確認する。
スクリーンショットを artifacts/playwright/ui_next/ に保存する。

usage: python scripts/smoke_ui_next_playwright.py [--base-url URL]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts" / "playwright" / "ui_next"

# mode -> そのモードで可視化されるべき代表ルート要素
MODE_ROOTS = {
    "chat": "#chat-col",
    "atlas": "#atlas-claude-col, #atlas-col, #atlas-panel-col",
    "echo": "#chat-col, #echo-col",
    "nexus": "#nexus-col",
    "forge": "#forge-col",
    "portal": "#portal-col",
}

# レガシー由来の既知の無害エラーを除外するフィルタ
IGNORED_CONSOLE_PATTERNS = [
    "favicon",           # favicon 404
    "the server responded with a status of 404",  # 任意リソース404 (fontsなど環境依存)
    "err_internet_disconnected",
    "err_name_not_resolved",  # CDN 不達 (オフライン環境)
    "the server responded with a status of 503",  # TTS等のバックエンド未起動 (UI起因ではない)
]


def _is_ignored(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in IGNORED_CONSOLE_PATTERNS)


async def run(base_url: str) -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    failures: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        page.on(
            "console",
            lambda msg: errors.append(msg.text)
            if msg.type == "error" and not _is_ignored(msg.text)
            else None,
        )
        page.on("pageerror", lambda err: errors.append(f"pageerror: {err}"))

        await page.goto(f"{base_url}/ui-next/", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)

        # シェル要素の存在
        for sel in ["#side-nav", ".main-col", "header.topbar", "#btn-chat", "#settings-btn"]:
            if await page.locator(sel).count() == 0:
                failures.append(f"shell element missing: {sel}")

        # テーマが aurora として適用されているか
        theme = await page.evaluate("document.documentElement.getAttribute('data-theme')")
        if theme != "aurora":
            failures.append(f"default theme mismatch: {theme!r} (expected 'aurora')")

        for mode, roots in MODE_ROOTS.items():
            await page.click(f"#btn-{mode}")
            await page.wait_for_timeout(1200)
            active = await page.evaluate(
                f"document.getElementById('btn-{mode}').classList.contains('active')"
            )
            if not active:
                failures.append(f"mode {mode}: nav button did not become active")
            visible_any = False
            for root_sel in [s.strip() for s in roots.split(",")]:
                loc = page.locator(root_sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    visible_any = True
                    break
            if not visible_any:
                failures.append(f"mode {mode}: no visible root among {roots}")
            await page.screenshot(path=str(ARTIFACT_DIR / f"mode_{mode}.png"))

        # 設定モーダル開閉
        await page.click("#settings-btn")
        await page.wait_for_timeout(800)
        modal_visible = await page.locator("#settings-modal").is_visible()
        if not modal_visible:
            failures.append("settings modal did not open")
        await page.screenshot(path=str(ARTIFACT_DIR / "settings_modal.png"))
        await page.keyboard.press("Escape")

        # モバイルビューポート
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.wait_for_timeout(600)
        await page.screenshot(path=str(ARTIFACT_DIR / "mobile_chat.png"))

        await browser.close()

    for e in errors:
        failures.append(f"console error: {e}")

    if failures:
        print("SMOKE FAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SMOKE OK: all modes rendered without console errors. screenshots -> {ARTIFACT_DIR}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    return asyncio.run(run(args.base_url.rstrip("/")))


if __name__ == "__main__":
    sys.exit(main())
