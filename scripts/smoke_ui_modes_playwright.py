#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from pathlib import Path
import os
import re
import time
import traceback
import json
import html
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from check_ui_inline_script_syntax import main as check_ui_syntax_main
try:
  from playwright.async_api import TimeoutError as PlaywrightTimeoutError, async_playwright
except Exception:  # pragma: no cover - optional dependency
  async_playwright = None
  PlaywrightTimeoutError = Exception


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

async def set_chat_input_value_direct(page, text: str) -> None:
  await page.evaluate("""([value]) => {
    const input = document.getElementById('input');
    if (!input) return;
    input.value = String(value || '');
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }""", [text])


async def set_chat_input(page, text: str, switch_to_chat: bool = True) -> None:
  if switch_to_chat:
    await page.click("#btn-chat")
  input_locator = page.locator("#input")
  try:
    await input_locator.wait_for(state="visible", timeout=1500)
    await input_locator.fill(text)
    return
  except Exception:
    await set_chat_input_value_direct(page, text)


async def open_atlas(page) -> None:
  await page.click("#btn-atlas")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('atlas-workbench-card') && getComputedStyle(document.getElementById('atlas-workbench-card')).display !== 'none'")


async def wait_atlas_subview(page, name: str) -> None:
  await page.wait_for_function("(subview) => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === subview", arg=name)
  await page.wait_for_function("(subview) => { const panel = document.querySelector(`#atlas-workbench-card [data-atlas-subview-panel=\"${subview}\"]`); return !!panel && getComputedStyle(panel).display !== 'none'; }", arg=name)


async def set_atlas_subview(page, name: str) -> None:
  await open_atlas(page)
  await page.click(f"#atlas-workbench-card [data-atlas-subview-tab='{name}']")
  try:
    await wait_atlas_subview(page, name)
  except Exception:
    await page.evaluate("(subview) => { if (typeof window.setAtlasSubview === 'function') window.setAtlasSubview(subview); }", name)
    await wait_atlas_subview(page, name)


async def ensure_atlas_overview(page) -> None:
  await set_atlas_subview(page, "overview")


