#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from pathlib import Path
import os
import re
import traceback
import json
import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from check_ui_inline_script_syntax import main as check_ui_syntax_main
try:
  from playwright.async_api import async_playwright
except Exception:  # pragma: no cover - optional dependency
  async_playwright = None


ROOT = Path(__file__).resolve().parents[1]
PLAYWRIGHT_ARTIFACT_DIR = ROOT / "artifacts" / "playwright"
DEFAULT_DESKTOP_VIEWPORT = {"width": 1280, "height": 900}
DEFAULT_MOBILE_VIEWPORT = {"width": 390, "height": 844}



MOCK_GET_ROUTES = {
  "/health": {"ok": True},
  "/settings": {},
  "/system/summary": {},
  "/system/usage": {},
  "/projects": {"projects": [{"name": "default"}]},
  "/llm/props": {},
  "/nexus/summary": {},
  "/models/db/status": {},
  "/models/db": {"models": []},
  "/models/roles": {},
  "/skills": [],
  "/projects/default/history": [],
  "/models/orchestration": {},
  "/projects/default/jobs": {"jobs": []},
  "/echo/sessions": [],
  "/nexus/documents": {"documents": []},
  "/nexus/jobs/active": {"jobs": []},
  "/nexus/web/status": {},
}

def _json_response(handler: BaseHTTPRequestHandler, payload, status: int = 200):
  body = json.dumps(payload).encode("utf-8")
  handler.send_response(status)
  handler.send_header("Content-Type", "application/json; charset=utf-8")
  handler.send_header("Content-Length", str(len(body)))
  handler.end_headers()
  handler.wfile.write(body)

def start_mock_server():
  ui_html = ROOT.joinpath("ui.html").read_bytes()
  class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
      return
    def do_GET(self):
      path = self.path.split("?", 1)[0]
      if path in ("/", "/ui.html"):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(ui_html)))
        self.end_headers()
        self.wfile.write(ui_html)
        return
      payload = MOCK_GET_ROUTES.get(path, {})
      _json_response(self, payload)
    def do_POST(self):
      path = self.path.split("?", 1)[0]
      if path == "/agent/start":
        return _json_response(self, {"ok": False, "message": "mock smoke backend"})
      if path == "/api/task/plan":
        return _json_response(self, {"ok": False, "error": "mock smoke backend: planner unavailable"})
      return _json_response(self, {})

  server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  return server, thread

def get_smoke_base_url():
  explicit = os.environ.get("PLAYWRIGHT_SMOKE_BASE_URL", "").strip()
  if explicit:
    return explicit.rstrip("/"), None
  server, thread = start_mock_server()
  return f"http://127.0.0.1:{server.server_port}", (server, thread)

async def get_chat_input_value(page) -> str:
  return await page.evaluate("() => document.getElementById('input')?.value || ''")

async def set_chat_input(page, text: str) -> None:
  await page.click("#btn-chat")
  input_locator = page.locator("#input")
  try:
    await input_locator.wait_for(state="visible", timeout=1500)
    await input_locator.fill(text)
    return
  except Exception:
    await page.evaluate("""([value]) => {
      const input = document.getElementById('input');
      if (!input) return;
      input.value = String(value || '');
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }""", [text])

NEXUS_TABS = [
  "dashboard",
  "library",
  "research",
  "sources",
  "evidence",
  "reports",
  "settings",
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
  await set_chat_input(page, "")
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
  await set_chat_input(page, 'chat survives clear')
  await page.click('#btn-atlas')
  await page.wait_for_selector('#atlas-requirement-input')
  assert await page.input_value('#atlas-requirement-input') == 'Short Atlas requirement for smoke test'

  await page.click('#atlas-requirement-clear-btn')
  assert await page.input_value('#atlas-requirement-input') == ''
  assert await get_chat_input_value(page) == 'chat survives clear'

  await set_chat_input(page, 'Copied from chat smoke')
  overview_panel = page.locator("#atlas-workbench-card [data-atlas-subview-panel='overview']")
  await overview_panel.wait_for(state="visible")
  use_chat_btn = overview_panel.locator('#atlas-requirement-use-chat-btn')
  await use_chat_btn.scroll_into_view_if_needed()
  await use_chat_btn.wait_for(state="visible")
  await use_chat_btn.click()
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
          );
  }""")

  await page.click('#atlas-requirement-clear-btn')
  await set_chat_input(page, 'Chat fallback smoke')
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
          );
  }""")

  await page.click('#atlas-requirement-clear-btn')
  await set_chat_input(page, '')
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


