#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
UI_FILE_URL = ROOT.joinpath("ui.html").resolve().as_uri()

NEXUS_TABS = [
  "dashboard",
  "library",
  "news",
  "market",
  "web-scout",
  "compare",
  "formula",
  "evidence",
  "report",
]


async def verify_mode_switches(page) -> None:
  await page.click("#btn-chat")
  await page.wait_for_function(
    "() => document.getElementById('chat-col')?.classList.contains('active')"
  )

  await page.click("#btn-agent")
  await page.wait_for_function(
    "() => document.getElementById('agent-col')?.classList.contains('active')"
  )
  await page.wait_for_function(
    "() => document.getElementById('agent-panel-col')?.classList.contains('active')"
  )

  await page.click("#btn-echo")
  await page.wait_for_function(
    "() => document.getElementById('echo-col')?.classList.contains('active')"
  )

  await page.click("#btn-nexus")
  await page.wait_for_function(
    "() => document.getElementById('nexus-col')?.classList.contains('active')"
  )


async def verify_nexus_tabs(page) -> None:
  await page.click("#btn-nexus")
  for tab in NEXUS_TABS:
    await page.click(f"#nexus-btn-{tab}")
    await page.wait_for_function(
      "(name) => document.getElementById(`nexus-btn-${name}`)?.classList.contains('active')",
      tab,
    )
    await page.wait_for_function(
      "(name) => document.getElementById(`nexus-tab-${name}`)?.classList.contains('active')",
      tab,
    )


async def verify_reference_card_actions(page) -> None:
  await page.click("#btn-nexus")
  await page.click("#nexus-btn-web-scout")

  await page.evaluate(
    """
    () => {
      window.__openedUrls = [];
      const realFetch = window.fetch.bind(window);
      window.open = (url) => {
        window.__openedUrls.push(String(url || ''));
        return null;
      };
      window.fetch = async (input, init) => {
        const url = String(typeof input === 'string' ? input : (input?.url || ''));
        if (url.includes('/nexus/sources/src-1/chunks')) {
          return {
            ok: true,
            json: async () => ({
              chunks: [{ page_start: 2, page_end: 3, chunk_id: 'doc-1:0', citation_label: '[S1]' }],
            }),
          };
        }
        return realFetch(input, init);
      };
      renderNexusDeepReferences(
        [{
          source_id: 'src-1',
          citation_label: '[S1]',
          title: 'Mock Source',
          source_type: 'web',
          status: 'downloaded',
          final_url: 'https://example.com/report',
          local_text_path: '/tmp/mock.txt',
        }],
        [{ source_id: 'src-1', quote: 'mock quote', chunk_id: 'doc-1:0', page_start: 2, page_end: 3 }],
      );
    }
    """
  )

  ref_card = page.locator("#nexus-deep-references .nexus-ref-card").first
  await ref_card.get_by_role("button", name="全文表示").click()
  await ref_card.get_by_role("button", name="該当箇所").click()
  await page.wait_for_function(
    "() => (document.querySelector('#nexus-deep-chunks-src-1')?.textContent || '').includes('chunk:doc-1:0')"
  )
  await ref_card.get_by_role("button", name="元URL").click()
  await ref_card.get_by_role("button", name="ダウンロード").click()

  opened_urls = await page.evaluate("() => window.__openedUrls || []")
  assert any("/nexus/sources/src-1/text" in url for url in opened_urls), opened_urls
  assert any("https://example.com/report" in url for url in opened_urls), opened_urls
  assert any("/nexus/sources/src-1/original" in url for url in opened_urls), opened_urls


async def verify_mobile_mode_switches(browser) -> None:
  page = await browser.new_page(viewport={"width": 390, "height": 844})
  errors: list[str] = []
  page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
  page.on("console", lambda m: errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)

  await page.goto(UI_FILE_URL)
  await page.wait_for_load_state("domcontentloaded")

  await page.click("#btn-chat")
  await page.wait_for_function(
    "() => !document.body.classList.contains('mode-agent') && !document.getElementById('chat-col')?.classList.contains('mob-hidden')"
  )

  await page.click("#btn-agent")
  await page.wait_for_function(
    "() => document.getElementById('agent-col') && !document.getElementById('agent-col').classList.contains('mob-hidden')"
  )

  await page.click("#btn-echo")
  await page.wait_for_function(
    "() => document.getElementById('echo-col') && !document.getElementById('echo-col').classList.contains('mob-hidden')"
  )

  await page.click("#btn-nexus")
  await page.wait_for_function(
    "() => document.getElementById('nexus-col') && !document.getElementById('nexus-col').classList.contains('mob-hidden')"
  )
  await page.wait_for_function(
    "() => document.getElementById('mob-nexus')?.classList.contains('active')"
  )

  if errors:
    raise AssertionError("\n".join(errors))

  await page.close()


async def main() -> None:
  async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page(viewport={"width": 1440, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)

    await page.goto(UI_FILE_URL)
    await page.wait_for_load_state("domcontentloaded")

    set_mode_type = await page.evaluate("() => typeof window.setMode")
    switch_tab_type = await page.evaluate("() => typeof window.switchNexusTab")
    assert set_mode_type == "function", f"window.setMode is {set_mode_type}"
    assert switch_tab_type == "function", f"window.switchNexusTab is {switch_tab_type}"

    await verify_mode_switches(page)
    await verify_nexus_tabs(page)
    await verify_reference_card_actions(page)

    if errors:
      raise AssertionError("\n".join(errors))

    await page.close()
    await verify_mobile_mode_switches(browser)
    await browser.close()

  print("OK: smoke_ui_modes_playwright passed (desktop + mobile)")


if __name__ == "__main__":
  asyncio.run(main())