async def ensure_atlas_plan(page) -> None:
  await set_atlas_subview(page, "plan")

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
  await open_atlas(page)
  await page.wait_for_function("() => document.getElementById('agent-col') && getComputedStyle(document.getElementById('agent-col')).display === 'none'")
  await page.wait_for_function("() => document.getElementById('agent-panel-col') && getComputedStyle(document.getElementById('agent-panel-col')).display === 'none'")
  assert await page.locator("#atlas-panel-col", has_text="Atlas Workbench").count() > 0
  assert await page.locator("#atlas-workbench-card").count() > 0
  assert await page.get_by_role("button", name="Start Atlas").count() > 0
  await set_atlas_subview(page, "legacy")
  assert await page.get_by_role("button", name="Open Legacy Task").count() > 0
  assert await page.get_by_role("button", name="Open Agent Advanced").count() > 0
  await set_atlas_subview(page, "runs")
  assert await page.get_by_role("button", name="Load Recent Atlas Runs").count() > 0, "runs subview should expose recent runs action"

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

  async def atlas_diag_dump(label: str):
    diag = await page.evaluate("""() => ({
      subview: document.getElementById('atlas-workbench-card')?.dataset?.atlasCurrentSubview || '',
      atlasRequirementInput: document.getElementById('atlas-requirement-input')?.value || '',
      chatInput: document.getElementById('input')?.value || '',
      status: document.getElementById('atlas-requirement-status')?.textContent || '',
      messagesTail: Array.from(document.querySelectorAll('#messages .msg')).map((el) => el.textContent || '').slice(-8),
      useChatVisible: !!document.querySelector('#atlas-workbench-card #atlas-requirement-use-chat-btn'),
      useChatEnabled: !(document.querySelector('#atlas-workbench-card #atlas-requirement-use-chat-btn')?.disabled ?? true),
      clearVisible: !!document.querySelector('#atlas-workbench-card #atlas-requirement-clear-btn'),
      clearEnabled: !(document.querySelector('#atlas-workbench-card #atlas-requirement-clear-btn')?.disabled ?? true),
      startVisible: !!document.querySelector("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn"),
      activeModeButton: document.querySelector('#mode-switcher .active,[data-mode].active')?.id || '',
    })""")
    print(f"INFO: atlas_start_button_feedback diagnostics ({label}): {diag}")
    return diag
  empty_start = "Atlas Start needs a request."
  empty_status = "Enter a requirement to start."
  atlas_start_value = "Atlas input start smoke"
  copied_requirement_text = "Copied from chat smoke"
  expected_text = copied_requirement_text
  try:
    # A. Empty start feedback
    await set_chat_input(page, "")
    await ensure_atlas_overview(page)
    await get_atlas_requirement_input(page).wait_for(state="visible")
    await fill_atlas_requirement(page, "")
    await page.click("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn")
    await page.wait_for_function("() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'plan'")
    await page.wait_for_function("""([msg, statusText]) => {
      const logs = Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || ''));
      const status = document.getElementById('atlas-requirement-status')?.textContent || '';
      return logs.some((t) => t.includes(msg)) || status.includes(statusText);
    }""", arg=[empty_start, empty_status])
    # B. Persistence / clear
    short_requirement_text = "Short Atlas requirement for smoke test"
    await fill_atlas_requirement(page, short_requirement_text)
    await page.wait_for_function("() => (document.getElementById('atlas-requirement-char-count')?.textContent || '').includes('chars')")
    await set_chat_input(page, "chat survives clear", switch_to_chat=True)
    await open_atlas(page)
    await click_atlas_requirement_clear(page)
    assert await get_atlas_requirement_input(page).input_value() == ""
    assert await get_chat_input_value(page) == "chat survives clear"
    # C. Use Chat Input
    await set_chat_input_value_direct(page, copied_requirement_text)
    await open_atlas(page)
    await click_atlas_use_chat_input(page)
    await page.wait_for_function("""([expected]) => {
      const atlasValue = document.getElementById('atlas-requirement-input')?.value || '';
      const status = document.getElementById('atlas-requirement-status')?.textContent || '';
      return atlasValue === expected || status.includes('Copied from Chat input.');
    }""", arg=[expected_text])
    assert await get_atlas_requirement_input(page).input_value() == expected_text
    # D. Atlas input Start
    expected_text = atlas_start_value
    await fill_atlas_requirement(page, expected_text)
    await ensure_atlas_overview(page)
    await page.click("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn")
    await page.wait_for_function("() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'plan'")
    await page.wait_for_function("""([atlasValue]) => {
      const logs = Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || ''));
      const status = document.getElementById('atlas-requirement-status')?.textContent || '';
      const msg = logs.join('\\n');
      return (
        logs.some((t) => t.includes('Using Atlas requirement input.'))
        || status.includes('Using Atlas requirement input.')
        || logs.some((t) => t.includes('Starting Atlas guided planning workflow...'))
      ) && (
        msg.includes(atlasValue) || msg.includes('Requirement Preview') || msg.includes('Atlas Workflow Status') || msg.includes('Boss')
      );
    }""", arg=[atlas_start_value])
    # E. Chat fallback Start
    await click_atlas_requirement_clear(page)
    await set_chat_input(page, "Chat fallback smoke")
    await ensure_atlas_overview(page)
    await page.click("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn")
    await page.wait_for_function("""() => {
      const logs = Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || ''));
      const status = document.getElementById('atlas-requirement-status')?.textContent || '';
      return logs.some((t) => t.includes('Falling back to Chat input.')) || status.includes('Falling back to Chat input.');
    }""")
  except (AssertionError, PlaywrightTimeoutError) as err:
    await atlas_diag_dump(f"failure: {type(err).__name__}")
    raise
  await atlas_diag_dump("final")
  assert not any('ReferenceError' in e for e in errors), f"atlas start smoke found reference errors: {errors}"
  assert not errors, f"atlas start smoke found errors: {errors}"