async def verify_atlas_guided_workflow_safe_journey(page) -> None:
  errors: list[str] = []
  page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
  page.on("console", lambda m: errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)

  await page.click("#btn-chat")
  await set_chat_input(page, "")
  await page.click("#btn-atlas")
  await page.wait_for_selector("#atlas-workbench-card")
  await page.click("#atlas-workbench-card [data-atlas-subview-tab='overview']")
  await page.fill("#atlas-requirement-input", "Phase 25 smoke requirement text")
  await page.click("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn")
  await page.wait_for_function("() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'plan'")
  await page.wait_for_function("""() => {
    const status = document.getElementById('atlas-requirement-status')?.textContent || '';
    const flow = document.getElementById('atlas-workbench-card-plan-flow')?.textContent || '';
    const messages = Array.from(document.querySelectorAll('#messages .msg')).map((el) => el.textContent || '').join('\\n');
    return (
      flow.includes('Requirement')
      && (
        status.includes('Starting Atlas guided planning workflow')
        || status.includes('Using Atlas requirement input')
        || status.includes('Atlas Start failed')
        || messages.includes('Starting Atlas guided planning workflow')
        || messages.includes('Atlas Workflow Status')
        || messages.includes('Atlas Start failed')
      )
    );
  }""")
  const_messages = await page.evaluate("""() => Array.from(document.querySelectorAll('#messages .msg')).map((el) => el.textContent || '').join('\\n')""")
  if "Atlas Start failed:" in const_messages:
    print("INFO: Atlas Start failed is visible in UI; accepted for backend-unavailable safe journey smoke.")
  if "Atlas Workflow Status" in const_messages:
    assert "Source: atlas" in const_messages
    assert "Workspace: Atlas" in const_messages
  await page.wait_for_function("""() => {
    const msg = Array.from(document.querySelectorAll('#messages .msg')).map((el) => el.textContent || '').join('\\n');
    const status = document.getElementById('atlas-requirement-status')?.textContent || '';
    return msg.includes('Requirement Source: atlas') || status.includes('Using Atlas requirement input.');
  }""")
  assert await page.input_value("#input") == "Phase 25 smoke requirement text"

  review_btn = page.get_by_role("button", name="Review Plan")
  if await review_btn.count() > 0:
    await review_btn.first.click()
  approval_btn = page.get_by_role("button", name="Open Approval Panel")
  if await approval_btn.count() > 0:
    await approval_btn.first.click()
  execute_btn = page.get_by_role("button", name="Open Execute Preview")
  if await execute_btn.count() > 0:
    await execute_btn.first.click()
  patch_btn = page.get_by_role("button", name="Open Patch Review")
  if await patch_btn.count() > 0:
    await patch_btn.first.click()
  else:
    await page.click("#atlas-workbench-card [data-atlas-subview-tab='patch_review']")

  await page.click("#atlas-workbench-card [data-atlas-subview-tab='runs']")
  await page.wait_for_function("() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'runs'")
  await page.click("#atlas-workbench-card [data-atlas-subview-tab='dashboard']")
  await page.wait_for_function("() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'dashboard'")
  await page.click("#atlas-workbench-card [data-atlas-subview-tab='legacy']")
  await page.wait_for_function("() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'legacy'")

  for mode in ["#btn-chat", "#btn-atlas", "#btn-echo", "#btn-nexus", "#btn-atlas"]:
    await page.click(mode)
  if errors:
    raise AssertionError("\n".join(errors))


