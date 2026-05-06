#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
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
PLAYWRIGHT_ARTIFACT_DIR = Path(os.environ.get("PLAYWRIGHT_SMOKE_ARTIFACT_DIR", str(ROOT / "artifacts" / "playwright")))
DEFAULT_DESKTOP_VIEWPORT = {"width": 1280, "height": 900}
DEFAULT_MOBILE_VIEWPORT = {"width": 390, "height": 844}



def _is_browser_launch_infra_error(exc: Exception) -> bool:
  text = f"{type(exc).__name__}: {exc}".lower()
  return any(token in text for token in [
    "targetclosederror",
    "browser has been closed",
    "target page, context or browser has been closed",
    "sigsegv",
    "process did exit",
  ])


async def launch_browser_with_retry(p, *, attempts: int = 2):
  last_error = None
  for attempt in range(1, max(1, attempts) + 1):
    try:
      return await p.chromium.launch()
    except Exception as exc:
      last_error = exc
      if not _is_browser_launch_infra_error(exc):
        raise
      print(f"WARN: browser launch infra retry {attempt}/{attempts}: {type(exc).__name__}: {exc}")
      if attempt < attempts:
        await asyncio.sleep(1)
  raise AssertionError(f"infra_browser_launch_failed: {type(last_error).__name__}: {last_error}")


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




async def write_dom_snapshot(page, label: str) -> str:
  PLAYWRIGHT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
  safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", label).strip("_") or "dom_snapshot"
  path = PLAYWRIGHT_ARTIFACT_DIR / f"{safe}.html"
  try:
    html_text = await page.content()
  except Exception as exc:
    html_text = f"<!-- DOM snapshot unavailable: {type(exc).__name__}: {exc} -->"
  path.write_text(html_text, encoding="utf-8")
  return path.name


async def wait_named(page, name: str, js_condition: str, *, timeout: int = 30_000, arg=None) -> None:
  try:
    if arg is None:
      await page.wait_for_function(js_condition, timeout=timeout)
    else:
      await page.wait_for_function(js_condition, arg=arg, timeout=timeout)
  except Exception as exc:
    artifact = await write_dom_snapshot(page, f"wait_named_timeout_{name}")
    raise AssertionError(f"wait_named_timeout:{name}; artifact={artifact}; cause={type(exc).__name__}: {exc}") from exc

async def click_named(page, name: str, selector: str, *, timeout: int = 10_000) -> None:
  try:
    await page.locator(selector).click(timeout=timeout)
  except Exception as exc:
    artifact = await write_dom_snapshot(page, f"click_named_timeout_{name}")
    raise AssertionError(
      f"click_named_timeout:{name}; selector={selector}; artifact={artifact}; cause={type(exc).__name__}: {exc}"
    ) from exc

async def open_atlas(page) -> None:
  await page.click("#btn-atlas")
  await wait_named(page, 'atlas_panel_visible', "() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display !== 'none'")
  await wait_named(page, 'atlas_workbench_visible', "() => document.getElementById('atlas-workbench-card') && getComputedStyle(document.getElementById('atlas-workbench-card')).display !== 'none'")

async def set_mode(page, mode: str) -> None:
  button_map = {
    "chat": "#btn-chat",
    "atlas": "#btn-atlas",
    "agent": "#btn-agent",
    "echo": "#btn-echo",
    "nexus": "#btn-nexus",
  }
  selector = button_map.get(mode)
  if not selector:
    raise ValueError(f"unsupported mode: {mode}")
  await page.click(selector)

async def get_nexus_root_selector(page) -> str:
  candidates = [
    "#nexus-panel-col",
    "#nexus-col",
    "#nexus-workspace",
    "[data-mode-panel='nexus']",
  ]
  for selector in candidates:
    if await page.locator(selector).count() > 0:
      return selector
  raise AssertionError("nexus_root_not_found")

async def click_nexus_tab(page, tab: str) -> None:
  await set_mode(page, "nexus")
  root = await get_nexus_root_selector(page)
  selector = f"{root} [data-nexus-tab='{tab}']"
  if await page.locator(selector).count() == 0:
    selector = f"[data-nexus-tab='{tab}']"
  if await page.locator(selector).count() > 0:
    await click_named(page, f"nexus_tab_{tab}", selector)
  else:
    await page.evaluate("(tab) => { if (typeof switchNexusTab === 'function') switchNexusTab(tab); }", tab)

ATLAS_CHAT_LEAK_TOKENS = [
  "Atlas Workflow Status",
  "Requirement Source: atlas",
  "Source: atlas",
  "Workspace: Atlas",
  "Clarification required before planning",
  "Plan generated",
  "Plan review detected",
  "Approval status",
  "Execution ready",
  "Patch review",
]

async def assert_no_atlas_chat_leak(page, label: str) -> None:
  leak = await page.evaluate("""(tokens) => {
    const text = document.getElementById('messages')?.textContent || '';
    return tokens.find((token) => text.includes(token)) || '';
  }""", ATLAS_CHAT_LEAK_TOKENS)
  if leak:
    raise AssertionError(f"chat_atlas_leak_detected:{leak}; check={label}")


async def wait_atlas_subview(page, name: str) -> None:
  await wait_named(page, f'atlas_subview_dataset_{name}', "(subview) => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === subview", arg=name)
  await wait_named(page, f'atlas_subview_visible_{name}', "(subview) => { const panel = document.querySelector(`#atlas-workbench-card [data-atlas-subview-panel=\"${subview}\"]`); return !!panel && getComputedStyle(panel).display !== 'none'; }", arg=name)


async def set_atlas_subview(page, name: str) -> None:
  await open_atlas(page)
  await page.click(f"#atlas-workbench-card [data-atlas-subview-tab='{name}']")
  try:
    await wait_atlas_subview(page, name)
  except Exception:
    await page.evaluate("(subview) => { if (typeof window.setAtlasSubview === 'function') window.setAtlasSubview(subview); }", name)
    await wait_atlas_subview(page, name)