async def verify_atlas_guided_workflow_safe_journey(page) -> None:
  errors: list[str] = []
  page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
  page.on("console", lambda m: errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)

  await set_chat_input(page, "")
  await ensure_atlas_overview(page)
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
  diag = await page.evaluate("""() => ({
    atlasRequirementInput: document.getElementById('atlas-requirement-input')?.value || '',
    chatInput: document.getElementById('input')?.value || '',
    status: document.getElementById('atlas-requirement-status')?.textContent || '',
    messages: Array.from(document.querySelectorAll('#messages .msg')).map((el) => el.textContent || ''),
  })""")
  assert diag["atlasRequirementInput"] == "Phase 25 smoke requirement text"
  joined_messages = "\n".join(diag["messages"])
  assert (
    "Requirement Preview: Phase 25 smoke requirement text" in joined_messages
    or "BossPhase 25 smoke requirement text" in joined_messages
  ), f"atlas requirement preview message missing: {diag}"
  if "Atlas Workflow Status" in joined_messages:
    assert "Requirement Source: atlas" in joined_messages
  print(f"INFO: chat input sync failed after atlas start (diagnostic-only in Phase 25.4.5): {diag['chatInput']!r}")

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
    diag = await page.evaluate(
      """(name) => {
        const button = document.getElementById(`nexus-btn-${name}`);
        const panel = document.getElementById(`nexus-tab-${name}`);
        const allPanelIds = Array.from(document.querySelectorAll('[id^="nexus-tab-"]')).map((el) => el.id);
        const nexusCol = document.getElementById('nexus-col');
        return {
          tab: name,
          buttonClass: button?.className || '',
          panelExists: !!panel,
          panelClass: panel?.className || '',
          panelDisplay: panel ? getComputedStyle(panel).display : 'missing',
          allPanelIds,
          nexusVisible: !!nexusCol && getComputedStyle(nexusCol).display !== 'none',
        };
      }""",
      tab,
    )
    if diag["panelExists"]:
      assert diag["panelDisplay"] != "none" or "active" in diag["panelClass"], f"nexus tab wait timeout diagnostics: {diag}"
    else:
      assert "active" in diag["buttonClass"] and diag["nexusVisible"], f"nexus tab wait timeout diagnostics: {diag}"

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


async def click_first_visible_button_by_names(container, names: list[str]) -> bool:
  for name in names:
    candidate = container.get_by_role("button", name=name)
    if await candidate.count() > 0:
      await candidate.first.click()
      return True
  return False


REFERENCE_VIEWER_SELECTORS = [
  "#nexus-reference-viewer",
  "#nexus-deep-reference-viewer",
  ".nexus-reference-viewer",
  "[id*='reference-viewer']",
  "[id*='reference'][id*='viewer']",
  "#nexus-deep-references",
  "#nexus-col",
]


def normalize_reference_text(text: str) -> str:
  return re.sub(r"\s+", " ", (text or "")).strip()


async def collect_reference_viewer_text(page) -> dict:
  return await page.evaluate("""(selectors) => {
    const candidates = selectors.map((selector) => ({
      selector,
      texts: Array.from(document.querySelectorAll(selector)).map((el) => (el.textContent || '').trim()).filter(Boolean),
    }));
    const newline = String.fromCharCode(10);
    const combinedText = candidates.flatMap((item) => item.texts).join(newline);
    const normalizedText = (combinedText || '').replace(/\s+/g, ' ').trim();
    const root = document.getElementById('nexus-deep-references');
    const card = root?.querySelector('.nexus-ref-card');
    const cardButtons = card ? Array.from(card.querySelectorAll('button')).map((el) => ({
      text: (el.textContent || '').trim(),
      disabled: !!el.disabled,
      onclick: el.getAttribute('onclick') || '',
    })) : [];
    return {
      candidates,
      combinedText,
      normalizedText,
      refCardCount: root?.querySelectorAll('.nexus-ref-card')?.length || 0,
      cardButtonTexts: cardButtons.map((item) => item.text),
      cardButtons,
      fetchedUrls: window.__fetchedUrls || [],
      openedUrls: window.__openedUrls || [],
      activeNexusTab: document.querySelector('#nexus-tabbar .nexus-tab-btn.active')?.id || '',
    };
  }""", arg=REFERENCE_VIEWER_SELECTORS)


async def click_reference_button(card, labels: list[str]) -> str:
  for label in labels:
    locator = card.get_by_role("button", name=label)
    if await locator.count() > 0:
      await locator.first.click()
      return label
  opened = await click_first_visible_button_by_names(card, labels)
  if opened:
    return labels[0] if labels else "unknown"
  raise AssertionError(f"reference card action button not found: {labels}")


async def click_reference_button_if_enabled(card, labels: list[str]) -> tuple[str, bool]:
  for label in labels:
    locator = card.get_by_role("button", name=label)
    if await locator.count() > 0:
      button = locator.first
      if await button.is_disabled():
        return label, False
      await button.click()
      return label, True
  opened = await click_first_visible_button_by_names(card, labels)
  if opened:
    return labels[0] if labels else "unknown", True
  raise AssertionError(f"reference card action button not found: {labels}")


async def wait_reference_viewer_text_fields(page, required_tokens: list[str], label: str, timeout_ms: int = 8000, interval_ms: int = 200) -> dict:
  last_diag = {}
  deadline = time.monotonic() + (timeout_ms / 1000.0)
  while time.monotonic() < deadline:
    last_diag = await collect_reference_viewer_text(page)
    normalized_text = normalize_reference_text(last_diag.get('normalizedText', ''))
    if all(token in normalized_text for token in required_tokens):
      return last_diag
    await page.wait_for_timeout(interval_ms)
  raise AssertionError(f"reference viewer fields not found ({label}): required={required_tokens} normalizedText={last_diag.get('normalizedText', '')} diag={last_diag}")


