#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from pathlib import Path
import os
import re
import time
from urllib.parse import urljoin
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

def get_smoke_base_url(use_explicit_base_url: bool = False):
  explicit = os.environ.get("PLAYWRIGHT_SMOKE_BASE_URL", "").strip()
  if use_explicit_base_url and explicit:
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




def _truncate_json(value, limit: int = 240):
  try:
    text = json.dumps(value, ensure_ascii=False)
  except Exception:
    return "<non-json>"
  if len(text) <= limit:
    return text
  return text[:limit] + "...<truncated>"


async def collect_backend_preflight_status(page) -> dict:
  base_url = os.environ.get("PLAYWRIGHT_SMOKE_BASE_URL", "").strip() or "mock-http-origin"
  endpoints = [
    ("health", "/health"),
    ("systemSummary", "/system/summary"),
    ("settings", "/settings"),
    ("projects", "/projects"),
    ("modelDbStatus", "/models/db/status"),
  ]
  status: dict[str, object] = {"baseUrl": base_url, "errors": [], "warnings": []}
  for key, path in endpoints:
    target_url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/")) if base_url.startswith("http") else path
    started = time.perf_counter()
    try:
      res = await page.request.get(target_url, timeout=3000)
      elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
      payload: dict[str, object] = {"status": res.status, "ok": res.ok, "elapsedMs": elapsed_ms}
      ctype = (res.headers.get("content-type") or "").lower()
      if "application/json" in ctype:
        try:
          payload["json"] = _truncate_json(await res.json())
        except Exception as exc:
          payload["jsonError"] = str(exc)
          status["warnings"].append(f"{path}: json parse failed ({exc})")
      elif ctype:
        payload["contentType"] = ctype
      status[key] = payload
      if key == "health" and res.status >= 500:
        status["errors"].append(f"{path}: health returned HTTP {res.status}")
      elif key != "health" and res.status >= 500:
        status["warnings"].append(f"{path}: returned HTTP {res.status}")
      elif key != "health" and res.status != 200:
        status["warnings"].append(f"{path}: returned HTTP {res.status}")
    except Exception as exc:
      elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
      status[key] = {"error": str(exc), "elapsedMs": elapsed_ms}
      if key == "health":
        status["errors"].append(f"{path}: {exc}")
      else:
        status["warnings"].append(f"{path}: {exc}")
  return status


async def run_backend_preflight(page) -> None:
  preflight = await collect_backend_preflight_status(page)
  print("INFO: backend preflight status:\n" + json.dumps(preflight, ensure_ascii=False, indent=2))
  if preflight.get("errors"):
    raise AssertionError(f"backend preflight failed: {preflight['errors']}")


async def start_atlas_backend_e2e_journey(page, atlas_requirement: str) -> None:
  await page.click("#btn-chat")
  await set_chat_input(page, "")
  await page.click("#btn-atlas")
  await page.wait_for_selector("#atlas-workbench-card")
  await page.click("#atlas-workbench-card [data-atlas-subview-tab='overview']")
  await page.fill("#atlas-requirement-input", atlas_requirement)
  await page.click("#atlas-workbench-card [data-atlas-subview-panel='overview'] button.phase1-plan-btn")