async def verify_atlas_backend_e2e_journey(page) -> None:
  if os.environ.get("RUN_ATLAS_BACKEND_E2E", "").strip() != "1":
    print("SKIP: RUN_ATLAS_BACKEND_E2E is not set")
    return
  errors: list[str] = []
  page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
  page.on("console", lambda m: errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)

  await page.click("#btn-chat")
  await set_chat_input(page, "")
  await page.click("#btn-atlas")
  await page.wait_for_selector("#atlas-workbench-card")
  await page.click("#atlas-workbench-card [data-atlas-subview-tab='overview']")
  await page.fill("#atlas-requirement-input", "Phase 25.2 backend e2e smoke requirement")
  await page.click("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn")

  await page.wait_for_function(
    "() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'plan'",
    timeout=30_000,
  )
  await page.wait_for_function(
    "() => !!document.getElementById('atlas-workbench-card-plan-flow') && (document.getElementById('atlas-workbench-card-plan-flow')?.textContent || '').includes('Requirement')",
    timeout=30_000,
  )

  const_messages = await page.evaluate("""() => Array.from(document.querySelectorAll('#messages .msg')).map((el) => el.textContent || '').join('\\n')""")
  assert "Atlas Start failed:" not in const_messages, "backend E2E smoke must not accept Atlas Start failed"

  await page.wait_for_function("""() => {
    const status = document.getElementById('atlas-requirement-status')?.textContent || '';
    const messages = Array.from(document.querySelectorAll('#messages .msg')).map((el) => el.textContent || '').join('\\n');
    return (
      messages.includes('Atlas Workflow Status')
      || messages.includes('Requirement Source: atlas')
      || messages.includes('Source: atlas')
      || messages.includes('Workspace: Atlas')
      || status.includes('Using Atlas requirement input.')
      || status.includes('Starting Atlas guided planning workflow')
    );
  }""", timeout=45_000)
  await page.wait_for_function("""() => {
    const status = document.getElementById('atlas-requirement-status')?.textContent || '';
    const messages = Array.from(document.querySelectorAll('#messages .msg')).map((el) => el.textContent || '').join('\\n');
    return (
      status.includes('Using Atlas requirement input.')
      || messages.includes('Requirement Source: atlas')
      || messages.includes('Source: atlas')
      || messages.includes('Workspace: Atlas')
    );
  }""", timeout=45_000)
  if errors:
    raise AssertionError("\n".join(errors))