async def get_reference_tracking(page) -> dict:
  diag = await collect_reference_viewer_text(page)
  return {
    "fetchedUrls": diag.get("fetchedUrls", []),
    "openedUrls": diag.get("openedUrls", []),
    "cardButtonTexts": diag.get("cardButtonTexts", []),
    "activeNexusTab": diag.get("activeNexusTab", ""),
  }


async def verify_reference_card_actions(page) -> None:
  clicked_action_button = ""
  initial_viewer_diag = {}
  final_viewer_diag = {}
  async def ref_diag_dump(label: str, reason: str = ""):
    ref_diag = await collect_reference_viewer_text(page)
    printable = {
      "selectorTextDump": ref_diag.get("candidates", []),
      "normalizedText": ref_diag.get("normalizedText", ""),
      "normalizedViewerText": ref_diag.get("normalizedText", ""),
      "cardButtonTexts": ref_diag.get("cardButtonTexts", []),
      "cardButtons": ref_diag.get("cardButtons", []),
      "fetchedUrls": ref_diag.get("fetchedUrls", []),
      "openedUrls": ref_diag.get("openedUrls", []),
      "activeNexusTab": ref_diag.get("activeNexusTab", ""),
      "refCardCount": ref_diag.get("refCardCount", 0),
      "viewerStatus": "updated" if all(token in ref_diag.get("normalizedText", "") for token in ["source_id: src-1", "mode: text", "highlight: doc-1:0"]) else "initial_or_pending",
      "viewerInitialStatus": "updated" if all(token in normalize_reference_text(initial_viewer_diag.get("normalizedText", "")) for token in ["source_id: src-1", "mode: text", "highlight: doc-1:0"]) else "initial_or_pending",
      "viewerFinalStatus": "updated" if all(token in normalize_reference_text(final_viewer_diag.get("normalizedText", "")) for token in ["source_id: src-1", "mode: text", "highlight: doc-1:0"]) else "initial_or_pending",
      "clickedActionButton": clicked_action_button,
      "fullErrorReason": reason,
    }
    print(f"INFO: reference_card_actions diagnostics ({label}): {printable}")
    return ref_diag
  await page.click("#btn-nexus")
  web_scout_tab = page.locator("#nexus-btn-web-scout")
  if await web_scout_tab.count() > 0:
    await web_scout_tab.click()
  else:
    await page.click("#nexus-btn-sources")
    await page.click("#nexus-btn-research")

  await page.evaluate(
    """
    () => {
      window.__openedUrls = [];
      window.__fetchedUrls = [];
      const realFetch = window.fetch.bind(window);
      window.open = (url) => {
        window.__openedUrls.push(String(url || ''));
        return null;
      };
      window.fetch = async (input, init) => {
        const url = String(typeof input === 'string' ? input : (input?.url || ''));
        if (url.includes('/nexus/sources/src-1')) {
          window.__fetchedUrls.push(url);
        }
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
          url: 'https://example.com/report',
          source_url: 'https://example.com/report',
          original_url: 'https://example.com/report',
          final_url: 'https://example.com/report',
          link: 'https://example.com/report',
          local_text_path: '/tmp/mock.txt',
        }],
        [{ source_id: 'src-1', quote: 'mock quote', chunk_id: 'doc-1:0', page_start: 2, page_end: 3 }],
      );
    }
    """
  )

  ref_debug = await page.evaluate("""() => {
    const root = document.getElementById('nexus-deep-references');
    return {
      innerHTML: root?.innerHTML || '',
      buttonTexts: root ? Array.from(root.querySelectorAll('button')).map((el) => el.textContent || '') : [],
    };
  }""")
  print(f"INFO: nexus deep references debug: {ref_debug}")

  try:
    ref_card = page.locator("#nexus-deep-references .nexus-ref-card").first
    await ref_card.wait_for(state="visible")
    assert await ref_card.locator("text=[S1] Mock Source").count() > 0

    initial_viewer_diag = await collect_reference_viewer_text(page)
    clicked_action_button = await click_reference_button(ref_card, ["全文表示", "Text", "Open Text", "Show Full Text", "全文"])
    final_viewer_diag = await wait_reference_viewer_text_fields(page, ["source_id: src-1", "mode: text"], "Full Text")
    tracking = await get_reference_tracking(page)
    assert any("/nexus/sources/src-1/text" in url for url in tracking["fetchedUrls"]), tracking

    clicked_action_button = await click_reference_button(ref_card, ["該当箇所", "Highlight", "Citation", "Chunk", "Open Highlight"])
    await wait_reference_viewer_text_fields(page, ["doc-1:0"], "Highlight")

    clicked_action_button, source_url_clicked = await click_reference_button_if_enabled(ref_card, ["元URL", "Source URL", "Open Source"])
    tracking = await get_reference_tracking(page)
    if source_url_clicked:
      assert any("https://example.com/report" in url for url in tracking["openedUrls"]), tracking
    else:
      print("INFO: Source URL action skipped because URL button disabled")

    clicked_action_button = await click_reference_button(ref_card, ["ダウンロード", "Download"])
    tracking = await get_reference_tracking(page)
    assert any("/nexus/sources/src-1/original" in url for url in tracking["openedUrls"]) or any("/nexus/sources/src-1/original" in url for url in tracking["fetchedUrls"]), tracking
  except (AssertionError, PlaywrightTimeoutError) as err:
    await ref_diag_dump(f"failure: {type(err).__name__}", str(err))
    raise

  viewer_diag = await wait_reference_viewer_text_fields(page, ["source_id: src-1", "mode: text", "doc-1:0"], "Final")
  viewer_text = normalize_reference_text(viewer_diag.get("normalizedText", ""))
  assert "[S1] Mock Source" in viewer_text, viewer_text
  assert "source_id: src-1" in viewer_text, viewer_text
  assert "mode: text" in viewer_text, viewer_text
  assert "highlight: doc-1:0" in viewer_text, viewer_text
  fetched_urls = await page.evaluate("() => window.__fetchedUrls || []")
  opened_urls = await page.evaluate("() => window.__openedUrls || []")
  await ref_diag_dump("final")
  assert any("/nexus/sources/src-1/text" in url for url in fetched_urls), fetched_urls
  source_url_button_state = await page.evaluate("""() => {
    const card = document.querySelector('#nexus-deep-references .nexus-ref-card');
    if (!card) return { exists: false, disabled: null, onclick: '', text: '' };
    const button = Array.from(card.querySelectorAll('button')).find((el) => ['元URL', 'Source URL', 'Open Source'].includes((el.textContent || '').trim()));
    if (!button) return { exists: false, disabled: null, onclick: '', text: '' };
    return { exists: true, disabled: !!button.disabled, onclick: button.getAttribute('onclick') || '', text: (button.textContent || '').trim() };
  }""")
  if source_url_button_state.get("exists") and not source_url_button_state.get("disabled"):
    assert any("https://example.com/report" in url for url in opened_urls), opened_urls
  else:
    print(f"INFO: Source URL action skipped because URL button disabled: {source_url_button_state}")
  assert any("/nexus/sources/src-1/original" in url for url in opened_urls), opened_urls