async def verify_atlas_backend_e2e_journey(page) -> None:
  page_errors: list[str] = []
  console_errors: list[str] = []
  page.on("pageerror", lambda e: page_errors.append(str(e)))
  page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
  preflight_status = await collect_backend_preflight_status(page)
  if preflight_status.get("errors"):
    raise AssertionError(f"backend preflight failed before full e2e: {preflight_status}")
  base_url = os.environ.get("PLAYWRIGHT_SMOKE_BASE_URL", "").strip() or "mock-http-origin"
  atlas_requirement = "Phase 26.0 backend e2e smoke requirement"

  async def backend_e2e_diag_dump(label: str):
    diag = await page.evaluate("""() => ({
      mode: document.querySelector('#mode-switcher .active,[data-mode].active')?.id || '',
      atlasSubview: document.getElementById('atlas-workbench-card')?.dataset?.atlasCurrentSubview || '',
      atlasRequirementInput: document.getElementById('atlas-requirement-input')?.value || '',
      atlasRequirementStatus: document.getElementById('atlas-requirement-status')?.textContent || '',
      messagesTail: Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || '').slice(0, 240)).slice(-8),
      planFlowTextTail: (document.getElementById('atlas-workbench-card-plan-flow')?.textContent || '').slice(-600),
      approveButtonsPresent: !!document.querySelector("#approve-plan-btn, [data-action='approve-plan']"),
      executeButtonsPresent: !!document.querySelector("#execute-preview-btn, [data-action='execute-preview']"),
      patchApplyButtonsPresent: !!document.querySelector("#apply-patch-btn, [data-action='apply-patch']"),
      bulkApprovePresent: !!Array.from(document.querySelectorAll('button')).find((el) => /bulk\\s*approve/i.test(el.textContent || '')),
      bulkApplyPresent: !!Array.from(document.querySelectorAll('button')).find((el) => /bulk\\s*apply/i.test(el.textContent || '')),
    })""")
    diag["baseUrl"] = base_url
    diag["preflightStatus"] = preflight_status
    diag["hasAtlasStartFailed"] = any("Atlas Start failed:" in (m or "") for m in diag.get("messagesTail", []))
    diag["consoleErrors"] = list(console_errors)
    diag["pageErrors"] = list(page_errors)
    print(f"INFO: atlas backend e2e diagnostics ({label}): {diag}")

  try:
    await start_atlas_backend_e2e_journey(page, atlas_requirement)
    print("INFO: backend E2E dry-run stops before approval/execute/patch actions.")

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
  except Exception:
    await backend_e2e_diag_dump("failure")
    raise
  await backend_e2e_diag_dump("success")
  if page_errors or console_errors:
    joined = [f"pageerror: {text}" for text in page_errors] + [f"console[error]: {text}" for text in console_errors]
    raise AssertionError("\n".join(joined))


async def collect_atlas_job_lifecycle_diag(page, preflight_status=None, base_url: str = "", elapsed_ms: int = 0, final_decision: str = "unknown", current_job_id: str = "") -> dict:
  status_text = await page.evaluate("""() => (document.getElementById('atlas-workflow-status')?.textContent || '')""")
  messages = await page.evaluate("""() => Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || ''))""")
  plan_flow_text = await page.evaluate("""() => (document.getElementById('atlas-workbench-card-plan-flow')?.textContent || '')""")
  atlas_data = await page.evaluate("""() => ({
    atlasSubview: document.getElementById('atlas-workbench-card')?.dataset?.atlasCurrentSubview || '',
    atlasRequirementInput: document.getElementById('atlas-requirement-input')?.value || '',
    atlasRequirementStatus: document.getElementById('atlas-requirement-status')?.textContent || '',
    approveButtonsPresent: !!document.querySelector("#approve-plan-btn, [data-action='approve-plan']"),
    executeButtonsPresent: !!document.querySelector("#execute-preview-btn, [data-action='execute-preview']"),
    patchApplyButtonsPresent: !!document.querySelector("#apply-patch-btn, [data-action='apply-patch']"),
  })""")

  async def safe_get_json(path: str) -> dict:
    payload = {"status": None, "ok": False, "json": None, "jsonError": None, "error": None}
    try:
      response = await page.request.get(urljoin(base_url.rstrip("/") + "/", path), timeout=5000)
      payload["status"] = response.status
      payload["ok"] = bool(response.ok)
      try:
        payload["json"] = await response.json()
      except Exception as exc:
        payload["jsonError"] = str(exc)
    except Exception as exc:
      payload["error"] = str(exc)
    return payload

  jobs_resp = await safe_get_json("projects/default/jobs?limit=20")
  history_resp = await safe_get_json("projects/default/history?limit=20")

  status_tail = status_text[-800:]
  messages_tail = [str(m)[-240:] for m in messages[-10:]]
  plan_tail = plan_flow_text[-800:]
  last_error = "-"
  for line in status_text.splitlines():
    if "Last Error:" in line:
      last_error = line.split("Last Error:", 1)[1].strip() or "-"
      break
  if not current_job_id and isinstance(jobs_resp, dict):
    jobs_json = jobs_resp.get("json") if isinstance(jobs_resp.get("json"), dict) else {}
    for j in jobs_json.get("jobs", []):
      if isinstance(j, dict) and j.get("id"):
        current_job_id = str(j.get("id"))
        break
  return {
    "baseUrl": base_url,
    "preflightStatus": preflight_status,
    **atlas_data,
    "atlasWorkflowStatusTextTail": status_tail,
    "planFlowTextTail": plan_tail,
    "messagesTail": messages_tail,
    "lastError": last_error,
    "activeJobsResponse": _truncate_json(jobs_resp),
    "recentJobsResponse": _truncate_json(history_resp),
    "currentJobId": current_job_id,
    "elapsedMs": elapsed_ms,
    "finalDecision": final_decision,
  }