async def verify_nexus_tabs(page) -> None:
  await page.click("#btn-nexus")
  for tab in NEXUS_TABS:
    await page.click(f"#nexus-btn-{tab}")
    await page.wait_for_function(
      "(name) => document.getElementById(`nexus-btn-${name}`)?.classList.contains('active')",
      arg=tab,
    )
    await page.wait_for_function(
      "(name) => document.getElementById(`nexus-tab-${name}`)?.classList.contains('active')",
      arg=tab,
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
  web_scout_tab = page.locator("#nexus-btn-web-scout")
  if await web_scout_tab.count() > 0:
    await web_scout_tab.click()
  else:
    await page.click("#nexus-btn-sources")

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


async def verify_mobile_mode_switches(page) -> None:
  await page.set_viewport_size(DEFAULT_MOBILE_VIEWPORT)
  await page.wait_for_timeout(100)
  errors: list[str] = []
  page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
  page.on("console", lambda m: errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)


  await page.click("#btn-chat")
  await page.wait_for_function(
    "() => !document.body.classList.contains('mode-agent') && !document.getElementById('chat-col')?.classList.contains('mob-hidden') && document.getElementById('mob-chat')?.classList.contains('active')"
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


def _safe_artifact_name(name: str) -> str:
  return re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_") or "scenario"


async def run_smoke_scenario(name: str, browser, base_url: str, coro_factory, results: list[dict[str, str]], viewport: dict[str, int] | None = None) -> None:
  scenario_errors: list[str] = []
  page = await browser.new_page(viewport=viewport or DEFAULT_DESKTOP_VIEWPORT)
  page.on("pageerror", lambda e: scenario_errors.append(f"pageerror: {e}"))
  page.on("console", lambda m: scenario_errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)
  try:
    await page.goto(base_url)
    await page.wait_for_load_state("domcontentloaded")
    await coro_factory(page)
    if scenario_errors:
      raise AssertionError("\n".join(scenario_errors))
    results.append({"name": name, "status": "PASS", "error": "", "artifact": ""})
  except Exception as err:
    safe = _safe_artifact_name(name)
    err_text = f"{type(err).__name__}: {err}"
    if scenario_errors:
      err_text = err_text + "\n" + "\n".join(scenario_errors)
    log_path = PLAYWRIGHT_ARTIFACT_DIR / f"{safe}.log"
    log_path.write_text(err_text + "\n\n" + traceback.format_exc(), encoding="utf-8")
    results.append({"name": name, "status": "FAIL", "error": err_text, "artifact": str(log_path.relative_to(ROOT))})
    try:
      await page.screenshot(path=str(PLAYWRIGHT_ARTIFACT_DIR / f"{safe}.png"), full_page=True)
    except Exception:
      pass
    try:
      (PLAYWRIGHT_ARTIFACT_DIR / f"{safe}.traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
    except Exception:
      pass
  finally:
    await page.close()


def has_smoke_failures(results: list[dict[str, str]]) -> bool:
  return any(r.get("status") == "FAIL" for r in results)


def print_smoke_summary(results: list[dict[str, str]]) -> str:
  counts: dict[str, int] = {}
  for row in results:
    counts[row["status"]] = counts.get(row["status"], 0) + 1
  total = len(results)
  pass_count = counts.get("PASS", 0)
  fail_count = counts.get("FAIL", 0)

  lines = [
    "# Playwright UI Smoke Summary",
    "",
    f"- Total scenarios: **{total}**",
    f"- PASS: **{pass_count}**",
    f"- FAIL: **{fail_count}**",
    "",
    "| Scenario | Status | Error summary | Artifact |",
    "|---|---|---|---|",
  ]
  for row in results:
    scenario_name = row.get("name", "")
    escaped_name = scenario_name.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
    error = html.escape((row.get("error") or "").replace("\n", "<br>")[:500])
    lines.append(f"| {escaped_name} | {row['status']} | {error} | {row.get('artifact', '')} |")
  summary = "\n".join(lines) + "\n"
  print(summary)
  (PLAYWRIGHT_ARTIFACT_DIR / "summary.md").write_text(summary, encoding="utf-8")
  return summary



async def main() -> None:
  if async_playwright is None:
    print("SKIP: playwright is not installed.")
    print("Install with:")
    print("python -m pip install playwright")
    print("python -m playwright install chromium")
    return
  syntax_rc = check_ui_syntax_main()
  if syntax_rc != 0:
    raise AssertionError(f"ui inline script syntax check failed: rc={syntax_rc}")
  PLAYWRIGHT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

  async with async_playwright() as p:
    browser = await p.chromium.launch()
    base_url, mock_server = get_smoke_base_url()
    print(f"INFO: Playwright smoke base URL = {base_url}")
    results: list[dict[str, str]] = []
    scenarios = [
      ("bootstrap_api_contract", lambda current_page: current_page.evaluate("() => [typeof window.setMode, typeof window.switchNexusTab]")),
      ("mode_switches", verify_mode_switches),
      ("atlas_start_button_feedback", verify_atlas_start_button_feedback),
      ("atlas_guided_workflow_safe_journey", verify_atlas_guided_workflow_safe_journey),
      ("mode_specific_subtabs", verify_mode_specific_subtabs),
      ("nexus_tabs", verify_nexus_tabs),
      ("reference_card_actions", verify_reference_card_actions),
      ("chat_search_and_agent_web_tool_tts", verify_chat_search_and_agent_web_tool_tts),
    ]
    if os.environ.get("RUN_ATLAS_BACKEND_E2E", "").strip() == "1":
      scenarios.append(("atlas_backend_e2e_journey", verify_atlas_backend_e2e_journey))
    else:
      print("INFO: backend E2E scenario remains opt-in (set RUN_ATLAS_BACKEND_E2E=1 to include).")

    async def bootstrap_assertions(current_page) -> None:
      set_mode_type, switch_tab_type = await current_page.evaluate("() => [typeof window.setMode, typeof window.switchNexusTab]")
      assert set_mode_type == "function", f"window.setMode is {set_mode_type}"
      assert switch_tab_type == "function", f"window.switchNexusTab is {switch_tab_type}"
    scenarios[0] = ("bootstrap_api_contract", bootstrap_assertions)

    for scenario_name, scenario_fn in scenarios:
      await run_smoke_scenario(scenario_name, browser, base_url, scenario_fn, results, DEFAULT_DESKTOP_VIEWPORT)

    await run_smoke_scenario("mobile_mode_switches", browser, base_url, lambda page: verify_mobile_mode_switches(page), results, DEFAULT_MOBILE_VIEWPORT)
    await browser.close()
    if mock_server:
      server, thread = mock_server
      server.shutdown()
      server.server_close()
      thread.join(timeout=2)

  summary = print_smoke_summary(results)
  if has_smoke_failures(results):
    raise AssertionError(f"Playwright smoke scenarios failed.\n\n{summary}")
  print("OK: smoke_ui_modes_playwright passed with scenario aggregation")


if __name__ == "__main__":
  asyncio.run(main())