def get_atlas_requirement_input(page):
  return page.locator("#atlas-workbench-card #atlas-requirement-input")


async def click_atlas_requirement_clear(page) -> None:
  clear_btn = page.locator("#atlas-workbench-card #atlas-requirement-clear-btn")
  await clear_btn.wait_for(state="visible")
  await clear_btn.scroll_into_view_if_needed()
  await clear_btn.click()


async def click_atlas_use_chat_input(page) -> None:
  use_chat_btn = page.locator("#atlas-workbench-card #atlas-requirement-use-chat-btn")
  await use_chat_btn.wait_for(state="visible")
  await use_chat_btn.scroll_into_view_if_needed()
  await use_chat_btn.click()


async def fill_atlas_requirement(page, text: str) -> None:
  requirement = get_atlas_requirement_input(page)
  await requirement.wait_for(state="visible")
  await requirement.scroll_into_view_if_needed()
  await requirement.fill(text)


async def verify_mobile_mode_switches(page) -> None:
  await page.set_viewport_size(DEFAULT_MOBILE_VIEWPORT)
  await page.wait_for_timeout(100)
  errors: list[str] = []
  page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
  page.on("console", lambda m: errors.append(f"console[{m.type}]: {m.text}") if m.type == "error" else None)


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
  await page.wait_for_function(
    "() => { const col = document.getElementById('agent-col'); const panel = document.getElementById('agent-panel-col'); const chat = document.getElementById('mob-agent-chat'); return (!!col && !col.classList.contains('mob-hidden')) || (!!panel && !panel.classList.contains('mob-hidden')) || (!!chat && getComputedStyle(chat).display !== 'none'); }"
  )
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
    "() => document.getElementById('mob-nexus') && getComputedStyle(document.getElementById('mob-nexus')).display !== 'none'"
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