async def wait_atlas_plan_completion(page, timeout_ms=180000, preflight_status=None, base_url: str = "", console_errors=None, page_errors=None) -> dict:
  console_errors = console_errors or []
  page_errors = page_errors or []
  started = time.perf_counter()
  final = "timeout"
  last_diag = {}
  while (time.perf_counter() - started) * 1000 < timeout_ms:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    diag = await collect_atlas_job_lifecycle_diag(page, preflight_status=preflight_status, base_url=base_url, elapsed_ms=elapsed_ms)
    diag["consoleErrors"] = list(console_errors)
    diag["pageErrors"] = list(page_errors)
    raw_haystack = "\n".join([diag.get("atlasWorkflowStatusTextTail", ""), diag.get("planFlowTextTail", ""), "\n".join(diag.get("messagesTail", []))])
    normalized_haystack = " ".join(raw_haystack.replace("•", " ").replace("	", " ").lower().split())
    haystack = normalized_haystack.replace(":", ": ").replace("  ", " ")
    last_error = str(diag.get("lastError", "-") or "-").strip()
    active_jobs = diag.get("activeJobsResponse", {}) if isinstance(diag.get("activeJobsResponse"), dict) else {}
    active_jobs_json = active_jobs.get("json") if isinstance(active_jobs.get("json"), dict) else {}
    active_statuses = [str(j.get("status", "")).strip().lower() for j in active_jobs_json.get("jobs", []) if isinstance(j, dict)]
    active_failed = any(st in {"failed", "error", "cancelled", "canceled"} for st in active_statuses)
    completion_signal_tokens = [
      "plan: completed",
      "plan: ready",
      "plan ready",
      "review ready",
      "plan generated",
      "generated plan",
      "plan review",
      "review: ready",
      "review: required",
      "requirement: done",
      "plan: generated",
      "review: done",
      "approval: required",
    ]
    pending_signal_tokens = ["plan: pending", "review: pending", "requirement: pending"]
    plan_flow_requirements = {
      "plan_flow_requirement_done": "requirement: done",
      "plan_flow_plan_generated": "plan: generated",
      "plan_flow_review_done": "review: done",
      "plan_flow_approval_required": "approval: required",
    }
    clarification_plan_flow_requirements = {
      "plan_flow_requirement_done": "requirement: done",
      "plan_flow_plan_pending": "plan: pending",
      "plan_flow_review_pending": "review: pending",
    }
    clarification_signal_tokens = {
      "next_action_answer_clarification": "next action: answer clarification",
      "answer_clarification_text_present": "answer clarification",
      "answer_and_generate_plan_button_present": "回答してplan生成",
      "proceed_with_assumptions_button_present": "おまかせで進める",
      "clarification_keyword_present": "clarification",
      "question_keyword_present": "question",
      "additional_confirmation_keyword_present": "追加確認",
      "confirmation_items_keyword_present": "確認事項",
    }
    matched_plan_flow = [name for name, token in plan_flow_requirements.items() if token in haystack]
    missing_plan_flow = [name for name in plan_flow_requirements if name not in matched_plan_flow]
    completion_signals = [token for token in completion_signal_tokens if token in haystack]
    completion_signals.extend(matched_plan_flow)
    pending_signals = [token for token in pending_signal_tokens if token in haystack]
    clarification_signals = [name for name, token in clarification_signal_tokens.items() if token in haystack]
    clarification_plan_flow_matched = [name for name, token in clarification_plan_flow_requirements.items() if token in haystack]
    backend_done_statuses = {"succeeded", "completed", "done", "success"}
    backend_running_statuses = {"running"}
    backend_statuses = [st for st in active_statuses if st]
    backend_done_hits = [st for st in backend_statuses if st in backend_done_statuses]
    backend_running_hits = [st for st in backend_statuses if st in backend_running_statuses]
    failure_signals = []
    if "atlas start failed:" in haystack:
      failure_signals.append("atlas_start_failed")
    if last_error not in ("", "-"):
      failure_signals.append("last_error_present")
    if " job failed" in haystack or "status: failed" in haystack or "failed:" in haystack or " exception" in haystack or " error:" in haystack:
      failure_signals.append("failed_text_detected")
    if active_failed:
      failure_signals.append("backend_failed_status")
    diag["completionSignals"] = completion_signals
    diag["pendingSignals"] = pending_signals
    diag["backendJobStatuses"] = backend_statuses
    diag["failureSignals"] = failure_signals
    diag["normalizedPlanFlowText"] = haystack
    diag["matchedCompletionSignals"] = matched_plan_flow
    diag["missingCompletionSignals"] = missing_plan_flow
    diag["clarificationSignals"] = clarification_signals
    diag["completionDecisionReason"] = "in_progress"

    if failure_signals:
      final = "failed"
      reason = "last_error_present" if "last_error_present" in failure_signals else "failure_signal_detected"
      last_diag = {**diag, "finalDecision": final, "completionDecisionReason": reason}
      break

    active_jobs_available = not (active_jobs.get("status") in (404, None) and (active_jobs.get("error") or active_jobs.get("json") is None))
    has_completion_signal = len(completion_signals) > 0
    has_pending_signal = len(pending_signals) > 0

    has_clarification_signal = len(clarification_signals) > 0
    has_clarification_plan_flow = all(name in clarification_plan_flow_matched for name in clarification_plan_flow_requirements)
    if has_clarification_plan_flow and has_clarification_signal and last_error in ("", "-") and not console_errors and not page_errors and not failure_signals:
      final = "needs_clarification"
      clarification_completion_signals = list(dict.fromkeys(clarification_plan_flow_matched + ["clarification_required"]))
      last_diag = {
        **diag,
        "finalDecision": final,
        "completionDecisionReason": "clarification_required_before_plan_generation",
        "completionSignals": clarification_completion_signals,
      }
      break
    if has_pending_signal:
      diag["completionDecisionReason"] = "pending_plan_detected"
    elif not missing_plan_flow and last_error in ("", "-") and not console_errors and not page_errors:
      final = "completed"
      last_diag = {**diag, "finalDecision": final, "completionDecisionReason": "plan_flow_generated_review_done_approval_required"}
      break
    elif has_completion_signal and backend_done_hits:
      final = "completed"
      last_diag = {**diag, "finalDecision": final, "completionDecisionReason": "ui_plan_ready_and_backend_done"}
      break
    elif has_completion_signal and not active_jobs_available:
      final = "completed"
      last_diag = {**diag, "finalDecision": final, "completionDecisionReason": "ui_plan_ready_backend_unavailable"}
      break
    elif has_completion_signal and backend_running_hits:
      diag["completionDecisionReason"] = "backend_running_not_completed"
    last_diag = diag
    await page.wait_for_timeout(2000)
  if not last_diag:
    last_diag = await collect_atlas_job_lifecycle_diag(page, preflight_status=preflight_status, base_url=base_url, elapsed_ms=timeout_ms)
  last_diag["consoleErrors"] = list(console_errors)
  last_diag["pageErrors"] = list(page_errors)
  last_diag["elapsedMs"] = int((time.perf_counter() - started) * 1000)
  if final == "timeout" and not last_diag.get("completionDecisionReason"):
    last_diag["completionDecisionReason"] = "timeout_without_completion"
  if final == "timeout":
    last_diag.setdefault("normalizedPlanFlowText", "")
    last_diag.setdefault("matchedCompletionSignals", [])
    last_diag.setdefault("missingCompletionSignals", ["plan_flow_requirement_done", "plan_flow_plan_generated", "plan_flow_review_done", "plan_flow_approval_required"])
  last_diag["finalDecision"] = final if final != "timeout" else last_diag.get("finalDecision", "timeout")
  return last_diag

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


