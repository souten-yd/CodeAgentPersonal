#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from pathlib import Path
import os

from check_ui_inline_script_syntax import main as check_ui_syntax_main
try:
  from playwright.async_api import async_playwright
except Exception:  # pragma: no cover - optional dependency
  async_playwright = None


ROOT = Path(__file__).resolve().parents[1]
UI_FILE_URL = ROOT.joinpath("ui.html").resolve().as_uri()
UI_TARGET_URL = os.environ.get("UI_TEST_URL", "").strip() or UI_FILE_URL

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
  await page.click("#btn-atlas")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('atlas-workbench-card') && getComputedStyle(document.getElementById('atlas-workbench-card')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('agent-col') && getComputedStyle(document.getElementById('agent-col')).display === 'none'")
  await page.wait_for_function("() => document.getElementById('agent-panel-col') && getComputedStyle(document.getElementById('agent-panel-col')).display === 'none'")
  assert await page.locator("#atlas-panel-col", has_text="Atlas Workbench").count() > 0
  assert await page.locator("#atlas-workbench-card").count() > 0
  assert await page.get_by_role("button", name="Start Atlas").count() > 0
  await page.click("[data-atlas-subview-tab='legacy']")
  assert await page.get_by_role("button", name="Open Legacy Task").count() > 0
  assert await page.get_by_role("button", name="Load Recent Atlas Runs").count() > 0

  await page.click("#btn-agent")
  await page.wait_for_function("() => document.getElementById('agent-col') && getComputedStyle(document.getElementById('agent-col')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('agent-panel-col') && getComputedStyle(document.getElementById('agent-panel-col')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display === 'none'")
  agent_chat_visible = await page.evaluate("() => getComputedStyle(document.getElementById('mob-agent-chat')).display !== 'none'")
  agent_tasks_visible = await page.evaluate("() => getComputedStyle(document.getElementById('mob-agent-tasks')).display !== 'none'")
  assert agent_chat_visible and agent_tasks_visible

  await page.click("#btn-chat")
  await page.wait_for_function("() => document.getElementById('chat-col') && getComputedStyle(document.getElementById('chat-col')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display === 'none'")
  await page.wait_for_function("() => document.getElementById('agent-col') && getComputedStyle(document.getElementById('agent-col')).display === 'none'")
  await page.wait_for_function("() => document.getElementById('agent-panel-col') && getComputedStyle(document.getElementById('agent-panel-col')).display === 'none'")
  assert await page.locator("#chat-role-note", has_text="Chat is for lightweight conversation").count() > 0
  assert await page.locator("#chat-role-note", has_text="Use Atlas for guided work planning").count() > 0

  await page.click("#btn-atlas")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display !== 'none'")

  await page.click("#btn-echo")
  await page.wait_for_function("() => document.getElementById('echo-col') && getComputedStyle(document.getElementById('echo-col')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display === 'none'")

  await page.click("#btn-nexus")
  await page.wait_for_function("() => document.getElementById('nexus-col') && getComputedStyle(document.getElementById('nexus-col')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display === 'none'")




async def verify_atlas_start_button_feedback(page) -> None:
  errors: list[str] = []
  page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
  page.on("console", lambda m: errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)

  await page.click("#btn-chat")
  await page.fill("#input", "")
  await page.click("#btn-atlas")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display !== 'none'")
  await page.click("#atlas-workbench-card [data-atlas-subview-tab='overview']")
  await page.wait_for_selector('#atlas-requirement-input')
  assert await page.locator('#atlas-requirement-input').count() > 0
  await page.fill('#atlas-requirement-input', '')
  await page.click("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn")
  await page.wait_for_function("""() => {
    const root = document.getElementById('atlas-workbench-card');
    return !!root && root.dataset.atlasCurrentSubview === 'plan';
  }""")
  await page.wait_for_function("""() => {
    const logs = Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || ''));
    return logs.some((t) => t.includes('Atlas Start needs a request.'));
  }""")
  assert await page.locator('#atlas-workbench-card', has_text='Atlas Guided Plan Flow').count() > 0
  await page.fill('#atlas-requirement-input', 'Short Atlas requirement for smoke test')
  await page.wait_for_function("() => (document.getElementById('atlas-requirement-char-count')?.textContent || '').includes('chars')")

  await page.click('#btn-chat')
  await page.fill('#input', 'chat survives clear')
  await page.click('#btn-atlas')
  await page.wait_for_selector('#atlas-requirement-input')
  assert await page.input_value('#atlas-requirement-input') == 'Short Atlas requirement for smoke test'

  await page.click('#atlas-requirement-clear-btn')
  assert await page.input_value('#atlas-requirement-input') == ''
  assert await page.input_value('#input') == 'chat survives clear'

  await page.fill('#input', 'Copied from chat smoke')
  await page.click('#atlas-requirement-use-chat-btn')
  assert await page.input_value('#atlas-requirement-input') == 'Copied from chat smoke'

  await page.click("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn")
  await page.wait_for_function("""() => {
    const root = document.getElementById('atlas-workbench-card');
    return !!root && root.dataset.atlasCurrentSubview === 'plan';
  }""")
  await page.wait_for_function("""() => {
    const logs = Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || ''));
    const status = (document.getElementById('atlas-requirement-status')?.textContent || '');
    const chatValue = (document.getElementById('input')?.value || '');
    return (
      (logs.some((t) => t.includes('Using Atlas requirement input.'))
        || status.includes('Using Atlas requirement input.')
        || logs.some((t) => t.includes('Starting Atlas guided planning workflow...')))
      && chatValue === 'Short Atlas requirement for smoke test'
      && !logs.some((t) => t.includes('Atlas Start failed:'))
    );
  }""")

  await page.click('#atlas-requirement-clear-btn')
  await page.fill('#input', 'Chat fallback smoke')
  await page.click("#atlas-workbench-card [data-atlas-subview-tab='overview']")
  await page.click("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn")
  await page.wait_for_function("""() => {
    const logs = Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || ''));
    const status = (document.getElementById('atlas-requirement-status')?.textContent || '');
    const chatValue = (document.getElementById('input')?.value || '');
    const atlasValue = (document.getElementById('atlas-requirement-input')?.value || '');
    return (
      (logs.some((t) => t.includes('Falling back to Chat input.')) || status.includes('Falling back to Chat input.'))
      && chatValue === 'Chat fallback smoke'
      && atlasValue === ''
      && !logs.some((t) => t.includes('Atlas Start failed:'))
    );
  }""")

  await page.click('#atlas-requirement-clear-btn')
  await page.fill('#input', '')
  await page.click("#atlas-workbench-card [data-atlas-subview-tab='overview']")
  await page.click("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn")
  await page.wait_for_function("""() => {
    const logs = Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || ''));
    const status = (document.getElementById('atlas-requirement-status')?.textContent || '');
    return (
      logs.some((t) => t.includes('Atlas Start needs a request.'))
      || status.includes('Enter a requirement to start.')
    );
  }""")
  assert not any('ReferenceError' in e for e in errors), f"atlas start smoke found reference errors: {errors}"
  assert not errors, f"atlas start smoke found errors: {errors}"

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

async def verify_mode_specific_subtabs(page) -> None:
  async def is_visible(tab_id: str) -> bool:
    return await page.evaluate(
      "(id) => { const el = document.getElementById(id); return !!el && getComputedStyle(el).display !== 'none'; }",
      tab_id,
    )

  await page.click("#btn-chat")
  for tab_id in ["mob-chat", "mob-files", "mob-log", "mob-skills", "mob-memory", "mob-models"]:
    assert await is_visible(tab_id), f"{tab_id} should be visible in chat mode"
  for tab_id in ["mob-agent-chat", "mob-agent-tasks", "mob-atlas", "mob-echo", "mob-vault", "mob-log-echo", "mob-models-echo", "mob-asr", "mob-tts", "mob-nexus"]:
    assert not await is_visible(tab_id), f"{tab_id} should be hidden in chat mode"

  await page.click("#btn-atlas")
  assert await is_visible("mob-atlas"), "mob-atlas should be visible in atlas mode"
  for tab_id in ["mob-chat", "mob-files", "mob-log", "mob-skills", "mob-memory", "mob-models", "mob-agent-chat", "mob-agent-tasks", "mob-echo", "mob-vault", "mob-log-echo", "mob-models-echo", "mob-asr", "mob-tts", "mob-nexus"]:
    assert not await is_visible(tab_id), f"{tab_id} should be hidden in atlas mode"

  await page.click("#btn-agent")
  for tab_id in ["mob-agent-chat", "mob-agent-tasks"]:
    assert await is_visible(tab_id), f"{tab_id} should be visible in agent mode"
  for tab_id in ["mob-chat", "mob-files", "mob-log", "mob-skills", "mob-memory", "mob-models", "mob-atlas", "mob-echo", "mob-vault", "mob-log-echo", "mob-models-echo", "mob-asr", "mob-tts", "mob-nexus"]:
    assert not await is_visible(tab_id), f"{tab_id} should be hidden in agent mode"

  await page.click("#btn-echo")
  for tab_id in ["mob-echo", "mob-vault", "mob-log-echo", "mob-models-echo", "mob-asr", "mob-tts"]:
    assert await is_visible(tab_id), f"{tab_id} should be visible in echo mode"
  for tab_id in ["mob-chat", "mob-files", "mob-log", "mob-skills", "mob-memory", "mob-models", "mob-agent-chat", "mob-agent-tasks", "mob-atlas", "mob-nexus"]:
    assert not await is_visible(tab_id), f"{tab_id} should be hidden in echo mode"

  await page.click("#btn-nexus")
  assert await is_visible("mob-nexus"), "mob-nexus should be visible in nexus mode"
  for tab_id in ["mob-chat", "mob-files", "mob-log", "mob-skills", "mob-memory", "mob-models", "mob-agent-chat", "mob-agent-tasks", "mob-atlas", "mob-echo", "mob-vault", "mob-log-echo", "mob-models-echo", "mob-asr", "mob-tts"]:
    assert not await is_visible(tab_id), f"{tab_id} should be hidden in nexus mode"


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

  await page.goto(UI_TARGET_URL)
  await page.wait_for_load_state("domcontentloaded")

  await page.click("#btn-chat")
  await page.wait_for_function(
    "() => !document.body.classList.contains('mode-agent') && !document.getElementById('chat-col')?.classList.contains('mob-hidden')"
  )

  await page.click("#btn-atlas")
  await page.wait_for_function(
    "() => document.getElementById('atlas-panel-col') && !document.getElementById('atlas-panel-col').classList.contains('mob-hidden')"
  )
  await page.wait_for_function(
    "() => document.getElementById('atlas-workbench-card') && getComputedStyle(document.getElementById('atlas-workbench-card')).display !== 'none'"
  )
  await page.wait_for_function(
    "() => document.getElementById('mob-atlas')?.classList.contains('active')"
  )
  await page.wait_for_function("() => document.getElementById('agent-panel-col')?.classList.contains('mob-hidden')")
  await page.wait_for_function("() => document.getElementById('agent-col')?.classList.contains('mob-hidden')")

  await page.click("#btn-agent")
  await page.wait_for_function(
    "() => document.getElementById('agent-col') && !document.getElementById('agent-col').classList.contains('mob-hidden')"
  )
  await page.wait_for_function("() => document.getElementById('mob-agent-chat')?.classList.contains('active')")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col')?.classList.contains('mob-hidden')")
  agent_tasks_visible = await page.evaluate("() => getComputedStyle(document.getElementById('mob-agent-tasks')).display !== 'none'")
  assert agent_tasks_visible

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
  nexus_visible = await page.evaluate("() => getComputedStyle(document.getElementById('mob-nexus')).display !== 'none'")
  echo_tts_visible = await page.evaluate("() => getComputedStyle(document.getElementById('mob-tts')).display !== 'none'")
  agent_chat_visible = await page.evaluate("() => getComputedStyle(document.getElementById('mob-agent-chat')).display !== 'none'")
  assert nexus_visible and not echo_tts_visible and not agent_chat_visible

  if errors:
    raise AssertionError("\n".join(errors))

  await page.close()



async def verify_echo_tts_minimal_ui(page) -> None:
  await page.click("#btn-echo")
  await page.click("#tab-btn-tts")
  await page.wait_for_selector("#tab-tts")
  must_exist = ["Echo ASR Language", "Echo Output Language", "Echo TTS Language", "TTS Model", "Speaker", "Style", "Speed / Length"]
  for label in must_exist:
    assert await page.locator(f"text={label}").count() > 0, f"missing: {label}"
  forbidden = [
    "TTS Engine",
    "Use TTS Translation",
    "Extra Text Process Options",
    "JP Extra Text Process Options",
    "JP Extra Non Japanese Policy",
    "TTS エンジン",
  ]
  for label in forbidden:
    assert await page.locator(f"text={label}").count() == 0, f"forbidden visible: {label}"
  for forbidden_id in ["echo-tts-use-translation", "echo-tts-preview-use-translation"]:
    assert await page.locator(f"#{forbidden_id}").count() == 0, f"forbidden id exists: {forbidden_id}"
  await page.locator("#tab-tts details summary", has_text="Advanced parameters").click()
  assert await page.locator("#echo-tts-sbv2-style-weight").is_visible()

async def verify_chat_search_and_agent_web_tool_tts(page) -> None:
  await page.evaluate(
    """
    () => {
      const makeJsonResponse = (payload, status = 200) =>
        new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json' } });

      window.__mockFetchCalls = [];
      window.__mockSearchSubmitBodies = [];
      window.__mockTtsCalls = [];
      window.__agentToolLogLines = [];
      window.__mockPollCount = 0;

      const originalPlayTTS = window.playTTS;
      window.playTTS = (text, sourceMode = 'chat', extraOpts = {}) => {
        window.__mockTtsCalls.push({ text: String(text || ''), sourceMode, enabled: window._isAutoSpeakEnabled(sourceMode) });
        return originalPlayTTS ? originalPlayTTS(text, sourceMode, extraOpts) : true;
      };

      window.fetch = async (input, init = {}) => {
        const url = String(typeof input === 'string' ? input : (input?.url || ''));
        const method = String(init?.method || 'GET').toUpperCase();
        const bodyText = typeof init?.body === 'string' ? init.body : '';
        window.__mockFetchCalls.push({ url, method, body: bodyText });

        if (url.endsWith('/settings')) {
          return makeJsonResponse({
            search_enabled: 'true',
            search_num: '5',
            max_steps: '20',
            llm_url: '',
          });
        }
        if (url.includes('/jobs/submit')) {
          try {
            const parsed = JSON.parse(bodyText || '{}');
            window.__mockSearchSubmitBodies.push(parsed);
          } catch (_) {}
          return makeJsonResponse({ job_id: 'job-smoke-1' });
        }
        if (url.includes('/jobs/job-smoke-1/poll')) {
          window.__mockPollCount += 1;
          if (window.__mockPollCount >= 1) {
            return makeJsonResponse({
              status: 'done',
              steps: [{ seq: 1, type: 'done', data: { result: 'chat done via search-enabled flow' } }],
            });
          }
        }
        if (url.includes('/agent/start')) {
          return makeJsonResponse({ status: 'started', session_id: 'agent-smoke-session' });
        }
        if (url.includes('/agent/tasks')) {
          return makeJsonResponse({ tasks: [] });
        }
        if (url.includes('/agent/turn')) {
          return makeJsonResponse({
            status: 'ok',
            conversation: {
              reply: 'agent final answer',
              logs: [
                { step: 1, selected_tool: 'nexus_web_search', tool_arguments: { topic: 'latest ai regulation' }, tool_result_summary: 'ok' },
              ],
            },
            execution: {
              status: 'done',
              events: [{ type: 'done', data: { final_text: 'agent final answer' } }],
              executed: [{ task_id: 'task-1', title: 'web evidence check', status: 'done', output: 'used nexus_web_search' }],
            },
          });
        }
        return makeJsonResponse({});
      };
    }
    """
  )

  await page.click("#btn-chat")
  await page.evaluate(
    """
    async () => {
      const chk = document.getElementById('search-chk');
      if (chk) chk.checked = true;
      window.searchEnabled = true;
      await window.sendMessage('latest AI regulation updates');
    }
    """
  )
  chat_search_checks = await page.evaluate(
    """
    () => {
      const calls = window.__mockFetchCalls || [];
      const submitBodies = window.__mockSearchSubmitBodies || [];
      const directNexusSearchCalled = calls.some((c) => String(c.url || '').includes('/nexus/web/search'));
      const commonSearchFlowCalled = submitBodies.some((body) => body && body.mode === 'chat' && body.search_enabled === true);
      return { directNexusSearchCalled, commonSearchFlowCalled };
    }
    """
  )
  assert (
    chat_search_checks.get("directNexusSearchCalled") or chat_search_checks.get("commonSearchFlowCalled")
  ), chat_search_checks

  await page.click("#btn-agent")
  await page.evaluate("() => { window.toggleAgentTts(true); }")
  await page.fill("#agent-input", "check latest policy changes")
  await page.click("#agent-send-btn")
  await page.wait_for_function("() => (window.__mockTtsCalls || []).filter(c => c.sourceMode === 'agent').length >= 1")

  agent_on_checks = await page.evaluate(
    """
    () => {
      const toolLogLines = Array.from(document.querySelectorAll('#log-output .log-line .lmsg')).map((el) => el.textContent || '');
      const hasNexusTool = toolLogLines.some((line) => line.includes('selected_tool=nexus_web_search'));
      const agentTtsCalls = (window.__mockTtsCalls || []).filter((c) => c.sourceMode === 'agent');
      const spokenTexts = agentTtsCalls.map((c) => String(c.text || ''));
      const spokeFinalAnswer = spokenTexts.includes('agent final answer');
      const spokeToolLog = spokenTexts.some((text) => text.includes('selected_tool=nexus_web_search'));
      return { hasNexusTool, ttsCount: agentTtsCalls.length, spokeFinalAnswer, spokeToolLog };
    }
    """
  )
  assert agent_on_checks.get("hasNexusTool"), agent_on_checks
  assert agent_on_checks.get("ttsCount") == 1, agent_on_checks
  assert agent_on_checks.get("spokeFinalAnswer"), agent_on_checks
  assert not agent_on_checks.get("spokeToolLog"), agent_on_checks

  await page.evaluate("() => { window.__mockTtsCalls = []; window.toggleAgentTts(false); }")
  await page.fill("#agent-input", "run again with tts off")
  await page.click("#agent-send-btn")
  await page.wait_for_timeout(300)
  agent_off_tts_count = await page.evaluate(
    "() => (window.__mockTtsCalls || []).filter((c) => c.sourceMode === 'agent').length"
  )
  assert agent_off_tts_count == 0, agent_off_tts_count


async def main() -> None:
  if async_playwright is None:
    print("SKIP: playwright is not installed")
    return
  syntax_rc = check_ui_syntax_main()
  if syntax_rc != 0:
    raise AssertionError(f"ui inline script syntax check failed: rc={syntax_rc}")

  async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page(viewport={"width": 1440, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("console", lambda m: errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)

    await page.goto(UI_TARGET_URL)
    await page.wait_for_load_state("domcontentloaded")

    set_mode_type = await page.evaluate("() => typeof window.setMode")
    switch_tab_type = await page.evaluate("() => typeof window.switchNexusTab")
    assert set_mode_type == "function", f"window.setMode is {set_mode_type}"
    assert switch_tab_type == "function", f"window.switchNexusTab is {switch_tab_type}"

    await verify_mode_switches(page)
    await verify_atlas_start_button_feedback(page)
    await verify_mode_specific_subtabs(page)
    await verify_nexus_tabs(page)
    await verify_reference_card_actions(page)
    await verify_chat_search_and_agent_web_tool_tts(page)

    if errors:
      raise AssertionError("\n".join(errors))

    await page.close()
    await verify_mobile_mode_switches(browser)
    await browser.close()

  print("OK: smoke_ui_modes_playwright passed (desktop + mobile)")


if __name__ == "__main__":
  asyncio.run(main())