async def ensure_atlas_start(page) -> None:
  await set_atlas_subview(page, "start")


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
  assert await page.locator("#atlas-panel-col", has_text="Workflow Workbench").count() > 0
  assert await page.locator("#atlas-workbench-card").count() > 0
  assert await page.locator("#atlas-workbench-card [data-atlas-subview-tab='legacy']").count() == 0
  assert await page.get_by_role("button", name="Start Atlas").count() > 0
  assert await page.locator("#atlas-agent-execution-marker[data-atlas-agent-execution='true']").count() == 1
  await set_atlas_subview(page, "runs")
  assert await page.get_by_role("button", name="Load Recent Atlas Runs").count() > 0, "runs subview should expose recent runs action"

  await page.click("#btn-agent")
  await page.wait_for_function("() => document.getElementById('agent-col') && getComputedStyle(document.getElementById('agent-col')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('agent-panel-col') && getComputedStyle(document.getElementById('agent-panel-col')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display === 'none'")
  assert await page.locator("#agent-panel-col", has_text="Legacy Agent Advanced").count() > 0
  agent_chat_visible = await page.evaluate("() => getComputedStyle(document.getElementById('mob-agent-chat')).display !== 'none'")
  agent_tasks_visible = await page.evaluate("() => getComputedStyle(document.getElementById('mob-agent-tasks')).display !== 'none'")
  assert agent_chat_visible and agent_tasks_visible

  await page.click("#btn-chat")
  await wait_named(page, 'chat_visible', "() => document.getElementById('chat-col') && getComputedStyle(document.getElementById('chat-col')).display !== 'none'")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display === 'none'")
  await page.wait_for_function("() => document.getElementById('agent-col') && getComputedStyle(document.getElementById('agent-col')).display === 'none'")
  await page.wait_for_function("() => document.getElementById('agent-panel-col') && getComputedStyle(document.getElementById('agent-panel-col')).display === 'none'")
  assert await page.locator("#chat-role-note").count() == 0
  assert await page.locator("#chat-task-toggle").count() == 0
  chat_text = await page.locator("#chat-col").inner_text()
  for forbidden in ["Legacy Task", "Chat is for lightweight conversation", "Planning, approval", "Plan設定", "Open Atlas", "Use Chat Input", "Atlas Plan", "Atlas status"]:
    assert forbidden not in chat_text, f"Chat planning affordance leaked: {forbidden}"

  await page.click("#btn-atlas")
  await page.wait_for_function("() => document.getElementById('atlas-panel-col') && getComputedStyle(document.getElementById('atlas-panel-col')).display !== 'none'")

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
      clearVisible: !!document.querySelector('#atlas-workbench-card #atlas-requirement-clear-btn'),
      clearEnabled: !(document.querySelector('#atlas-workbench-card #atlas-requirement-clear-btn')?.disabled ?? true),
      startVisible: !!document.querySelector("#atlas-workbench-card [data-atlas-subview-panel='start'] button.phase1-plan-btn"),
      activeModeButton: document.querySelector('#mode-switcher .active,[data-mode].active')?.id || '',
    })""")
    print(f"INFO: atlas_start_button_feedback diagnostics ({label}): {diag}")
    return diag
  empty_start = "Atlas Start needs a request."
  empty_status = "Enter a requirement to start."
  atlas_start_value = "Atlas input start smoke"
  try:
    # A. Empty start feedback
    await set_chat_input(page, "")
    await ensure_atlas_start(page)
    await get_atlas_requirement_input(page).wait_for(state="visible")
    await fill_atlas_requirement(page, "")
    await page.click("#atlas-workbench-card [data-atlas-subview-panel='start'] button.phase1-plan-btn")
    await page.wait_for_function("() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'plan'")
    await page.wait_for_function("""([msg, statusText]) => {
      const status = document.getElementById('atlas-requirement-status')?.textContent || '';
      const flow = document.getElementById('atlas-plan-flow-summary')?.textContent || '';
      return status.includes(statusText) || flow.includes('Last Error');
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
    # C. Atlas input Start
    expected_text = atlas_start_value
    await fill_atlas_requirement(page, expected_text)
    await ensure_atlas_start(page)
    await page.click("#atlas-workbench-card [data-atlas-subview-panel='start'] button.phase1-plan-btn")
    await page.wait_for_function("() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'plan'")
    await page.wait_for_function("""([atlasValue]) => {
      const status = document.getElementById('atlas-requirement-status')?.textContent || '';
      const workbench = document.getElementById('atlas-workbench-status')?.textContent || '';
      const flow = document.getElementById('atlas-plan-flow-summary')?.textContent || '';
      const planPanel = document.querySelector('[data-atlas-subview-panel="plan"]')?.textContent || '';
      const overviewPanel = document.querySelector('[data-atlas-subview-panel="start"]')?.textContent || '';
      return (
        status.includes('Using Atlas requirement input.')
        || status.includes('Starting Atlas guided planning workflow...')
      ) && (
        workbench.includes('Current Action')
        || flow.includes('Requirement')
        || planPanel.includes('Guided Plan Flow')
        || overviewPanel.includes(atlasValue)
      );
    }""", arg=[atlas_start_value])
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
  before_messages = await page.evaluate("""() => Array.from(document.querySelectorAll('#messages .msg')).map((el) => el.textContent || '')""")
  await ensure_atlas_start(page)
  await page.fill("#atlas-requirement-input", "Phase 25 smoke requirement text")
  await page.click("#atlas-workbench-card [data-atlas-subview-panel='start'] button.phase1-plan-btn")
  await page.wait_for_function("() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'plan'")
  await page.wait_for_function("""() => {
    const status = document.getElementById('atlas-requirement-status')?.textContent || '';
    const flow = document.getElementById('atlas-plan-flow-summary')?.textContent || '';
    const workbench = document.getElementById('atlas-workbench-status')?.textContent || '';
    return (
      flow.includes('Requirement')
      && (
        status.includes('Starting Atlas guided planning workflow')
        || status.includes('Using Atlas requirement input')
        || status.includes('Atlas Start failed')
        || workbench.includes('Current Action')
      )
    );
  }""")
  await page.wait_for_function("""() => {
    const status = document.getElementById('atlas-requirement-status')?.textContent || '';
    return status.includes('Using Atlas requirement input.') || status.includes('Atlas Start failed') || status.includes('Starting Atlas guided planning workflow');
  }""")
  diag = await page.evaluate("""() => ({
    atlasRequirementInput: document.getElementById('atlas-requirement-input')?.value || '',
    chatInput: document.getElementById('input')?.value || '',
    status: document.getElementById('atlas-requirement-status')?.textContent || '',
    messages: Array.from(document.querySelectorAll('#messages .msg')).map((el) => el.textContent || ''),
  })""")
  assert diag["atlasRequirementInput"] == "Phase 25 smoke requirement text"
  after_messages = diag["messages"]
  new_messages = after_messages[len(before_messages):]
  forbidden = ['Atlas Workflow Status', 'Requirement Preview', 'Boss', 'Approval required', 'Plan generated', 'Starting Atlas guided planning workflow', 'Atlas Start needs a request']
  assert not any(any(token in msg for token in forbidden) for msg in new_messages), f"atlas chat leak detected: {new_messages}"

  for subview in ["runs", "execute", "patch"]:
    await page.click(f"#atlas-workbench-card [data-atlas-subview-tab='{subview}']")
    await page.wait_for_function("(name) => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === name", arg=subview)
  assert await page.locator("#atlas-workbench-card [data-atlas-subview-tab='legacy']").count() == 0

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
  await page.click("#atlas-workbench-card [data-atlas-subview-tab='start']")
  await page.fill("#atlas-requirement-input", atlas_requirement)
  await page.click("#atlas-workbench-card [data-atlas-subview-panel='start'] button.phase1-plan-btn")

ATLAS_APPROVAL_STABLE_PROMPT_LEGACY = "Create a non-destructive implementation plan for adding a small UI label to the Atlas Start tab. Do not execute or modify files."
ATLAS_APPROVAL_STABLE_PROMPT = "Create a concrete implementation plan for a small ui.html Atlas Start tab label update. Do not execute or modify files. Include target file ui.html, expected UI change, iPhone Safari regression checks, rollback notes, and require user confirmation before any execution."


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
    planFetchState: (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.workflowPhase || '',
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
      const flow = document.getElementById('atlas-workbench-card-plan-flow')?.textContent || '';
      const activityPlan = !!document.querySelector('#atlas-activity-stream [data-activity-type="plan_generated"]');
      return (
        (status.includes('Using Atlas requirement input.') || status.includes('Starting Atlas guided planning workflow'))
        && (flow.includes('Requirement') || flow.includes('Plan') || activityPlan)
      );
    }""", timeout=45_000)
    await assert_no_atlas_chat_leak(page, "backend_e2e")
  except Exception:
    await backend_e2e_diag_dump("failure")
    raise
  await backend_e2e_diag_dump("success")
  if page_errors or console_errors:
    joined = [f"pageerror: {text}" for text in page_errors] + [f"console[error]: {text}" for text in console_errors]
    raise AssertionError("\n".join(joined))


async def collect_atlas_job_lifecycle_diag(page, preflight_status=None, base_url: str = "", elapsed_ms: int = 0, final_decision: str = "unknown", current_job_id: str = "") -> dict:
  status_text = await page.evaluate("""() => (document.getElementById('atlas-workflow-status')?.textContent || document.getElementById('atlas-workbench-status')?.textContent || '')""")
  messages = await page.evaluate("""() => Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || ''))""")
  plan_flow_text = await page.evaluate("""() => (document.getElementById('atlas-workbench-card-plan-flow')?.textContent || '')""")
  atlas_data = await page.evaluate("""() => ({
    atlasSubview: document.getElementById('atlas-workbench-card')?.dataset?.atlasCurrentSubview || '',
    atlasRequirementInput: document.getElementById('atlas-requirement-input')?.value || '',
    atlasRequirementStatus: document.getElementById('atlas-requirement-status')?.textContent || '',
    planFetchState: (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.workflowPhase || '',
    currentJobId: (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.currentJobId || '',
    currentRunId: (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.currentRunId || (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.lastRunId || '',
    jobStatus: (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.jobStatus || '',
    workflowPhase: (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.workflowPhase || '',
    planId: (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.planId || '',
    lastPlanApiIds: (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.lastPlanApiIds || {},
    hasGeneratedPlanState: !!((typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.generatedPlan || (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.planMarkdown || (typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.planResult),
    approveButtonsPresent: !!document.querySelector("#approve-plan-btn, [data-action='approve-plan']"),
    executeButtonsPresent: !!document.querySelector("#execute-preview-btn, [data-action='execute-preview']"),
    patchApplyButtonsPresent: !!document.querySelector("#apply-patch-btn, [data-action='apply-patch']"),
    lastError: String((typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.lastError || document.getElementById('atlas-workflow-status')?.dataset?.lastError || document.getElementById('atlas-workflow-last-error')?.dataset?.lastErrorValue || '').trim(),
    approvalPanelVisible: !!document.querySelector('[data-atlas-workflow-target=\"dynamic-approval\"], [data-atlas-workflow-target=\"approval\"]'),
    approvalButtonsActionable: !!Array.from(document.querySelectorAll('#atlas-workbench-card button')).find((el) => /approve|承認/i.test(el.textContent || '') && !el.disabled),
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
  plan_tail = plan_flow_text[-2000:]
  last_error = str(atlas_data.get("lastError") or "").strip()
  if last_error == "-":
    last_error = ""
  if not current_job_id:
    current_job_id = str(atlas_data.get("currentJobId") or "")
  inferred_active_job_id = ""
  if isinstance(jobs_resp, dict):
    jobs_json = jobs_resp.get("json") if isinstance(jobs_resp.get("json"), dict) else {}
    for j in jobs_json.get("jobs", []):
      if isinstance(j, dict) and j.get("id"):
        inferred_active_job_id = str(j.get("id"))
        break
  return {
    "baseUrl": base_url,
    "preflightStatus": preflight_status,
    **atlas_data,
    "atlasWorkflowStatusTextTail": status_tail,
    "planFlowTextTail": plan_tail,
    "planFlowFullText": plan_flow_text[-6000:],
    "syncPlanPendingDetected": str(current_job_id) == "sync-plan-pending",
    "atlasRequirementStatus": str(atlas_data.get("atlasRequirementStatus") or ""),
    "messagesTail": messages_tail,
    "lastError": last_error or "-",
    "activeJobsResponse": _truncate_json(jobs_resp),
    "recentJobsResponse": _truncate_json(history_resp),
    "currentJobId": current_job_id,
    "uiCurrentJobId": str(atlas_data.get("currentJobId") or ""),
    "inferredActiveJobId": inferred_active_job_id,
    "currentRunId": str(atlas_data.get("currentRunId") or ""),
    "apiAtlasJobId": str((atlas_data.get("lastPlanApiIds") or {}).get("atlas_job_id") or "") if isinstance(atlas_data.get("lastPlanApiIds"), dict) else "",
    "apiAtlasRunId": str((atlas_data.get("lastPlanApiIds") or {}).get("atlas_run_id") or "") if isinstance(atlas_data.get("lastPlanApiIds"), dict) else "",
    "planGeneratedStatePresent": bool(atlas_data.get("hasGeneratedPlanState") or atlas_data.get("planId")),
    "elapsedMs": elapsed_ms,
    "finalDecision": final_decision,
  }


async def _write_atlas_lifecycle_snapshot(diag: dict, label: str) -> None:
  try:
    PLAYWRIGHT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "snapshot"
    path = PLAYWRIGHT_ARTIFACT_DIR / f"atlas_lifecycle_{safe_label}.json"
    path.write_text(json.dumps(diag, ensure_ascii=False, indent=2), encoding="utf-8")
  except Exception:
    pass



def compact_atlas_diag_reason(diag: dict, *, prefix: str = "atlas wait-plan failed") -> str:
  final_decision = str(diag.get("finalDecision") or "unknown")
  reason = str(diag.get("completionDecisionReason") or "unknown")
  failure_signals = diag.get("failureSignals", [])
  if not isinstance(failure_signals, list):
    failure_signals = [str(failure_signals)]
  current_job_id = str(diag.get("currentJobId") or "") or "-"
  current_run_id = str(diag.get("currentRunId") or "") or "-"
  last_error = str(diag.get("lastError") or "-").strip() or "-"
  if len(last_error) > 120:
    last_error = last_error[:119].rstrip() + "…"
  signal_text = ",".join(str(x) for x in failure_signals[:4]) or "-"
  return (
    f"{prefix}: {reason}; final={final_decision}; "
    f"signals={signal_text}; currentJobId={current_job_id}; currentRunId={current_run_id}; "
    f"lastError={last_error}; artifact=atlas_lifecycle_final.json"
  )

def raise_compact_atlas_diag(diag: dict, *, prefix: str = "atlas wait-plan failed") -> None:
  raise AssertionError(compact_atlas_diag_reason(diag, prefix=prefix))

async def wait_atlas_plan_completion(page, timeout_ms=180000, preflight_status=None, base_url: str = "", console_errors=None, page_errors=None) -> dict:
  console_errors = console_errors or []
  page_errors = page_errors or []
  started = time.perf_counter()
  final = "timeout"
  last_diag: dict = {}
  next_snapshot_ms = 0
  saw_current_job = False
  no_job_fail_after_ms = 8000
  missing_job_fail_after_ms = 12000

  while (time.perf_counter() - started) * 1000 < timeout_ms:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    diag = await collect_atlas_job_lifecycle_diag(page, preflight_status=preflight_status, base_url=base_url, elapsed_ms=elapsed_ms)
    diag["consoleErrors"] = list(console_errors)
    diag["pageErrors"] = list(page_errors)
    raw_haystack = "\n".join([diag.get("atlasWorkflowStatusTextTail", ""), diag.get("planFlowTextTail", ""), "\n".join(diag.get("messagesTail", []))])
    normalized_haystack = " ".join(raw_haystack.replace("•", " ").replace("\t", " ").lower().split())
    haystack = normalized_haystack.replace(":", ": ").replace("  ", " ")
    last_error = str(diag.get("lastError", "-") or "-").strip()
    current_job_id = str(diag.get("currentJobId") or "").strip()
    current_run_id = str(diag.get("currentRunId") or "").strip()
    if current_job_id:
      saw_current_job = True

    active_jobs = diag.get("activeJobsResponse", {}) if isinstance(diag.get("activeJobsResponse"), dict) else {}
    active_jobs_json = active_jobs.get("json") if isinstance(active_jobs.get("json"), dict) else {}
    active_jobs_list = [j for j in active_jobs_json.get("jobs", []) if isinstance(j, dict)]
    active_jobs_available = bool(active_jobs_list)
    # contract markers:
    # plan_flow_requirement_done / plan_flow_plan_generated / plan_flow_review_done
    backend_done_statuses = {"succeeded", "completed", "done", "success"}
    active_statuses = [str(j.get("status", "")).strip().lower() for j in active_jobs_list]
    active_failed = any(st in {"failed", "error", "cancelled", "canceled"} for st in active_statuses)
    current_job_active = bool(current_job_id and any(str(j.get("id") or "") == current_job_id for j in active_jobs_list))
    sync_job = current_job_id.startswith("sync-")
    concrete_sync_job = bool(current_job_id and current_job_id != "sync-plan-pending" and (current_job_id.startswith("sync-plan:") or not current_job_id.startswith("sync-plan")))

    plan_flow_requirements = {
      "plan_flow_requirement_done": "requirement: done",
      "plan_flow_requirement_ready": "requirement: ready",
      "plan_flow_plan_generated": "plan: generated",
      "plan_flow_review_done": "review: done",
      "plan_flow_review_ready": "review: ready",
    }
    legacy_plan_flow_aliases = {
      "plan_flow_requirement_ready": ["requirement: done"],
      "plan_flow_review_ready": ["review: ready", "review: required"],
    }
    matched_plan_flow = []
    for name, token in plan_flow_requirements.items():
      aliases = legacy_plan_flow_aliases.get(name, [])
      if token in haystack or any(alias in haystack for alias in aliases):
        matched_plan_flow.append(name)
    missing_plan_flow = [name for name in plan_flow_requirements if name not in matched_plan_flow]
    pending_signals = [token for token in ["plan: pending", "review: pending", "requirement: pending"] if token in haystack]
    contradictory_signals = []
    if "plan: pending" in haystack and "approval: required" in haystack:
      contradictory_signals.append("plan_pending_approval_required")
    if "plan: pending" in haystack and "patch review: available" in haystack:
      contradictory_signals.append("plan_pending_patch_review_available")
    if "requirement: pending" in haystack and "approval: required" in haystack:
      contradictory_signals.append("requirement_pending_approval_required")

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
    clarification_signals = [name for name, token in clarification_signal_tokens.items() if token in haystack]

    failure_signals = []
    if "atlas start failed:" in haystack or "atlas start failed" in haystack:
      failure_signals.append("atlas_start_failed")
    if last_error not in ("", "-"):
      failure_signals.append("last_error_present")
    explicit_failure_text = any(token in haystack for token in ["plan: failed", " status: failed", " exception", "atlas start failed"])
    explicit_error_text = any(token in haystack for token in ["api exception", "request failed", "uncaught error", "job error"])
    if explicit_failure_text or explicit_error_text:
      failure_signals.append("failed_text_detected")
    if active_failed:
      failure_signals.append("backend_failed_status")
    if contradictory_signals:
      failure_signals.extend(contradictory_signals)

    diag.update({
      "currentJobId": current_job_id,
      "currentRunId": current_run_id,
      "completionSignals": matched_plan_flow,
      "pendingSignals": pending_signals,
      "backendJobStatuses": active_statuses,
      "failureSignals": failure_signals,
      "normalizedPlanFlowText": haystack,
      "matchedCompletionSignals": matched_plan_flow,
      "missingCompletionSignals": missing_plan_flow,
      "clarificationSignals": clarification_signals,
      "completionDecisionReason": "in_progress",
    })

    if elapsed_ms >= next_snapshot_ms:
      await _write_atlas_lifecycle_snapshot(diag, f"{elapsed_ms}ms")
      next_snapshot_ms += 30000

    if failure_signals:
      final = "failed"
      reason = "last_error_present" if "last_error_present" in failure_signals else "failure_signal_detected"
      last_diag = {**diag, "finalDecision": final, "completionDecisionReason": reason}
      break

    has_plan_marker = ("plan: generated" in haystack)
    has_activity_marker = "plan_generated" in haystack
    has_state_plan = bool(diag.get('planId') or current_run_id)
    backend_status_hit = any(tok in haystack for tok in ["planned", "needs_confirmation", "needs_revision", "rejected"])
    has_completion_signal = bool(has_plan_marker or has_activity_marker or has_state_plan or backend_status_hit)
    if has_completion_signal and not active_jobs_available:
      diag["completionDecisionReason"] = "has_completion_signal and not active_jobs_available"
    if has_completion_signal and last_error in ("", "-") and current_job_id != "sync-plan-pending":
      final = "completed"
      last_diag = {**diag, "finalDecision": final, "completionDecisionReason": "plan_generated_review_ready"}
      break

    if clarification_signals and "plan: pending" in haystack and last_error in ("", "-"):
      final = "needs_clarification"
      last_diag = {**diag, "finalDecision": final, "completionDecisionReason": "clarification_required_before_plan_generation"}
      break

    if elapsed_ms >= no_job_fail_after_ms and not saw_current_job:
      final = "failed"
      last_diag = {**diag, "finalDecision": final, "completionDecisionReason": "no_current_job_id_or_sync_plan_id"}
      break

    # do not fail just because backend jobs list is empty
    if elapsed_ms >= missing_job_fail_after_ms and current_job_id and not sync_job and active_jobs.get("ok") and active_jobs_list and not current_job_active and "plan: generated" not in haystack:
      final = "failed"
      last_diag = {**diag, "finalDecision": final, "completionDecisionReason": "current_job_missing_from_active_jobs_without_plan"}
      break


    if current_job_id == "sync-plan-pending" and has_plan_marker:
      diag["completionDecisionReason"] = "sync_plan_pending_after_generation"
    elif current_job_id == "sync-plan-pending":
      diag["completionDecisionReason"] = "sync_plan_pending_waiting"
    elif pending_signals:
      diag["completionDecisionReason"] = "pending_plan_detected"
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
    last_diag.setdefault("missingCompletionSignals", ["plan_flow_requirement_ready", "plan_flow_plan_generated", "plan_flow_review_ready"])
    last_diag["completionDecisionReason"] = "sync_plan_pending_timeout" if str(last_diag.get("currentJobId") or "") == "sync-plan-pending" else last_diag.get("completionDecisionReason", "timeout_without_completion")
    if not str(last_diag.get("lastError") or "").strip():
      last_diag["lastError"] = "sync_plan_timeout: pending_not_resolved"
  last_diag["finalDecision"] = final if final != "timeout" else last_diag.get("finalDecision", "timeout")
  await _write_atlas_lifecycle_snapshot(last_diag, "final")
  return last_diag


async def collect_atlas_clarification_diag(page) -> dict:
  return await page.evaluate("""() => ({
    clarificationInputPresent: !!document.querySelector("#atlas-clarification-input, textarea[name='clarification'], textarea#clarification-answer"),
    answerAndGenerateButtonPresent: !!Array.from(document.querySelectorAll('#atlas-workbench-card button, #atlas-workbench-card [role="button"]')).find((el) => (el.textContent || '').includes('回答してPlan生成')),
    proceedWithAssumptionsButtonPresent: !!Array.from(document.querySelectorAll('#atlas-workbench-card button, #atlas-workbench-card [role="button"]')).find((el) => (el.textContent || '').includes('おまかせで進める')),
    clarificationSignals: {
      nextActionAnswerClarification: (document.getElementById('atlas-workbench-card-plan-flow')?.textContent || '').includes('Next Action: answer clarification'),
      clarificationKeyword: (document.getElementById('atlas-workbench-card-plan-flow')?.textContent || '').toLowerCase().includes('clarification'),
    },
    planFlowTextTail: (document.getElementById('atlas-workbench-card-plan-flow')?.textContent || '').slice(-800),
    messagesTail: Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || '').slice(-240)).slice(-10),
    approveButtonsPresent: !!document.querySelector("#approve-plan-btn, [data-action='approve-plan']"),
    executeButtonsPresent: !!document.querySelector("#execute-preview-btn, [data-action='execute-preview']"),
    patchApplyButtonsPresent: !!document.querySelector("#apply-patch-btn, [data-action='apply-patch']"),
    lastError: String((typeof planWorkflowState !== 'undefined' ? planWorkflowState : {})?.lastError || document.getElementById('atlas-workflow-status')?.dataset?.lastError || document.getElementById('atlas-workflow-last-error')?.dataset?.lastErrorValue || '').trim(),
    approvalPanelVisible: !!document.querySelector('[data-atlas-workflow-target=\"dynamic-approval\"], [data-atlas-workflow-target=\"approval\"]'),
    approvalButtonsActionable: !!Array.from(document.querySelectorAll('#atlas-workbench-card button')).find((el) => /approve|承認/i.test(el.textContent || '') && !el.disabled),
  })""")


async def collect_atlas_plan_approval_gate_diag(page) -> dict:
  return await page.evaluate("""() => {
    try {
    const statusText = document.getElementById('atlas-workflow-status')?.textContent || document.getElementById('atlas-workbench-status')?.textContent || '';
    const flowText = document.getElementById('atlas-workbench-card-plan-flow')?.textContent || '';
    const messages = Array.from(document.querySelectorAll('#messages .msg')).map((el) => (el.textContent || ''));
    const approvalCard = document.querySelector('#plan-approval-card, [data-atlas-workflow-target=\"dynamic-approval\"], [data-atlas-workflow-target=\"approval\"]');
    const selectorErrors = [];
    const approveSelectorCandidates = [
      '#approve-plan-btn',
      '[data-action=\"approve-plan\"]',
      '#plan-approval-card [data-a=\"approve\"]',
      '#plan-approval-card button.phase1-plan-btn[data-a=\"approve\"]',
      '#atlas-workbench-card [data-action*=\"approve\"]',
      '#atlas-workbench-card [data-a*=\"approve\"]',
      '#atlas-workbench-card [id*=\"approve\"]',
      '#atlas-workbench-card [class*=\"approve\"]',
    ];
    const approveTextCandidates = [
      'approve',
      'approve plan',
      'plan approve',
      'approve_plan',
      '承認',
      '計画を承認',
      'planを承認',
      'プランを承認',
      '承認して続行',
    ];
    const isVisibleIsh = (el) => {
      if (!el) return false;
      const style = window.getComputedStyle(el);
      if (!style) return false;
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || '1') <= 0) return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const buttonSelectorScopes = [
      '#atlas-workbench-card button',
      '#atlas-workbench-card [role=\"button\"]',
      '#plan-approval-card button',
      '[data-atlas-workflow-target] button',
      '[data-a]',
      '[data-action]',
    ];
    const allButtonElements = Array.from(new Set(buttonSelectorScopes.flatMap((sel) => {
      try {
        return Array.from(document.querySelectorAll(sel));
      } catch (error) {
        selectorErrors.push({ selector: sel, error: String(error) });
        return [];
      }
    })));
    const buttonInventory = allButtonElements.map((el) => ({
      text: (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 200),
      id: el.id || '',
      className: String(el.className || '').slice(0, 300),
      disabled: !!el.disabled,
      ariaLabel: (el.getAttribute('aria-label') || '').slice(0, 200),
      title: (el.getAttribute('title') || '').slice(0, 200),
      dataAction: (el.getAttribute('data-action') || '').slice(0, 120),
      dataA: (el.getAttribute('data-a') || '').slice(0, 120),
      dataAtlasWorkflowTarget: (el.getAttribute('data-atlas-workflow-target') || '').slice(0, 120),
      visibleIsh: isVisibleIsh(el),
    }));
    const approvalCandidateButtons = buttonInventory.filter((b) => {
      const corpus = `${b.text} ${b.id} ${b.className} ${b.ariaLabel} ${b.title} ${b.dataAction} ${b.dataA}`.toLowerCase();
      return approveTextCandidates.some((token) => corpus.includes(token.toLowerCase())) || /approve/.test(corpus);
    });
    const destructiveCandidateButtons = buttonInventory.filter((b) => {
      const corpus = `${b.text} ${b.id} ${b.className} ${b.ariaLabel} ${b.title} ${b.dataAction} ${b.dataA}`.toLowerCase();
      return /execute|apply\\s+patch|apply|approve|承認|bulk/.test(corpus);
    });
    const approveButton = approveSelectorCandidates.map((sel) => {
      try {
        return document.querySelector(sel);
      } catch (error) {
        selectorErrors.push({ selector: sel, error: String(error) });
        return null;
      }
    }).find((el) => !!el)
      || allButtonElements.find((el) => {
        const corpus = `${el.textContent || ''} ${el.id || ''} ${el.className || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''} ${el.getAttribute('data-action') || ''} ${el.getAttribute('data-a') || ''}`.toLowerCase();
        return approveTextCandidates.some((token) => corpus.includes(token.toLowerCase()));
      })
      || null;
    const executeButton = document.querySelector('#execute-preview-btn, [data-action=\"execute-preview\"], #plan-approval-card [data-a=\"execute-preview\"]');
    const patchApplyButtons = Array.from(document.querySelectorAll('button')).filter((el) => /apply\\s+approved\\s+patch|apply\\s+patch/i.test(el.textContent || ''));
    const patchCards = Array.from(document.querySelectorAll('[id*=\"patch-\"], [data-pa]'));
    const patchCountText = (document.getElementById('patch-review-count')?.textContent || '').trim();
    const approvalStatusLine = (flowText.split('\\n').find((line) => /approval\\s*:/i.test(line)) || '').trim();
    const planGenerated = /plan\\s*:\\s*(generated|ready|completed)/i.test(flowText);
    const reviewDone = /review\\s*:\\s*(done|ready|required)/i.test(flowText);
    const approvalRequired = /approval\\s*:\\s*required/i.test(flowText);
    const execute_preview_locked = !executeButton || !!executeButton.disabled || /locked|approval/i.test(executeButton.textContent || '');
    const patchApplyLocked = patchApplyButtons.length === 0 || patchApplyButtons.every((btn) => !!btn.disabled);
    return {
      atlasSubview: document.getElementById('atlas-workbench-card')?.dataset?.atlasCurrentSubview || '',
      planApprovalGatePresent: !!approvalCard || /approval\\s*:\\s*required/i.test(flowText),
      approveButtonPresent: !!approveButton,
      approveButtonEnabled: !!approveButton && !approveButton.disabled,
      approvalStatusText: approvalStatusLine || statusText.slice(-240),
      planGenerated,
      reviewDone,
      execute_preview_locked,
      execute_preview_locked: execute_preview_locked,
      patchApplyLocked,
      patchCount: patchCountText || String(patchCards.length),
      planTextTail: flowText.slice(-800),
      reviewTextTail: messages.join('\\n').slice(-800),
      nextAction: ((flowText.match(/next\\s*action\\s*:\\s*([^\\n]+)/i) || [])[1] || '').trim(),
      consoleErrors: [],
      pageErrors: [],
      destructiveActionDetected: false,
      planFlowTextTail: flowText.slice(-800),
      messagesTail: messages.slice(-10).map((text) => String(text).slice(-240)),
      approvalRequired,
      allButtons: buttonInventory,
      approvalCandidateButtons,
      destructiveCandidateButtons,
      approvalPanelTextTail: (approvalCard?.textContent || '').slice(-1000),
      workbenchTextTail: (document.getElementById('atlas-workbench-card')?.textContent || '').slice(-1000),
      workbenchHtmlTail: (document.getElementById('atlas-workbench-card')?.innerHTML || '').slice(-1000),
      approveSelectorCandidates,
      diagnosticError: "",
      selectorErrors,
      failureReason: "",
    };
    } catch (error) {
      return {
        diagnosticError: String(error),
        allButtons: [],
        approvalCandidateButtons: [],
        destructiveCandidateButtons: [],
        approvalPanelTextTail: "",
        workbenchTextTail: "",
        selectorErrors: [],
        failureReason: "",
      };
    }
  }""")


async def verify_atlas_plan_approval_gate_readiness(page, wait_diag: dict, console_errors: list[str], page_errors: list[str]) -> dict:
  final_decision = str(wait_diag.get("finalDecision") or "unknown")
  if final_decision in ("needs_clarification", "needs_clarification_after_resolution"):
    return {
      "finalDecision": final_decision,
      "completionDecisionReason": wait_diag.get("completionDecisionReason", ""),
      "consoleErrors": list(console_errors),
      "pageErrors": list(page_errors),
      "destructiveActionDetected": False,
      "skippedReason": "plan_approval_gate_skipped_needs_clarification",
      "diagnosticError": "",
      "allButtons": [],
      "approvalCandidateButtons": [],
      "destructiveCandidateButtons": [],
      "approvalPanelTextTail": "",
      "workbenchTextTail": "",
      "selectorErrors": [],
    }
  if final_decision != "completed":
    dep_diag = {**wait_diag, "finalDecision": final_decision, "completionDecisionReason": wait_diag.get("completionDecisionReason", "wait_plan_failed")}
    current_job = str(wait_diag.get("currentJobId") or "")
    if current_job.startswith("sync-plan:req_") or current_job.startswith("sync-requirement:") or wait_diag.get("completionDecisionReason") == "pending_plan_detected":
      dep_diag["completionDecisionReason"] = "dependency_failed:no_plan_generated"
    raise AssertionError(compact_atlas_diag_reason(dep_diag, prefix="plan approval gate failed: wait_plan_failed"))
  gate_diag = await collect_atlas_plan_approval_gate_diag(page)
  gate_diag["finalDecision"] = final_decision
  gate_diag["completionDecisionReason"] = wait_diag.get("completionDecisionReason", "")
  gate_diag["consoleErrors"] = list(console_errors)
  gate_diag["pageErrors"] = list(page_errors)
  gate_diag["destructiveActionDetected"] = False
  gate_diag["skippedReason"] = ""
  if console_errors or page_errors:
    raise AssertionError("plan approval gate failed: page_or_console_errors; artifact=atlas_lifecycle_final.json")
  if not gate_diag.get("planApprovalGatePresent"):
    raise AssertionError("plan approval gate failed: no_approval_required_signal; artifact=atlas_lifecycle_final.json")
  if not gate_diag.get("approveButtonPresent"):
    gate_diag["failureReason"] = "approval_required_but_approve_button_missing"
    raise AssertionError("plan approval gate failed: approval_button_missing; artifact=atlas_lifecycle_final.json")
  if not gate_diag.get("execute_preview_locked"):
    raise AssertionError("plan approval gate failed: execute_preview_unlocked_before_approval; artifact=atlas_lifecycle_final.json")
  if not gate_diag.get("patchApplyLocked"):
    raise AssertionError("plan approval gate failed: patch_apply_unlocked_before_approval; artifact=atlas_lifecycle_final.json")
  if not (gate_diag.get("planGenerated") and gate_diag.get("reviewDone") and gate_diag.get("approvalRequired")):
    raise AssertionError("plan approval gate failed: plan_review_approval_signals_inconsistent; artifact=atlas_lifecycle_final.json")
  return gate_diag


async def open_atlas_approval_panel_for_inspection(page) -> dict:
  # Contract marker: inspect the "Open Approval Panel" affordance only; do not approve.
  return await page.evaluate("""() => {
    const isVisibleIsh = (el) => {
      if (!el) return false;
      const style = window.getComputedStyle(el);
      if (!style) return false;
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || '1') <= 0) return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const approvalPanel = document.querySelector('#plan-approval-card, [data-atlas-workflow-target="dynamic-approval"], [data-atlas-workflow-target="approval"]');
    const approvalPanelAlreadyVisible = isVisibleIsh(approvalPanel || null);
    const allButtons = Array.from(document.querySelectorAll('#atlas-workbench-card button, #atlas-workbench-card [role="button"]'));
    const openButton = allButtons.find((el) => /open\s+approval\s+panel/i.test((el.textContent || '').trim()));
    const beforePresent = approvalPanelAlreadyVisible || !!openButton;
    const beforeVisible = approvalPanelAlreadyVisible || isVisibleIsh(openButton || null);
    let clicked = false;
    if (!approvalPanelAlreadyVisible && openButton && !openButton.disabled) {
      openButton.click();
      clicked = true;
    }
    const visiblePanel = document.querySelector('#plan-approval-card, [data-atlas-workflow-target="dynamic-approval"], [data-atlas-workflow-target="approval"]');
    const approvalPanelVisible = approvalPanelAlreadyVisible || isVisibleIsh(visiblePanel || null);
    return {
      openApprovalPanelButtonPresent: beforePresent,
      openApprovalPanelButtonVisible: beforeVisible,
      openApprovalPanelClicked: approvalPanelAlreadyVisible || clicked,
      approvalPanelVisible,
    };
  }""")


async def collect_atlas_approval_panel_actionability_diag(page) -> dict:
  return await page.evaluate("""() => {
    const isVisibleIsh = (el) => {
      if (!el) return false;
      const style = window.getComputedStyle(el);
      if (!style) return false;
      if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || '1') <= 0) return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const allButtons = Array.from(document.querySelectorAll('#atlas-workbench-card button, #atlas-workbench-card [role="button"], #plan-approval-card button'));
    const inventory = allButtons.map((el) => ({
      text: (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 200),
      id: el.id || '',
      dataAction: el.getAttribute('data-action') || '',
      dataA: el.getAttribute('data-a') || '',
      disabled: !!el.disabled,
      visibleIsh: isVisibleIsh(el),
    }));
    const corpusFor = (b) => `${b.text} ${b.id} ${b.dataAction} ${b.dataA}`.toLowerCase();
    const approveButton = inventory.find((b) => /approve|承認/.test(corpusFor(b)));
    const requestRevisionButton = inventory.find((b) => /request\\s+revision|revision|修正/.test(corpusFor(b)));
    const rejectButton = inventory.find((b) => /reject|却下/.test(corpusFor(b)));
    const executeButton = inventory.find((b) => /execute\\s+preview/.test(corpusFor(b)));
    const patchApplyButton = inventory.find((b) => /apply\\s+approved\\s+patch|apply\\s+patch/.test(corpusFor(b)));
    const approvalPanel = document.querySelector('#plan-approval-card, [data-atlas-workflow-target="dynamic-approval"], [data-atlas-workflow-target="approval"]');
    const approveButtonActionableCandidate = !!approveButton && !!approveButton.visibleIsh && !approveButton.disabled && /approve|承認/.test(corpusFor(approveButton));
    return {
      approvalPanelVisible: isVisibleIsh(approvalPanel || null),
      approveButtonPresent: !!approveButton,
      approveButtonVisible: !!approveButton && !!approveButton.visibleIsh,
      approveButtonEnabled: !!approveButton && !approveButton.disabled,
      approveButtonActionableCandidate,
      requestRevisionButtonPresent: !!requestRevisionButton,
      rejectButtonPresent: !!rejectButton,
      execute_preview_locked: !executeButton || !!executeButton.disabled,
      patchApplyLocked: !patchApplyButton || !!patchApplyButton.disabled,
      approvalPanelTextTail: (approvalPanel?.textContent || '').slice(-1000),
      allButtonsAfterOpen: inventory,
      approvalCandidateButtonsAfterOpen: inventory.filter((b) => /approve|承認/.test(corpusFor(b))),
      destructiveActionDetected: false,
    };
  }""")


async def verify_atlas_plan_approval_actionability(page, wait_diag: dict, console_errors: list[str], page_errors: list[str]) -> dict:
  seed = await load_debug_seed_plan(page)
  await open_atlas(page)
  await page.evaluate("""(seed) => {
    if (typeof window.__atlasApplyDebugSeedPlanForTests !== 'function') {
      throw new Error('missing __atlasApplyDebugSeedPlanForTests');
    }
    window.__atlasApplyDebugSeedPlanForTests(seed);
  }""", seed)
  gate_diag_before_open = await collect_atlas_plan_approval_gate_diag(page)
  open_diag = await open_atlas_approval_panel_for_inspection(page)
  action_diag = await collect_atlas_approval_panel_actionability_diag(page)
  diag = {
    "finalDecision": "completed",
    "completionDecisionReason": "debug_seed_plan_applied",
    "gateDiagBeforeOpen": gate_diag_before_open,
    "actionabilityDiagAfterOpen": action_diag,
    **open_diag,
    **action_diag,
    "skippedReason": "",
    "destructiveActionDetected": False,
    "consoleErrors": list(console_errors),
    "pageErrors": list(page_errors),
  }
  if console_errors or page_errors:
    raise AssertionError("plan approval actionability failed: page_or_console_errors; artifact=atlas_lifecycle_final.json")
  if not diag.get("openApprovalPanelButtonPresent"):
    raise AssertionError("plan approval actionability failed: open_approval_panel_button_missing; artifact=atlas_lifecycle_final.json")
  if not diag.get("openApprovalPanelClicked"):
    raise AssertionError("plan approval actionability failed: open_approval_panel_not_actionable; artifact=atlas_lifecycle_final.json")
  if not diag.get("approvalPanelVisible"):
    raise AssertionError("plan approval actionability failed: approval_panel_not_visible; artifact=atlas_lifecycle_final.json")
  if not diag.get("approveButtonActionableCandidate"):
    raise AssertionError("plan approval actionability failed: approve_button_not_actionable_candidate; artifact=atlas_lifecycle_final.json")
  if not diag.get("execute_preview_locked"):
    raise AssertionError("plan approval actionability failed: execute_preview_unlocked_before_approval; artifact=atlas_lifecycle_final.json")
  if not diag.get("patchApplyLocked"):
    raise AssertionError("plan approval actionability failed: patch_apply_unlocked_before_approval; artifact=atlas_lifecycle_final.json")
  await assert_no_atlas_chat_leak(page, "plan_approval_actionability")
  return diag


def is_generated_plan_diag(diag: dict) -> bool:
  current_job = str(diag.get("currentJobId") or "")
  current_run = str(diag.get("currentRunId") or "")
  plan_id = str(diag.get("planId") or diag.get("plan_id") or "")
  final = str(diag.get("final") or diag.get("finalDecision") or "")
  workflow_phase = str(diag.get("workflowPhase") or "").strip().lower()
  last_error = str(diag.get("lastError") or "").strip()
  if last_error and last_error != "-":
    return False
  if current_job.startswith("sync-plan:req_") or current_run.startswith("req_"):
    return False
  if current_job == "sync-plan-pending":
    return False
  if workflow_phase == "waiting_for_clarification":
    return False
  if diag.get("planGenerated") is True or diag.get("plan_generated") is True:
    if plan_id.startswith("plan_") or current_run.startswith("plan_") or current_job.startswith("sync-plan:plan_"):
      return True
  if plan_id.startswith("plan_") or current_run.startswith("plan_") or current_job.startswith("sync-plan:plan_"):
    return True
  if final == "completed" and current_job.startswith("sync-plan:plan_"):
    return True
  if workflow_phase in {"plan_generated", "review_ready", "completed"}:
    return True
  if diag.get("generatedPlan") or diag.get("planMarkdown") or diag.get("planResult"):
    return True
  return False


async def verify_atlas_plan_api_contract(page) -> None:
  base_url = os.environ.get("PLAYWRIGHT_SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
  payload = {"input": ATLAS_APPROVAL_STABLE_PROMPT, "project_name": "default", "planning_mode": "standard", "requirement_mode": "ask_when_needed", "execution_mode": "plan_only", "use_nexus": True}
  res = await page.request.post(f"{base_url}/api/task/plan", data=payload, timeout=45_000)
  body = await res.json()
  keys = sorted(body.keys())
  status = str(body.get("status") or body.get("job_status") or "").strip().lower()
  plan_id = str(body.get("plan_id") or "").strip()
  requirement_id = str(body.get("requirement_id") or "").strip()
  atlas_job_id = str(body.get("atlas_job_id") or "").strip()
  atlas_run_id = str(body.get("atlas_run_id") or "").strip()
  atlas_requirement_job_id = str(body.get("atlas_requirement_job_id") or "").strip()
  plan_generated = body.get("plan_generated") is True
  has_error = bool(body.get("error")) or body.get("ok") is False
  if atlas_job_id.startswith("sync-plan:req_") or atlas_run_id.startswith("req_"):
    raise AssertionError(f"atlas_plan_api_contract failed: requirement_id_leak keys={keys}")
  if status == "waiting_for_clarification":
    if (not requirement_id.startswith("req_")) or plan_generated or plan_id or atlas_job_id or atlas_run_id:
      raise AssertionError(f"atlas_plan_api_contract failed: clarification_contract_mismatch keys={keys}")
    if atlas_requirement_job_id != f"sync-requirement:{requirement_id}":
      raise AssertionError(f"atlas_plan_api_contract failed: clarification_requirement_job_mismatch keys={keys}")
  elif has_error:
    if plan_generated or plan_id:
      raise AssertionError(f"atlas_plan_api_contract failed: failure_contract_mismatch keys={keys}")
  else:
    if (not plan_generated) or (not plan_id.startswith("plan_")):
      raise AssertionError(f"atlas_plan_api_contract failed: success_contract_mismatch keys={keys}")
    if atlas_job_id != f"sync-plan:{plan_id}" or atlas_run_id != plan_id:
      raise AssertionError(f"atlas_plan_api_contract failed: success_id_contract_mismatch keys={keys}")


async def load_debug_seed_plan(page) -> dict:
  base_url = os.environ.get("PLAYWRIGHT_SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
  res = await page.request.post(f"{base_url}/api/debug/atlas/seed-plan", timeout=15_000)
  if res.status in {403, 404}:
    raise AssertionError("plan approval actionability failed: debug_seed_unavailable")
  data = await res.json()
  if not isinstance(data, dict) or data.get("ok") is not True:
    raise AssertionError("plan approval actionability failed: debug_seed_invalid_response")
  return data


async def load_debug_seed_clarification(page) -> dict:
  base_url = os.environ.get("PLAYWRIGHT_SMOKE_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
  res = await page.request.post(f"{base_url}/api/debug/atlas/seed-clarification", timeout=15_000)
  if res.status in {403, 404}:
    raise AssertionError("clarification resolution failed: debug_seed_unavailable")
  data = await res.json()
  if not isinstance(data, dict) or data.get("ok") is not True:
    raise AssertionError("clarification resolution failed: debug_seed_invalid_response")
  return data


def has_requirement_id_leak_in_plan_lifecycle(diag: dict) -> bool:
  current_job = str(diag.get("currentJobId") or "").strip()
  current_run = str(diag.get("currentRunId") or "").strip()
  return current_job.startswith("sync-plan:req_") or current_run.startswith("req_")


async def prepare_generated_plan(
  page,
  *,
  prompt: str,
  preflight_status: dict,
  base_url: str,
  console_errors: list[str],
  page_errors: list[str],
) -> dict:
  await start_atlas_backend_e2e_journey(page, prompt)
  await page.wait_for_function(
    "() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'plan'",
    timeout=30_000,
  )
  diag = await wait_atlas_plan_completion(
    page,
    timeout_ms=45000,
    preflight_status=preflight_status,
    base_url=base_url,
    console_errors=console_errors,
    page_errors=page_errors,
  )
  if not is_generated_plan_diag(diag):
    reason = "plan_generated_false"
    workflow_phase = str(diag.get("workflowPhase") or "").strip().lower()
    plan_id = str(diag.get("planId") or diag.get("plan_id") or "").strip()
    last_error = str(diag.get("lastError") or "").strip()
    completion_reason = str(diag.get("completionDecisionReason") or "").strip()
    if workflow_phase in {"waiting_for_clarification", "requirement_ready"} and not plan_id:
      reason = "plan_generated_false+waiting_for_clarification"
    elif "api_task_plan_http_error" in last_error:
      reason = "plan_generated_false+api_task_plan_http_error"
    elif "api_task_plan_exception" in last_error:
      reason = "plan_generated_false+api_task_plan_exception"
    elif completion_reason == "sync_plan_pending_timeout":
      reason = "plan_generated_false+sync_plan_pending_timeout"
    elif has_requirement_id_leak_in_plan_lifecycle(diag):
      reason = "plan_generated_false+requirement_id_leaked_into_plan_lifecycle"
    dep_diag = {**diag, "completionDecisionReason": reason}
    raise AssertionError(compact_atlas_diag_reason(dep_diag, prefix="atlas wait-plan failed"))
  return diag


async def prepare_generated_plan_for_approval_tests(
  page,
  *,
  preflight_status: dict,
  base_url: str,
  console_errors: list[str],
  page_errors: list[str],
) -> dict:
  diag = await prepare_generated_plan(
    page,
    prompt=ATLAS_APPROVAL_STABLE_PROMPT,
    preflight_status=preflight_status,
    base_url=base_url,
    console_errors=console_errors,
    page_errors=page_errors,
  )
  await set_atlas_subview(page, "review")
  return diag


async def prepare_seeded_review_ready_plan(page) -> dict:
  seed = await load_debug_seed_plan(page)
  await open_atlas(page)
  await set_atlas_subview(page, "plan")
  await page.evaluate("""(seed) => {
    if (typeof window.__atlasApplyDebugSeedPlanForTests !== 'function') throw new Error('missing_debug_seed_hook');
    window.__atlasApplyDebugSeedPlanForTests(seed);
  }""", seed)
  await set_atlas_subview(page, "review")
  return seed


async def click_atlas_proceed_with_assumptions_once(page) -> tuple[bool, str]:
  selectors = [
    "#atlas-workbench-card button:has-text('おまかせで進める')",
    "#atlas-workbench-card [role='button']:has-text('おまかせで進める')",
    "text=おまかせで進める",
  ]
  for selector in selectors:
    locator = page.locator(selector)
    if await locator.count() > 0:
      await locator.first.click()
      return True, "おまかせで進める"
  return False, ""


async def resolve_atlas_clarification_once(page) -> dict:
  diag_before = await collect_atlas_clarification_diag(page)
  click_succeeded, clicked_text = await click_atlas_proceed_with_assumptions_once(page)
  diag_after = await collect_atlas_clarification_diag(page)
  return {
    "resolutionAttempted": True,
    "resolutionAction": "proceed_with_assumptions" if click_succeeded else "none",
    "clickedButtonText": clicked_text,
    "resolutionClickSucceeded": click_succeeded,
    "clarificationBefore": diag_before,
    "clarificationAfter": diag_after,
  }

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


async def verify_nexus_current_ui_smoke(page) -> None:
  await set_mode(page, "nexus")
  root = await get_nexus_root_selector(page)
  tabs = await page.evaluate("""(rootSel) => {
    const root = document.querySelector(rootSel) || document;
    return Array.from(root.querySelectorAll('[data-nexus-tab]')).map((el) => String(el.dataset.nexusTab || '').trim()).filter(Boolean);
  }""", root)
  if "dashboard" not in tabs:
    raise AssertionError(f"nexus_dashboard_tab_missing; tabs={tabs}")
  for required in ["research", "sources", "evidence", "reports", "settings"]:
    if required not in tabs:
      print(f"INFO: nexus_smoke_missing_expected_tab_name:{required}; tabs={tabs}")
  await click_nexus_tab(page, "dashboard")
  await wait_named(page, "nexus_dashboard_visible_on_dashboard_tab", """() => {
    const panel = document.querySelector('[data-nexus-panel="dashboard"]');
    return !!panel && !panel.hidden && getComputedStyle(panel).display !== 'none';
  }""")
  for tab in ["research", "sources", "evidence", "reports", "settings"]:
    await click_nexus_tab(page, tab)
    await wait_named(page, f"nexus_dashboard_hidden_on_{tab}", f"""() => {{
      const dashboard = document.querySelector('[data-nexus-panel="dashboard"]');
      const active = document.querySelector('[data-nexus-panel="{tab}"]');
      if (!dashboard || !active) return false;
      return (dashboard.hidden || getComputedStyle(dashboard).display === 'none')
        && !active.hidden && getComputedStyle(active).display !== 'none';
    }}""")
  await wait_named(page, "nexus_active_tab_matches_visible_panel", """() => {
    const activeTab = document.querySelector('[data-nexus-tab].active')?.dataset?.nexusTab;
    const visiblePanels = Array.from(document.querySelectorAll('[data-nexus-panel]')).filter((panel) => !panel.hidden && getComputedStyle(panel).display !== 'none');
    return !!activeTab && visiblePanels.length === 1 && visiblePanels[0].dataset.nexusPanel === activeTab;
  }""")

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


async def fill_atlas_requirement(page, text: str) -> None:
  requirement = get_atlas_requirement_input(page)
  await requirement.wait_for(state="visible")
  await requirement.scroll_into_view_if_needed()
  await requirement.fill(text)


async def verify_atlas_current_ui_smoke(page) -> None:
  await page.click("#btn-chat")
  await wait_named(page, 'atlas_current_chat_visible', "() => document.getElementById('chat-col') && getComputedStyle(document.getElementById('chat-col')).display !== 'none'")
  chat_text = await page.locator("#chat-col").inner_text()
  assert await page.locator("#chat-task-toggle").count() == 0
  assert await page.locator("#chat-role-note").count() == 0
  for forbidden in ["Legacy Task", "Chat is for lightweight conversation", "Planning, approval", "Plan設定", "Start Plan", "Generate Plan", "Guided Plan", "Open Atlas", "Use Chat Input", "Atlas Plan", "Atlas status"]:
    assert forbidden not in chat_text, f"Chat should not expose planning affordance: {forbidden}"

  await open_atlas(page)
  atlas_text = await page.locator("#atlas-panel-col").inner_text()
  assert "Workflow Workbench" in atlas_text
  assert "Workflow Workbench: Requirement / Plan / Review / Approval / Agent Execution / Execute Preview / Patch Review / Apply." not in atlas_text
  assert "Agent execution is moving under Atlas" not in atlas_text
  assert "Recent and manual run inspection live" not in atlas_text
  assert await page.locator("#atlas-panel-col > .agent-head").count() == 0
  stray_atlas_heading = await page.evaluate("""() => {
    const panel = document.getElementById('atlas-panel-col');
    const card = document.getElementById('atlas-workbench-card');
    if (!panel || !card) return false;
    const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const text = String(node.nodeValue || '').trim();
      if (text !== 'Atlas') continue;
      const parent = node.parentElement;
      if (!parent) continue;
      if (parent.closest('.mode-wrap, .mob-tabs, #atlas-workbench-card')) continue;
      const rect = parent.getBoundingClientRect();
      const cardRect = card.getBoundingClientRect();
      const style = getComputedStyle(parent);
      if (style.display !== 'none' && style.visibility !== 'hidden' && rect.bottom <= cardRect.top + 2) return true;
    }
    return false;
  }""")
  await wait_named(page, 'no_standalone_atlas_label', """() => {
    const card = document.getElementById('atlas-workbench-card');
    if (!card) return false;
    const cardTop = card.getBoundingClientRect().top;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const text = String(node.nodeValue || '').trim();
      if (text !== 'Atlas') continue;
      const parent = node.parentElement;
      if (!parent) continue;
      if (parent.closest('.mode-wrap, .mob-tabs, #atlas-workbench-card')) continue;
      const style = getComputedStyle(parent);
      const rect = parent.getBoundingClientRect();
      const visible = style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
      if (visible && rect.bottom <= cardTop + 2) return false;
    }
    return true;
  }""")
  assert not stray_atlas_heading, "Atlas mode must not render a standalone Atlas heading above Workflow Workbench"
  assert await page.locator("#atlas-workbench-card [data-atlas-subview-tab='legacy']").count() == 0
  for tab in ["start", "plan", "review", "execute", "patch", "runs", "activity"]:
    assert await page.locator(f"#atlas-workbench-card [data-atlas-subview-tab='{tab}']").count() == 1

  await wait_named(page, 'atlas_panel_visible', """() => {
    const panel = document.getElementById('atlas-panel-col');
    return !!panel && getComputedStyle(panel).display !== 'none' && panel.getBoundingClientRect().height > 0;
  }""")
  await wait_named(page, 'atlas_workbench_visible', """() => {
    const card = document.getElementById('atlas-workbench-card');
    return !!card && getComputedStyle(card).display !== 'none' && card.getBoundingClientRect().height > 0;
  }""")
  await wait_named(page, 'activity_tab_exists', "() => document.querySelectorAll(\"#atlas-workbench-card [data-atlas-subview-tab='activity']\").length === 1")
  await wait_named(page, 'activity_panel_exists', "() => document.querySelectorAll(\"#atlas-workbench-card [data-atlas-subview-panel='activity']\").length === 1")
  await wait_named(page, 'activity_stream_singleton', "() => document.querySelectorAll('#atlas-activity-stream').length === 1")
  await wait_named(page, 'activity_stream_inside_activity_panel', """() => {
    const panel = document.querySelector("#atlas-workbench-card [data-atlas-subview-panel='activity']");
    const stream = document.getElementById('atlas-activity-stream');
    return !!panel && !!stream && panel.contains(stream);
  }""")
  await wait_named(page, 'activity_stream_hidden_until_activity_tab_selected', """() => {
    const stream = document.getElementById('atlas-activity-stream');
    const panel = document.querySelector('[data-atlas-subview-panel="activity"]');
    if (!panel || !stream) return false;
    if (!panel.contains(stream)) return false;
    const panelVisible = !panel.hidden && getComputedStyle(panel).display !== 'none' && panel.getBoundingClientRect().height > 0;
    return !panelVisible;
  }""")
  for mode_name in ["chat", "echo", "agent", "nexus"]:
    await set_mode(page, mode_name)
    await wait_named(page, f'atlas_activity_stream_hidden_{mode_name}', """() => {
      const stream = document.getElementById('atlas-activity-stream');
      if (!stream) return false;
      const style = getComputedStyle(stream);
      const atlas = document.getElementById('atlas-panel-col');
      const atlasHidden = !atlas || style.display === 'none' || atlas.offsetParent === null;
      return atlasHidden && stream.offsetParent === null;
    }""")
  await open_atlas(page)
  await wait_named(page, 'activity_stream_hidden_after_mode_switches_until_tab_selected', """() => {
    const stream = document.getElementById('atlas-activity-stream');
    const panel = document.querySelector('[data-atlas-subview-panel="activity"]');
    if (!panel || !stream) return false;
    if (!panel.contains(stream)) return false;
    const panelVisible = !panel.hidden && getComputedStyle(panel).display !== 'none' && panel.getBoundingClientRect().height > 0;
    return !panelVisible;
  }""")

  await ensure_atlas_start(page)
  await wait_named(page, 'atlas_start_tab_visible', "() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'start'")
  assert await page.locator("#atlas-workbench-card [data-atlas-subview-panel='start'] #atlas-requirement-input").count() == 1
  assert await page.locator("#atlas-workbench-card [data-atlas-subview-panel='start'] button", has_text="Start Atlas").count() == 1
  await ensure_atlas_plan(page)
  await wait_named(page, 'plan_tab_plan_only', """() => {
    const panel = document.querySelector("#atlas-workbench-card [data-atlas-subview-panel='plan']");
    if (!panel) return false;
    const text = panel.textContent || '';
    return !text.includes('Approve Plan') && !text.includes('Execute Preview') && !text.includes('Patch Review');
  }""")
  plan_panel_text = await page.locator("#atlas-workbench-card [data-atlas-subview-panel='plan']").inner_text()
  assert "No plan yet" in plan_panel_text
  assert await page.locator("#atlas-workbench-card [data-atlas-subview-panel='plan'] button", has_text="Start Atlas").count() == 0
  await set_atlas_subview(page, "review")
  await wait_named(page, 'review_tab_has_review_host', """() => {
    const panel = document.querySelector("#atlas-workbench-card [data-atlas-subview-panel='review']");
    if (!panel) return false;
    const text = panel.textContent || '';
    return text.includes('Plan Review') || text.includes('No review yet') || !!panel.querySelector('[data-atlas-workflow-target="approval"], #atlas-workbench-card-plan-next-action');
  }""")
  await set_atlas_subview(page, "execute")
  await wait_named(page, 'execute_tab_visible', "() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'execute'")
  await set_atlas_subview(page, "patch")
  await wait_named(page, 'patch_tab_visible', "() => document.getElementById('atlas-workbench-card')?.dataset.atlasCurrentSubview === 'patch'")
  await set_atlas_subview(page, "activity")
  await wait_named(page, 'activity_tab_stream_visible_after_select', """() => {
    const stream = document.getElementById('atlas-activity-stream');
    const panel = document.querySelector('[data-atlas-subview-panel="activity"]');
    if (!panel || !stream) return false;
    if (!panel.contains(stream)) return false;
    return (
      !panel.hidden &&
      getComputedStyle(panel).display !== 'none' &&
      stream.getBoundingClientRect().height > 0
    );
  }""")
  await set_mode(page, "chat")
  await wait_named(page, 'chat_hides_activity_stream', """() => {
    const panel = document.querySelector('[data-atlas-subview-panel="activity"]');
    const stream = document.getElementById('atlas-activity-stream');
    if (!panel || !stream) return false;
    return panel.hidden || getComputedStyle(panel).display === 'none' || stream.offsetParent === null;
  }""")
  await set_mode(page, "echo")
  await wait_named(page, 'echo_hides_activity_stream', """() => {
    const panel = document.querySelector('[data-atlas-subview-panel="activity"]');
    const stream = document.getElementById('atlas-activity-stream');
    if (!panel || !stream) return false;
    return panel.hidden || getComputedStyle(panel).display === 'none' || stream.offsetParent === null;
  }""")
  await open_atlas(page)
  await set_atlas_subview(page, "activity")

  collapse = page.locator("#atlas-workbench-collapse-btn")
  await collapse.click()
  await wait_named(page, 'workbench_collapsed', "() => document.getElementById('atlas-workbench-card')?.classList.contains('is-collapsed')")
  await wait_named(page, 'activity_stream_hidden_when_collapsed_off_activity_tab', """() => {
    const stream = document.getElementById('atlas-activity-stream');
    const panel = document.querySelector('[data-atlas-subview-panel="activity"]');
    if (!panel || !stream) return false;
    return panel.hidden || getComputedStyle(panel).display === 'none' || stream.offsetParent === null;
  }""")
  await collapse.click()
  await wait_named(page, 'workbench_collapse_available', "() => !document.getElementById('atlas-workbench-card')?.classList.contains('is-collapsed')")
  assert await page.locator("#atlas-agent-execution-marker[data-atlas-agent-execution='true']").count() == 1

  await page.set_viewport_size(DEFAULT_MOBILE_VIEWPORT)
  await page.wait_for_timeout(100)
  overflow = await page.evaluate("""() => ({
    doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    body: document.body.scrollWidth - document.body.clientWidth,
    atlas: document.getElementById('atlas-panel-col')?.scrollWidth - document.getElementById('atlas-panel-col')?.clientWidth,
  })""")
  if not (overflow["doc"] <= 1 and overflow["body"] <= 1 and overflow["atlas"] <= 1):
    offenders = await page.evaluate("""() => Array.from(document.body.querySelectorAll('*')).map((el) => {
      const r = el.getBoundingClientRect();
      return {
        tag: el.tagName,
        id: el.id,
        className: String(el.className || ''),
        text: (el.textContent || '').trim().slice(0, 80),
        left: r.left,
        right: r.right,
        width: r.width,
        overflowRight: r.right - window.innerWidth,
      };
    }).filter(x => x.overflowRight > 1).sort((a,b) => b.overflowRight - a.overflowRight).slice(0,20)""")
    raise AssertionError(f"mobile horizontal overflow detected: {overflow}; offenders: {offenders}")
  await wait_named(page, 'mobile_no_horizontal_overflow', "() => document.documentElement.scrollWidth - document.documentElement.clientWidth <= 1 && document.body.scrollWidth - document.body.clientWidth <= 1")

  await page.click("#btn-agent")
  await wait_named(page, 'agent_hides_atlas_panel_from_atlas_smoke', "() => document.getElementById('atlas-panel-col')?.classList.contains('mob-hidden') || getComputedStyle(document.getElementById('atlas-panel-col')).display === 'none'")
  await wait_named(page, 'agent_hides_activity_stream_from_atlas_smoke', """() => {
    const panel = document.querySelector('[data-atlas-subview-panel="activity"]');
    const stream = document.getElementById('atlas-activity-stream');
    if (!panel || !stream) return false;
    return panel.hidden || getComputedStyle(panel).display === 'none' || stream.offsetParent === null;
  }""")
  await assert_no_atlas_chat_leak(page, "atlas_current_ui_smoke_agent_switch")


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


def safe_artifact_path(path: Path) -> str:
  resolved_path = path.resolve()
  resolved_root = ROOT.resolve()
  try:
    return str(resolved_path.relative_to(resolved_root))
  except ValueError:
    return str(resolved_path)


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
    results.append({"name": name, "status": "FAIL", "error": err_text, "artifact": safe_artifact_path(log_path)})
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


def compact_smoke_error(error: str, *, limit: int = 240) -> str:
  text = " ".join((error or "").replace("\r", " ").split())
  if len(text) > limit:
    text = text[: limit - 1].rstrip() + "…"
  return html.escape(text).replace("|", "\\|")


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
    "| Scenario | Status | Error summary | Artifact log |",
    "|---|---|---|---|",
  ]
  for row in results:
    scenario_name = row.get("name", "")
    escaped_name = scenario_name.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
    error = compact_smoke_error(row.get("error") or "")
    lines.append(f"| {escaped_name} | {row['status']} | {error} | {row.get('artifact', '')} |")
  summary = "\n".join(lines) + "\n"
  print(summary)
  (PLAYWRIGHT_ARTIFACT_DIR / "summary.md").write_text(summary, encoding="utf-8")
  return summary



@dataclass(frozen=True)
class SmokeScenarioSpec:
  id: str
  fn: callable
  kind: str
  requires_backend: bool = False
  allowed_in_preflight_only: bool = False
  default_ui: bool = False
  default_backend_e2e: bool = False
  deterministic: bool = True
  acceptance_default: bool = False
  uses_live_llm: bool = False
  destructive: bool = False


SMOKE_SCENARIOS: dict[str, SmokeScenarioSpec] = {
  "atlas_backend_preflight": SmokeScenarioSpec(id="atlas_backend_preflight", fn=run_backend_preflight, kind="backend_preflight", requires_backend=True, allowed_in_preflight_only=True),
  "atlas_backend_e2e_journey": SmokeScenarioSpec(id="atlas_backend_e2e_journey", fn=verify_atlas_backend_e2e_journey, kind="backend_e2e", requires_backend=True, deterministic=False, uses_live_llm=True),
  "atlas_backend_e2e_wait_plan_live_llm": SmokeScenarioSpec(id="atlas_backend_e2e_wait_plan_live_llm", fn=verify_atlas_backend_e2e_journey, kind="backend_e2e", requires_backend=True, deterministic=False, uses_live_llm=True),
  "atlas_backend_e2e_wait_plan": SmokeScenarioSpec(id="atlas_backend_e2e_wait_plan", fn=verify_atlas_backend_e2e_journey, kind="backend_e2e", requires_backend=True, acceptance_default=True),
  "atlas_backend_e2e_resolve_clarification": SmokeScenarioSpec(id="atlas_backend_e2e_resolve_clarification", fn=verify_atlas_backend_e2e_journey, kind="backend_e2e", requires_backend=True, acceptance_default=True),
  "atlas_backend_e2e_plan_approval_gate": SmokeScenarioSpec(id="atlas_backend_e2e_plan_approval_gate", fn=verify_atlas_backend_e2e_journey, kind="backend_e2e", requires_backend=True, acceptance_default=True),
  "atlas_backend_e2e_plan_approval_actionability": SmokeScenarioSpec(id="atlas_backend_e2e_plan_approval_actionability", fn=verify_atlas_backend_e2e_journey, kind="backend_e2e", requires_backend=True, acceptance_default=True),
  "bootstrap_api_contract": SmokeScenarioSpec(id="bootstrap_api_contract", fn=verify_mode_switches, kind="ui", default_ui=True),
  "mode_switches": SmokeScenarioSpec(id="mode_switches", fn=verify_mode_switches, kind="ui", default_ui=True),
  "atlas_current_ui_smoke": SmokeScenarioSpec(id="atlas_current_ui_smoke", fn=verify_atlas_current_ui_smoke, kind="ui", default_ui=True),
  "nexus_current_ui_smoke": SmokeScenarioSpec(id="nexus_current_ui_smoke", fn=verify_nexus_current_ui_smoke, kind="ui", default_ui=True),
  "atlas_plan_api_contract": SmokeScenarioSpec(id="atlas_plan_api_contract", fn=verify_atlas_plan_api_contract, kind="backend_api", requires_backend=True, allowed_in_preflight_only=True),
  "atlas_start_button_feedback": SmokeScenarioSpec(id="atlas_start_button_feedback", fn=verify_atlas_start_button_feedback, kind="ui", default_ui=True),
  "atlas_guided_workflow_safe_journey": SmokeScenarioSpec(id="atlas_guided_workflow_safe_journey", fn=verify_atlas_guided_workflow_safe_journey, kind="ui", default_ui=True),
  "mode_specific_subtabs": SmokeScenarioSpec(id="mode_specific_subtabs", fn=verify_mode_specific_subtabs, kind="ui", default_ui=True),
  "nexus_tabs": SmokeScenarioSpec(id="nexus_tabs", fn=verify_nexus_tabs, kind="ui", default_ui=True),
  "reference_card_actions": SmokeScenarioSpec(id="reference_card_actions", fn=verify_reference_card_actions, kind="ui", default_ui=True),
  "chat_search_and_agent_web_tool_tts": SmokeScenarioSpec(id="chat_search_and_agent_web_tool_tts", fn=verify_chat_search_and_agent_web_tool_tts, kind="ui", default_ui=True),
  "mobile_mode_switches": SmokeScenarioSpec(id="mobile_mode_switches", fn=verify_mobile_mode_switches, kind="ui"),
}


def _scenario_to_json(spec: SmokeScenarioSpec) -> dict:
  return {
    "id": spec.id,
    "kind": spec.kind,
    "requires_backend": spec.requires_backend,
    "allowed_in_preflight_only": spec.allowed_in_preflight_only,
    "default_ui": spec.default_ui,
    "default_backend_e2e": spec.default_backend_e2e,
    "deterministic": spec.deterministic,
    "acceptance_default": spec.acceptance_default,
    "uses_live_llm": spec.uses_live_llm,
    "destructive": spec.destructive,
  }


def resolve_smoke_scenarios(*, only: list[str], preflight_only_mode: bool, run_backend_e2e: bool, run_wait_plan: bool, run_resolve_clarification: bool, run_check_plan_approval: bool, run_check_plan_approval_actionable: bool) -> list[str]:
  if only:
    unknown = [item for item in only if item not in SMOKE_SCENARIOS]
    if unknown:
      raise AssertionError(f"unknown scenarios: {unknown}")
    if preflight_only_mode:
      disallowed = [item for item in only if SMOKE_SCENARIOS[item].kind == "ui" and not SMOKE_SCENARIOS[item].allowed_in_preflight_only]
      if disallowed:
        raise AssertionError(f"scenario not allowed in current mode: {disallowed}")
    selected = []
    if any(SMOKE_SCENARIOS[item].requires_backend for item in only):
      selected.append("atlas_backend_preflight")
    selected.extend(only)
    return list(dict.fromkeys(selected))

  if preflight_only_mode:
    return ["atlas_backend_preflight"]
  if run_backend_e2e:
    if run_check_plan_approval_actionable:
      return ["atlas_backend_preflight", "atlas_backend_e2e_plan_approval_actionability"]
    if run_check_plan_approval:
      return ["atlas_backend_preflight", "atlas_backend_e2e_plan_approval_gate"]
    if run_wait_plan and run_resolve_clarification:
      return ["atlas_backend_preflight", "atlas_backend_e2e_resolve_clarification"]
    if run_wait_plan:
      return ["atlas_backend_preflight", "atlas_backend_e2e_wait_plan"]
    return ["atlas_backend_preflight", "atlas_backend_e2e_journey"]
  return [spec.id for spec in SMOKE_SCENARIOS.values() if spec.default_ui]



async def main() -> None:
  parser = argparse.ArgumentParser(add_help=True)
  parser.add_argument("--list-scenarios", action="store_true")
  args, _ = parser.parse_known_args()
  if args.list_scenarios:
    print(json.dumps({"scenarios": [_scenario_to_json(SMOKE_SCENARIOS[name]) for name in sorted(SMOKE_SCENARIOS.keys())]}, ensure_ascii=False, indent=2))
    return
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
  run_backend_resolve_clarification_opt_in = os.environ.get("RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION", "").strip() == "1"
  run_backend_check_plan_approval_opt_in = os.environ.get("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL", "").strip() == "1"
  run_backend_check_plan_approval_actionable_opt_in = os.environ.get("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL_ACTIONABLE", "").strip() == "1"
  if run_backend_wait_plan_opt_in and not run_backend_e2e_opt_in:
    raise AssertionError("RUN_ATLAS_BACKEND_E2E_WAIT_PLAN requires RUN_ATLAS_BACKEND_E2E=1.")
  if run_backend_resolve_clarification_opt_in and not (run_backend_e2e_opt_in and run_backend_wait_plan_opt_in):
    raise AssertionError("RUN_ATLAS_BACKEND_E2E_RESOLVE_CLARIFICATION requires RUN_ATLAS_BACKEND_E2E=1 and RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1.")
  if run_backend_check_plan_approval_opt_in and not (run_backend_e2e_opt_in and run_backend_wait_plan_opt_in):
    raise AssertionError("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL requires RUN_ATLAS_BACKEND_E2E=1 and RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1.")
  if run_backend_check_plan_approval_actionable_opt_in and not (run_backend_e2e_opt_in and run_backend_wait_plan_opt_in and run_backend_check_plan_approval_opt_in):
    raise AssertionError("RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL_ACTIONABLE requires RUN_ATLAS_BACKEND_E2E=1, RUN_ATLAS_BACKEND_E2E_WAIT_PLAN=1, and RUN_ATLAS_BACKEND_E2E_CHECK_PLAN_APPROVAL=1.")
  preflight_only_mode = run_backend_preflight_opt_in and not run_backend_e2e_opt_in
  full_backend_e2e_mode = run_backend_e2e_opt_in
  real_backend_opt_in = run_backend_preflight_opt_in or run_backend_e2e_opt_in
  explicit_base_url = os.environ.get("PLAYWRIGHT_SMOKE_BASE_URL", "").strip()

  async with async_playwright() as p:
    browser = await launch_browser_with_retry(p, attempts=2)
    if explicit_base_url and not real_backend_opt_in:
      print("INFO: PLAYWRIGHT_SMOKE_BASE_URL is ignored in default mock-backed UI smoke. Set RUN_ATLAS_BACKEND_PREFLIGHT=1 or RUN_ATLAS_BACKEND_E2E=1 to target a real backend.")
    if real_backend_opt_in and not explicit_base_url:
      raise AssertionError("PLAYWRIGHT_SMOKE_BASE_URL is required when RUN_ATLAS_BACKEND_PREFLIGHT=1 or RUN_ATLAS_BACKEND_E2E=1.")
    base_url, mock_server = get_smoke_base_url(use_explicit_base_url=real_backend_opt_in)
    print(f"INFO: Playwright smoke base URL = {base_url}")
    results: list[dict[str, str]] = []
    scenario_runners: dict[str, callable] = {name: spec.fn for name, spec in SMOKE_SCENARIOS.items()}

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
        if run_backend_check_plan_approval_actionable_opt_in:
          await prepare_seeded_review_ready_plan(page)
          actionability_diag = await verify_atlas_plan_approval_actionability(page, {}, console_errors, page_errors)
          print("INFO: atlas plan-approval-actionability diagnostics:\n" + json.dumps(actionability_diag, ensure_ascii=False, indent=2))
          await assert_no_atlas_chat_leak(page, "plan_approval_actionability")
          return
        if run_backend_check_plan_approval_opt_in:
          await prepare_seeded_review_ready_plan(page)
          diag = await collect_atlas_plan_approval_gate_diag(page)
          diag = {**diag, "finalDecision": "generated_plan_ready_for_review", "completionDecisionReason": "debug_seed_plan_applied"}
        elif run_backend_wait_plan_opt_in and run_backend_resolve_clarification_opt_in:
          clarification_seed = await load_debug_seed_clarification(page)
          await start_atlas_backend_e2e_journey(page, "debug seeded clarification journey")
          await page.evaluate("""(seed) => {
            if (typeof window.__atlasApplyPlanResultForTests !== 'function') throw new Error('missing_plan_result_hook');
            window.__atlasApplyPlanResultForTests(seed);
          }""", clarification_seed)
          resolution_diag = await resolve_atlas_clarification_once(page)
          if not resolution_diag.get("resolutionClickSucceeded"):
            raise AssertionError("clarification resolution failed: proceed_with_assumptions_button_missing; artifact=atlas_lifecycle_final.json")
          await prepare_seeded_review_ready_plan(page)
          diag = {**(await collect_atlas_plan_approval_gate_diag(page)), "finalDecision": "generated_plan_ready_for_review", "completionDecisionReason": "debug_seed_clarification_resolved"}
        elif run_backend_wait_plan_opt_in:
          await prepare_seeded_review_ready_plan(page)
          diag = {**(await collect_atlas_plan_approval_gate_diag(page)), "finalDecision": "generated_plan_ready_for_review", "completionDecisionReason": "debug_seed_plan_applied"}
        else:
          diag = await prepare_generated_plan(
            page,
            prompt=ATLAS_APPROVAL_STABLE_PROMPT,
            preflight_status=preflight_status,
            base_url=base_url,
            console_errors=console_errors,
            page_errors=page_errors,
          )
        wait_plan_diag = {
          "initialFinalDecision": diag.get("finalDecision"),
          "initialCompletionReason": diag.get("completionDecisionReason"),
          "resolutionAttempted": False,
          "resolutionAction": "none",
          "clickedButtonText": "",
          "resolutionClickSucceeded": False,
          "postResolutionFinalDecision": diag.get("finalDecision"),
          "postResolutionCompletionReason": diag.get("completionDecisionReason"),
          "clarificationSignalsBefore": diag.get("clarificationSignals", []),
          "clarificationSignalsAfter": diag.get("clarificationSignals", []),
          "planFlowTextTailBefore": diag.get("planFlowTextTail", ""),
          "planFlowTextTailAfter": diag.get("planFlowTextTail", ""),
          "messagesTailBefore": diag.get("messagesTail", []),
          "messagesTailAfter": diag.get("messagesTail", []),
          "approveButtonsPresentBefore": diag.get("approveButtonsPresent", False),
          "executeButtonsPresentBefore": diag.get("executeButtonsPresent", False),
          "patchApplyButtonsPresentBefore": diag.get("patchApplyButtonsPresent", False),
          "consoleErrors": list(console_errors),
          "pageErrors": list(page_errors),
          "elapsedMs": diag.get("elapsedMs"),
        }
        if diag.get("finalDecision") == "needs_clarification" and run_backend_resolve_clarification_opt_in and not run_backend_wait_plan_opt_in:
          resolution_diag = await resolve_atlas_clarification_once(page)
          wait_plan_diag["resolutionAttempted"] = bool(resolution_diag.get("resolutionAttempted"))
          wait_plan_diag["resolutionAction"] = resolution_diag.get("resolutionAction", "none")
          wait_plan_diag["clickedButtonText"] = resolution_diag.get("clickedButtonText", "")
          wait_plan_diag["resolutionClickSucceeded"] = bool(resolution_diag.get("resolutionClickSucceeded"))
          wait_plan_diag["clarificationSignalsBefore"] = diag.get("clarificationSignals", [])
          wait_plan_diag["planFlowTextTailBefore"] = diag.get("planFlowTextTail", "")
          wait_plan_diag["messagesTailBefore"] = diag.get("messagesTail", [])
          wait_plan_diag["approveButtonsPresentBefore"] = diag.get("approveButtonsPresent", False)
          wait_plan_diag["executeButtonsPresentBefore"] = diag.get("executeButtonsPresent", False)
          wait_plan_diag["patchApplyButtonsPresentBefore"] = diag.get("patchApplyButtonsPresent", False)
          if not wait_plan_diag["resolutionClickSucceeded"]:
            raise AssertionError("clarification resolution failed: proceed_with_assumptions_button_missing; artifact=atlas_lifecycle_final.json")
          post_diag = await wait_atlas_plan_completion(page, timeout_ms=45000, preflight_status=preflight_status, base_url=base_url, console_errors=console_errors, page_errors=page_errors)
          wait_plan_diag["postResolutionFinalDecision"] = post_diag.get("finalDecision")
          wait_plan_diag["postResolutionCompletionReason"] = post_diag.get("completionDecisionReason")
          wait_plan_diag["clarificationSignalsAfter"] = post_diag.get("clarificationSignals", [])
          wait_plan_diag["planFlowTextTailAfter"] = post_diag.get("planFlowTextTail", "")
          wait_plan_diag["messagesTailAfter"] = post_diag.get("messagesTail", [])
          wait_plan_diag["approveButtonsPresentAfter"] = post_diag.get("approveButtonsPresent", False)
          wait_plan_diag["executeButtonsPresentAfter"] = post_diag.get("executeButtonsPresent", False)
          wait_plan_diag["patchApplyButtonsPresentAfter"] = post_diag.get("patchApplyButtonsPresent", False)
          wait_plan_diag["consoleErrors"] = list(console_errors)
          wait_plan_diag["pageErrors"] = list(page_errors)
          wait_plan_diag["elapsedMs"] = post_diag.get("elapsedMs")
          diag = post_diag
          if diag.get("finalDecision") == "needs_clarification":
            diag = {**diag, "finalDecision": "needs_clarification_after_resolution", "completionDecisionReason": "clarification_required_after_single_resolution_attempt"}
            wait_plan_diag["postResolutionFinalDecision"] = "needs_clarification_after_resolution"
        print("INFO: atlas backend wait-plan diagnostics:\n" + json.dumps({"waitPlan": diag, "resolution": wait_plan_diag}, ensure_ascii=False, indent=2))
        await assert_no_atlas_chat_leak(page, "wait_plan")
        if run_backend_check_plan_approval_opt_in:
          approval_diag = await verify_atlas_plan_approval_gate_readiness(page, diag, console_errors, page_errors)
          print("INFO: atlas plan-approval-gate diagnostics:\n" + json.dumps(approval_diag, ensure_ascii=False, indent=2))
        if run_backend_check_plan_approval_actionable_opt_in:
          actionability_diag = await verify_atlas_plan_approval_actionability(page, diag, console_errors, page_errors)
          print("INFO: atlas plan-approval-actionability diagnostics:\n" + json.dumps(actionability_diag, ensure_ascii=False, indent=2))
        if diag.get("finalDecision") in ("failed", "timeout", "unknown"):
          raise_compact_atlas_diag(diag, prefix="atlas wait-plan failed")
        if run_backend_check_plan_approval_opt_in and diag.get("finalDecision") in ("needs_clarification", "needs_clarification_after_resolution"):
          print("INFO: plan_approval_gate_skipped_needs_clarification")

      if run_backend_check_plan_approval_actionable_opt_in:
        scenarios = [
          ("atlas_backend_preflight", run_backend_preflight),
          ("atlas_backend_e2e_plan_approval_actionability", verify_atlas_backend_e2e_wait_plan),
        ]
        scenario_runners["atlas_backend_e2e_plan_approval_actionability"] = verify_atlas_backend_e2e_wait_plan
      elif run_backend_check_plan_approval_opt_in:
        scenarios = [
          ("atlas_backend_preflight", run_backend_preflight),
          ("atlas_backend_e2e_plan_approval_gate", verify_atlas_backend_e2e_wait_plan),
        ]
        scenario_runners["atlas_backend_e2e_plan_approval_gate"] = verify_atlas_backend_e2e_wait_plan
      elif run_backend_wait_plan_opt_in and run_backend_resolve_clarification_opt_in:
        scenarios = [
          ("atlas_backend_preflight", run_backend_preflight),
          ("atlas_backend_e2e_resolve_clarification", verify_atlas_backend_e2e_wait_plan),
        ]
        scenario_runners["atlas_backend_e2e_resolve_clarification"] = verify_atlas_backend_e2e_wait_plan
      elif run_backend_wait_plan_opt_in:
        scenarios = [
          ("atlas_backend_preflight", run_backend_preflight),
          ("atlas_backend_e2e_wait_plan", verify_atlas_backend_e2e_wait_plan),
        ]
        scenario_runners["atlas_backend_e2e_wait_plan"] = verify_atlas_backend_e2e_wait_plan
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
      scenarios = []

      async def bootstrap_assertions(current_page) -> None:
        set_mode_type, switch_tab_type = await current_page.evaluate("() => [typeof window.setMode, typeof window.switchNexusTab]")
        assert set_mode_type == "function", f"window.setMode is {set_mode_type}"
        assert switch_tab_type == "function", f"window.switchNexusTab is {switch_tab_type}"

      scenario_runners["bootstrap_api_contract"] = bootstrap_assertions

    only = [item.strip() for item in os.environ.get("PLAYWRIGHT_SMOKE_ONLY", "").split(",") if item.strip()]
    selected_scenarios = resolve_smoke_scenarios(
      only=only,
      preflight_only_mode=preflight_only_mode,
      run_backend_e2e=run_backend_e2e_opt_in,
      run_wait_plan=run_backend_wait_plan_opt_in,
      run_resolve_clarification=run_backend_resolve_clarification_opt_in,
      run_check_plan_approval=run_backend_check_plan_approval_opt_in,
      run_check_plan_approval_actionable=run_backend_check_plan_approval_actionable_opt_in,
    )
    if not selected_scenarios:
      raise AssertionError("no scenarios selected after resolution: []")
    print("INFO: selected scenarios: " + ", ".join(selected_scenarios))
    missing_runners = [name for name in selected_scenarios if name not in scenario_runners]
    if missing_runners:
      raise AssertionError(f"selected scenarios missing runners: {missing_runners}")
    scenarios = [(name, scenario_runners[name]) for name in selected_scenarios]

    for scenario_name, scenario_fn in scenarios:
      await run_smoke_scenario(scenario_name, browser, base_url, scenario_fn, results, DEFAULT_DESKTOP_VIEWPORT)

    if not (preflight_only_mode or full_backend_e2e_mode) and (not only or "mobile_mode_switches" in set(only)):
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

# contract token: plan_flow_approval_required

# contract token: plan_flow_generated_review_done_approval_required