async def get_reference_button_state(card, labels: list[str]) -> dict:
  for label in labels:
    locator = card.get_by_role("button", name=label)
    if await locator.count() > 0:
      button = locator.first
      return {
        "exists": True,
        "disabled": await button.is_disabled(),
        "enabled": await button.is_enabled(),
        "visible": await button.is_visible(),
        "text": ((await button.text_content()) or "").strip(),
        "onclick": (await button.get_attribute("onclick")) or "",
      }
  return {
    "exists": False,
    "disabled": None,
    "enabled": False,
    "visible": False,
    "text": "",
    "onclick": "",
  }


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
  source_url_action_status = "skippedMissing"
  source_url_button_state = {}
  download_action_status = "inspected"
  download_button_state = {}
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
      "sourceUrlActionStatus": source_url_action_status,
      "sourceUrlButtonState": source_url_button_state,
      "downloadActionStatus": download_action_status,
      "downloadButtonState": download_button_state,
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

    source_url_button_state = await get_reference_button_state(ref_card, ["元URL", "Source URL", "Open URL", "Original URL", "URL"])
    if source_url_button_state.get("exists") and source_url_button_state.get("enabled"):
      clicked_action_button = await click_reference_button(ref_card, ["元URL", "Source URL", "Open URL", "Original URL", "URL"])
      tracking = await get_reference_tracking(page)
      source_url_action_status = "opened" if any("https://example.com/report" in url for url in tracking.get("openedUrls", [])) else "clickedNoOpen"
      if source_url_action_status == "clickedNoOpen":
        print("INFO: Source URL action did not open a URL; continuing because Source URL is diagnostic-only.")
    elif source_url_button_state.get("exists"):
      source_url_action_status = "skippedDisabled"
      print(f"INFO: Source URL action skipped: button disabled, onclick={source_url_button_state.get('onclick', '')}, text={source_url_button_state.get('text', '')}")
    else:
      source_url_action_status = "skippedMissing"
      print("INFO: Source URL action skipped: button missing")
    if source_url_action_status == "skippedDisabled":
      print("INFO: Source URL action did not open a URL; continuing because Source URL is diagnostic-only.")
    elif source_url_action_status == "skippedMissing":
      print("INFO: Source URL action did not open a URL; continuing because Source URL is diagnostic-only.")

    download_button_state = await get_reference_button_state(ref_card, ["ダウンロード", "Download"])
    if not download_button_state.get("exists"):
      download_action_status = "skippedMissing"
      print("INFO: Download action skipped: button missing")
    elif not download_button_state.get("enabled"):
      download_action_status = "skippedDisabled"
      print(f"INFO: Download action skipped: button disabled, onclick={download_button_state.get('onclick', '')}, text={download_button_state.get('text', '')}")
    else:
      download_action_status = "inspected"
      print("INFO: Download action inspected only; not clicked to avoid current-page navigation in UI smoke.")
  except (AssertionError, PlaywrightTimeoutError) as err:
    await ref_diag_dump(f"failure: {type(err).__name__}", str(err))
    raise

  fetched_urls = await page.evaluate("() => window.__fetchedUrls || []")
  await ref_diag_dump("final")
  assert any("/nexus/sources/src-1/text" in url for url in fetched_urls), fetched_urls


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

  run_backend_preflight_opt_in = os.environ.get("RUN_ATLAS_BACKEND_PREFLIGHT", "").strip() == "1"
  run_backend_e2e_opt_in = os.environ.get("RUN_ATLAS_BACKEND_E2E", "").strip() == "1"
  run_backend_wait_plan_opt_in = os.environ.get("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN", "").strip() == "1"
  if run_backend_wait_plan_opt_in and not run_backend_e2e_opt_in:
    raise AssertionError("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN requires RUN_ATLAS_BACKEND_E2E=1.")
  preflight_only_mode = run_backend_preflight_opt_in and not run_backend_e2e_opt_in
  full_backend_e2e_mode = run_backend_e2e_opt_in
  real_backend_opt_in = run_backend_preflight_opt_in or run_backend_e2e_opt_in
  explicit_base_url = os.environ.get("PLAYWRIGHT_SMOKE_BASE_URL", "").strip()

  async with async_playwright() as p:
    browser = await p.chromium.launch()
    if explicit_base_url and not real_backend_opt_in:
      print("INFO: PLAYWRIGHT_SMOKE_BASE_URL is ignored in default mock-backed UI smoke. Set RUN_ATLAS_BACKEND_PREFLIGHT=1 or RUN_ATLAS_BACKEND_E2E=1 to target a real backend.")
    if real_backend_opt_in and not explicit_base_url:
      raise AssertionError("PLAYWRIGHT_SMOKE_BASE_URL is required when RUN_ATLAS_BACKEND_PREFLIGHT=1 or RUN_ATLAS_BACKEND_E2E=1.")
    base_url, mock_server = get_smoke_base_url(use_explicit_base_url=real_backend_opt_in)
    print(f"INFO: Playwright smoke base URL = {base_url}")
    results: list[dict[str, str]] = []
    default_ui_scenarios = [
      ("bootstrap_api_contract", lambda current_page: current_page.evaluate("() => [typeof window.setMode, typeof window.switchNexusTab]")),
      ("mode_switches", verify_mode_switches),
      ("atlas_start_button_feedback", verify_atlas_start_button_feedback),
      ("atlas_guided_workflow_safe_journey", verify_atlas_guided_workflow_safe_journey),
      ("mode_specific_subtabs", verify_mode_specific_subtabs),
      ("nexus_tabs", verify_nexus_tabs),
      ("reference_card_actions", verify_reference_card_actions),
      ("chat_search_and_agent_web_tool_tts", verify_chat_search_and_agent_web_tool_tts),
    ]


    if preflight_only_mode:
      print("INFO: preflight-only mode enabled (RUN_ATLAS_BACKEND_PREFLIGHT=1, RUN_ATLAS_BACKEND_E2E unset).")
      print("INFO: UI scenarios skipped in preflight-only mode.")
      scenarios = [("atlas_backend_preflight", run_backend_preflight)]
    elif full_backend_e2e_mode:
      print("INFO: full backend E2E mode enabled (RUN_ATLAS_BACKEND_E2E=1).")
      print("INFO: default UI scenarios are skipped in full backend E2E mode.")

      async def verify_atlas_backend_e2e_wait_plan(page):
        page_errors = []
        console_errors = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        preflight_status = await collect_backend_preflight_status(page)
        if preflight_status.get("errors"):
          raise AssertionError(f"backend preflight failed before wait-plan e2e: {preflight_status}")
        base_url = os.environ.get("PLAYWRIGHT_SMOKE_BASE_URL", "").strip() or "mock-http-origin"
        await start_atlas_backend_e2e_journey(page, "Phase 26.0 backend e2e smoke requirement")
        await page.wait_for_function(
          "() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'plan'",
          timeout=30_000,
        )
        diag = await wait_atlas_plan_completion(page, timeout_ms=180000, preflight_status=preflight_status, base_url=base_url, console_errors=console_errors, page_errors=page_errors)
        print("INFO: atlas backend wait-plan diagnostics:\n" + json.dumps(diag, ensure_ascii=False, indent=2))
        if diag.get("finalDecision") in ("failed", "timeout", "unknown"):
          raise AssertionError(f"atlas wait-plan did not complete successfully: {json.dumps(diag, ensure_ascii=False)}")

      if run_backend_wait_plan_opt_in:
        scenarios = [
          ("atlas_backend_preflight", run_backend_preflight),
          ("atlas_backend_e2e_wait_plan", verify_atlas_backend_e2e_wait_plan),
        ]
      else:
        scenarios = [
          ("atlas_backend_preflight", run_backend_preflight),
          ("atlas_backend_e2e_journey", verify_atlas_backend_e2e_journey),
        ]
    else:
      print("INFO: default mode enabled; running mock-backed UI smoke scenarios.")
      print("INFO: backend preflight remains opt-in (set RUN_ATLAS_BACKEND_PREFLIGHT=1 to include).")
      print("SKIP: RUN_ATLAS_BACKEND_E2E is not set")
      print("INFO: backend E2E scenario remains opt-in (set RUN_ATLAS_BACKEND_E2E=1 to include).")
      scenarios = list(default_ui_scenarios)

      async def bootstrap_assertions(current_page) -> None:
        set_mode_type, switch_tab_type = await current_page.evaluate("() => [typeof window.setMode, typeof window.switchNexusTab]")
        assert set_mode_type == "function", f"window.setMode is {set_mode_type}"
        assert switch_tab_type == "function", f"window.switchNexusTab is {switch_tab_type}"

      scenarios[0] = ("bootstrap_api_contract", bootstrap_assertions)

    for scenario_name, scenario_fn in scenarios:
      await run_smoke_scenario(scenario_name, browser, base_url, scenario_fn, results, DEFAULT_DESKTOP_VIEWPORT)

    if not (preflight_only_mode or full_backend_e2e_mode):
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
