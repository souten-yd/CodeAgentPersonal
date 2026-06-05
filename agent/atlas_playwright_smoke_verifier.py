from __future__ import annotations

import contextlib
import asyncio
import os
import re
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

try:
    from playwright.sync_api import sync_playwright  # type: ignore[import]
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

# Animation tasks require computed style changes over time. Keep the regex word-boundary
# based so descriptions like "inanimate object" do not accidentally become animation tasks.
_ANIMATION_TASK_HINT = ("animat", "wave", "oscillat", "bounce", "spin", "rotat", "pulse", "fade",
                        "move", "motion", "color chang", "hue")
_ANIMATION_TASK_RE = re.compile(
    r'\b(animat\w*|wave\w*|oscillat\w*|bounce\w*|spin\w*|rotat\w*|pulse\w*|fade\w*|mov\w*|motion|color\s*chang\w*|hue)\b',
    re.IGNORECASE,
)

# How long to wait for animations to produce a change (ms). Generous enough for slow
# first-frame animations and games that start a beat after load.
_ANIMATION_POLL_INTERVAL_MS = 100
_ANIMATION_MAX_WAIT_MS = 3500


def _sample_interval_ms() -> int:
    return _env_int("ATLAS_VISUAL_SAMPLE_INTERVAL_MS", _ANIMATION_POLL_INTERVAL_MS, minimum=1)


def _sample_max_wait_ms() -> int:
    return _env_int("ATLAS_VISUAL_SAMPLE_MAX_MS", _ANIMATION_MAX_WAIT_MS, minimum=1)


def _env_int(name: str, default: int, *, minimum: int) -> int:
    try:
        value = int(str(os.environ.get(name, "") or "").strip())
    except ValueError:
        return default
    return max(minimum, value)


def _is_animation_task(task_description: str) -> bool:
    return bool(_ANIMATION_TASK_RE.search(task_description or ""))


# Playwright raises this class of error when the python package is present but the
# browser binary was never downloaded (``playwright install``). The message is stable
# across platforms ("Executable doesn't exist at ... playwright install").
def _is_browser_not_installed_error(exc: Exception) -> bool:
    msg = f"{type(exc).__name__}: {exc}".lower()
    return (
        "executable doesn't exist" in msg
        or "browser executable" in msg and "not found" in msg
        or "executable was not found" in msg
        or ("playwright install" in msg and ("browsertype.launch" in msg or "browser" in msg or "executable" in msg))
    )


@contextlib.contextmanager
def _playwright_event_loop_policy():
    if sys.platform != "win32" or not hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        yield
        return
    previous = asyncio.get_event_loop_policy()
    try:
        if hasattr(asyncio, "WindowsSelectorEventLoopPolicy") and isinstance(previous, asyncio.WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        yield
    finally:
        try:
            asyncio.set_event_loop_policy(previous)
        except Exception:  # noqa: BLE001
            pass


class _QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler that doesn't spam stderr with per-request log lines."""

    def log_message(self, *_args) -> None:  # noqa: D401 — silence access logs
        return


@contextlib.contextmanager
def _serve_artifact_dir(root: Path, diagnostics: list[str] | None = None):
    """Serve ``root`` over an ephemeral loopback HTTP server.

    Generated apps frequently load ``<script type="module">`` or use ``fetch()``, both of
    which the browser blocks under ``file://`` (origin ``null``). Serving over
    ``http://127.0.0.1`` lets those execute so animation detection isn't a false negative.

    Yields the base URL, or ``None`` if a server can't be bound (caller falls back to
    ``file://``). Constrained: loopback only, ephemeral port, static read-only serving.
    """
    server = None
    try:
        handler = partial(_QuietHTTPRequestHandler, directory=str(root))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        yield f"http://127.0.0.1:{server.server_address[1]}"
    except Exception as exc:  # noqa: BLE001 — any bind/serve failure falls back to file://
        if diagnostics is not None:
            detail = f"{type(exc).__name__}: {exc}".strip().rstrip(":").strip()
            diagnostics.append(f"serve_artifact_bind_failed:{detail}")
        yield None
    finally:
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:  # noqa: BLE001
                pass


class AtlasPlaywrightSmokeVerifier:
    """Optional constrained browser smoke verifier for generated local HTML artifacts.

    - Only opens file:// URIs pointing to local artifacts (no arbitrary URLs).
    - Playwright unavailable → browser_smoke_skipped.
    - Results are supplemental to the static contract (AtlasVisualArtifactVerifier).
    """

    def verify(
        self,
        html_path: str | Path,
        *,
        task_description: str = "",
        expected_text: str | None = None,
        contract_id: str | None = None,
    ) -> dict:
        """Run browser smoke verification.

        When contract_id is provided the verifier selects only the checks that
        are relevant for that contract type:
          static_html_visual_v1        — page loads + no hard JS errors; no animation sampling
          animated_dom_visual_v1       — style-change sampling; canvas NOT required
          ui_component_visual_v1       — page loads + controls; optional interaction smoke
          interactive_web_app_visual_v1— page loads + state-change smoke
          canvas_animation_visual_v1   — canvas + frame changes required; no input/game state
          canvas_game_visual_v1        — full canvas + loop + optional input/game checks
          chart_visualization_v1       — page loads + chart element; no animation sampling
          None (legacy)                — falls back to keyword-based is_anim detection
        """
        html_path = Path(html_path).resolve()
        if not html_path.exists():
            return self._result("browser_smoke_failed", reason="html_file_missing",
                                contract_id=contract_id)

        if not _PLAYWRIGHT_AVAILABLE:
            return self._result("browser_smoke_skipped", reason="playwright_not_installed",
                                contract_id=contract_id)

        # Determine animation/canvas requirements from contract when available.
        # This prevents static_html or chart tasks from polling for style/canvas changes.
        _STATIC_CONTRACTS = {"static_html_visual_v1", "chart_visualization_v1"}
        _ANIMATION_CONTRACTS = {
            "animated_dom_visual_v1", "ui_component_visual_v1",
            "interactive_web_app_visual_v1",
        }
        _CANVAS_CONTRACTS = {"canvas_animation_visual_v1", "canvas_game_visual_v1"}

        if contract_id in _STATIC_CONTRACTS:
            require_animation = False
            require_canvas = False
        elif contract_id in _CANVAS_CONTRACTS:
            require_animation = False   # canvas frame check replaces style-change check
            require_canvas = True
        elif contract_id in _ANIMATION_CONTRACTS:
            require_animation = True
            require_canvas = False
        else:
            # Legacy fallback: keyword-based detection
            require_animation = _is_animation_task(task_description)
            require_canvas = False   # canvas will be checked only if animation polling finds it

        console_errors: list[str] = []
        serve_warnings: list[str] = []

        try:
            with _playwright_event_loop_policy(), sync_playwright() as pw, _serve_artifact_dir(html_path.parent, serve_warnings) as base_url:
                target = f"{base_url}/{quote(html_path.name)}" if base_url else html_path.as_uri()
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.on("console", lambda msg: console_errors.append(msg.text)
                        if msg.type in ("error", "warning") else None)
                page.on("pageerror", lambda err: console_errors.append(str(err)))

                page.goto(target, wait_until="domcontentloaded", timeout=10000)
                page.wait_for_timeout(100)

                # Check for JS errors (ReferenceError / SyntaxError are hard failures).
                # Add local static diagnostics so repair planning can target common
                # generated-game wiring mistakes instead of producing generic tests.
                diagnostic = self._diagnose_js_wiring(html_path, console_errors)
                js_errors = self._hard_js_errors(console_errors, html_path)
                if js_errors or diagnostic in {
                    "module_script_mismatch",
                    "missing_script_src",
                    "missing_import_target",
                    "import_path_case_mismatch",
                }:
                    browser.close()
                    return self._result("browser_smoke_failed", reason=self._js_error_reason(diagnostic),
                                        console_errors=console_errors, diagnostics=diagnostic,
                                        contract_id=contract_id)

                # Check expected visible text
                if expected_text:
                    try:
                        page.wait_for_selector(f"text={expected_text}", timeout=3000)
                    except Exception:
                        browser.close()
                        return self._result("browser_smoke_failed", reason="expected_text_missing",
                                            console_errors=console_errors, contract_id=contract_id)

                # --- Static-only contracts: skip all animation/canvas sampling ---
                if contract_id in _STATIC_CONTRACTS:
                    browser.close()
                    return self._result(
                        "browser_smoke_passed",
                        console_errors=console_errors,
                        diagnostics=self._diagnostics({}, serve_warnings),
                        contract_id=contract_id,
                    )

                # --- Canvas contracts: require canvas frame changes ---
                if require_canvas:
                    self._nudge_interaction(page)
                    canvas = self._check_canvas_changes_over_time(page)
                    browser.close()
                    if canvas.get("changed"):
                        return self._result(
                            "browser_smoke_passed",
                            console_errors=console_errors,
                            diagnostics=self._diagnostics({"canvas": canvas}, serve_warnings),
                            contract_id=contract_id,
                        )
                    if not canvas.get("present"):
                        return self._result(
                            "browser_smoke_failed",
                            reason="canvas_frame_not_detected:canvas_missing",
                            console_errors=console_errors,
                            diagnostics=self._diagnostics({"canvas": canvas}, serve_warnings),
                            contract_id=contract_id,
                        )
                    warning = canvas.get("warning", "no_frame_change")
                    return self._result(
                        "browser_smoke_failed",
                        reason=f"canvas_frame_not_detected:{warning}",
                        console_errors=console_errors,
                        diagnostics=self._diagnostics({"canvas": canvas}, serve_warnings),
                        contract_id=contract_id,
                    )

                # --- Animation contracts (DOM/CSS): style-change sampling, canvas NOT required ---
                if require_animation:
                    # Many generated animations gate their loop on a first interaction.
                    # A single guarded nudge starts them before sampling.
                    self._nudge_interaction(page)
                    style_changed = self._check_style_changes_over_time(page)
                    # For animated_dom contracts, canvas changes are acceptable as secondary evidence
                    # but canvas is NOT required.
                    canvas = self._check_canvas_changes_over_time(page) if not style_changed else {}
                    browser.close()
                    if style_changed or canvas.get("changed"):
                        return self._result(
                            "browser_smoke_passed",
                            console_errors=console_errors,
                            diagnostics=self._diagnostics({"style_changed": style_changed, "canvas": canvas}, serve_warnings),
                            contract_id=contract_id,
                        )
                    # Contract-aware path uses motion_not_detected (signal name);
                    # legacy fallback (no contract_id) keeps the original animation_not_detected.
                    _base_reason = "motion_not_detected" if contract_id else "animation_not_detected"
                    if canvas.get("warning"):
                        return self._result(
                            "browser_smoke_failed",
                            reason=f"{_base_reason}:{canvas['warning']}",
                            console_errors=console_errors,
                            diagnostics=self._diagnostics({"canvas": canvas}, serve_warnings),
                            contract_id=contract_id,
                        )
                    return self._result(
                        "browser_smoke_failed",
                        reason=_base_reason,
                        console_errors=console_errors,
                        diagnostics=self._diagnostics({"canvas": canvas}, serve_warnings),
                        contract_id=contract_id,
                    )

                # --- No animation required (static page, non-animation component) ---
                browser.close()
                if js_errors:
                    return self._result("browser_smoke_failed", reason="js_error",
                                        console_errors=console_errors, contract_id=contract_id)

                return self._result("browser_smoke_passed", console_errors=console_errors,
                                    diagnostics=self._diagnostics({}, serve_warnings),
                                    contract_id=contract_id)

        except Exception as exc:  # noqa: BLE001
            # The python package can be importable while the browser binary is missing
            # (a fresh machine that never ran ``playwright install``). That surfaced as an
            # opaque ``playwright_error`` and got treated as a visual *failure*, hiding the
            # one actionable fix. Detect it and report a clear, install-guided *skip* — the
            # same soft handling as a missing package — instead of a product defect.
            if _is_browser_not_installed_error(exc):
                return self._result(
                    "browser_smoke_skipped",
                    reason="playwright_browser_not_installed: run `playwright install chromium`",
                    console_errors=console_errors,
                    contract_id=contract_id,
                )
            detail = f"{type(exc).__name__}: {exc}".strip().rstrip(":").strip()
            return self._result("browser_smoke_failed", reason=f"playwright_error: {detail}",
                                console_errors=console_errors, contract_id=contract_id)

    def _nudge_interaction(self, page) -> None:
        """Best-effort: start interaction-gated animations/games with one click in the
        viewport centre plus a couple of common start/move keys. No arbitrary or
        user-supplied automation — failures are swallowed so sampling proceeds regardless."""
        try:
            size = page.viewport_size or {"width": 800, "height": 600}
            page.mouse.click(int(size["width"]) // 2, int(size["height"]) // 2)
        except Exception:  # noqa: BLE001
            pass
        for key in ("Space", "ArrowRight", "Enter"):
            try:
                page.keyboard.press(key)
            except Exception:  # noqa: BLE001
                pass

    def _check_style_changes_over_time(self, page) -> bool:
        """Poll computed transform + color on body/canvas for up to _ANIMATION_MAX_WAIT_MS."""
        script = """\
        () => {
            const el = document.querySelector('canvas') || document.body;
            const s = window.getComputedStyle(el);
            return s.transform + '|' + s.color + '|' + s.backgroundColor;
        }
        """
        try:
            baseline = page.evaluate(script)
            deadline = time.time() + _sample_max_wait_ms() / 1000
            while time.time() < deadline:
                time.sleep(_sample_interval_ms() / 1000)
                current = page.evaluate(script)
                if current != baseline:
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False


    def _check_canvas_changes_over_time(self, page) -> dict:
        """Sample local file:// canvas pixels/data URL over a short interval.

        This is intentionally constrained: it runs only inside the already-opened
        local file artifact and does not navigate, fetch, click, or execute
        arbitrary user-provided automation. Tainted/inaccessible canvases return a
        soft warning so static verification can decide whether to fail.
        """
        script = """\
        () => {
            const canvases = Array.from(document.querySelectorAll('canvas'));
            if (!canvases.length) return {present:false, samples:[]};
            const out = [];
            for (const canvas of canvases.slice(0, 3)) {
                try {
                    const w = canvas.width || canvas.clientWidth || 0;
                    const h = canvas.height || canvas.clientHeight || 0;
                    if (!w || !h) { out.push({empty:true, width:w, height:h}); continue; }
                    const ctx = canvas.getContext('2d');
                    if (!ctx) { out.push({no2d:true, width:w, height:h}); continue; }
                    const sampleW = Math.max(1, Math.min(32, Math.floor(w)));
                    const sampleH = Math.max(1, Math.min(32, Math.floor(h)));
                    const scratch = document.createElement('canvas');
                    scratch.width = sampleW;
                    scratch.height = sampleH;
                    const scratchCtx = scratch.getContext('2d', {willReadFrequently:true});
                    if (!scratchCtx) { out.push({noSampleContext:true, width:w, height:h}); continue; }
                    scratchCtx.drawImage(canvas, 0, 0, sampleW, sampleH);
                    const data = scratchCtx.getImageData(0, 0, sampleW, sampleH).data;
                    let gridHash = 2166136261;
                    for (let i = 0; i < data.length; i++) {
                        gridHash ^= data[i];
                        gridHash = Math.imul(gridHash, 16777619) >>> 0;
                    }
                    let dataHash = '';
                    try { dataHash = scratch.toDataURL('image/png').slice(0, 256); } catch (_e) {}
                    out.push({width:w, height:h, sampleWidth:sampleW, sampleHeight:sampleH, gridHash:String(gridHash), dataHash});
                } catch (e) {
                    out.push({error:String(e && e.message || e)});
                }
            }
            return {present:true, samples:out};
        }
        """
        try:
            baseline = page.evaluate(script)
            deadline = time.time() + _sample_max_wait_ms() / 1000
            while time.time() < deadline:
                time.sleep(_sample_interval_ms() / 1000)
                current = page.evaluate(script)
                if current != baseline:
                    return {"present": True, "changed": True, "baseline": baseline, "current": current}
            if not baseline.get("present"):
                return {"present": False, "changed": False}
            sample_errors = [str(s.get("error")) for s in (baseline.get("samples") or []) if isinstance(s, dict) and s.get("error")]
            if sample_errors:
                return {"present": True, "changed": False, "warning": "canvas_inaccessible", "errors": sample_errors[:3]}
            return {"present": True, "changed": False}
        except Exception as exc:  # noqa: BLE001
            return {"present": False, "changed": False, "warning": "canvas_inaccessible", "errors": [str(exc)]}

    def _hard_js_errors(self, console_errors: list[str], html_path: Path | None = None) -> list[str]:
        hard_markers = (
            "ReferenceError",
            "SyntaxError",
            " is not defined",
            "Cannot use import statement",
            "Unexpected token 'export'",
            "Failed to resolve module specifier",
            "Failed to fetch dynamically imported module",
        )
        entry_refs = self._entry_script_refs(html_path) if html_path else []
        hard: list[str] = []
        for error in console_errors:
            if any(marker in error for marker in hard_markers):
                hard.append(error)
                continue
            if ("Failed to load resource" in error or "ERR_FILE_NOT_FOUND" in error or "net::" in error) and self._mentions_entry_script(error, entry_refs):
                hard.append(error)
        return hard

    def _entry_script_refs(self, html_path: Path | None) -> list[str]:
        if html_path is None:
            return []
        try:
            html = html_path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return []
        refs: list[str] = []
        for attrs, _body in re.findall(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL):
            src_m = re.search(r'\bsrc\s*=\s*([\'"])(.*?)\1', attrs, flags=re.IGNORECASE)
            if not src_m:
                continue
            src = src_m.group(2).split("#", 1)[0].split("?", 1)[0]
            if not src or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", src) or src.startswith("//"):
                continue
            refs.extend([src, src.lstrip("/"), Path(src).name])
        return [ref for ref in dict.fromkeys(refs) if ref]

    def _mentions_entry_script(self, error: str, entry_refs: list[str]) -> bool:
        if not entry_refs:
            return False
        normalized = error.replace("\\", "/")
        return any(ref.replace("\\", "/") in normalized for ref in entry_refs)

    def _js_error_reason(self, diagnostic: str) -> str:
        return f"js_error:{diagnostic}" if diagnostic else "js_error"

    def _diagnose_js_wiring(self, html_path: Path, console_errors: list[str]) -> str:
        try:
            html = html_path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            html = ""
        script_tags = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, flags=re.IGNORECASE | re.DOTALL)
        srcs: list[tuple[str, bool]] = []
        inline_non_module_uses_modules = False
        for attrs, body in script_tags:
            is_module = bool(re.search(r"\btype\s*=\s*(['\"])module\1", attrs, flags=re.IGNORECASE))
            src_m = re.search(r"\bsrc\s*=\s*(['\"])(.*?)\1", attrs, flags=re.IGNORECASE)
            if src_m:
                srcs.append((src_m.group(2), is_module))
            elif not is_module and re.search(r"\b(import|export)\b", body):
                inline_non_module_uses_modules = True
        missing_script = self._missing_script_src(html_path, [s for s, _ in srcs])
        missing_import = self._missing_import_target(html_path, [s for s, _ in srcs])
        if missing_script:
            return "missing_script_src"
        if missing_import:
            return missing_import
        loaded_non_module_with_modules = False
        for src, is_module in srcs:
            if is_module:
                continue
            target = self._safe_child_path(html_path.parent, src)
            if target and target.exists():
                text = target.read_text(encoding="utf-8", errors="replace")[:200000]
                if re.search(r"(^|\n)\s*(import|export)\b", text):
                    loaded_non_module_with_modules = True
                    break
        joined = "\n".join(console_errors)
        if inline_non_module_uses_modules or loaded_non_module_with_modules or "Cannot use import statement" in joined or "Unexpected token 'export'" in joined:
            return "module_script_mismatch"
        if "Failed to resolve module specifier" in joined or "Failed to fetch dynamically imported module" in joined:
            return "missing_import_target"
        return ""

    def _missing_script_src(self, html_path: Path, srcs: list[str]) -> bool:
        for src in srcs:
            target = self._safe_child_path(html_path.parent, src)
            if target is not None and not target.exists():
                return True
        return False

    def _missing_import_target(self, html_path: Path, srcs: list[str]) -> str:
        roots = []
        for src in srcs:
            target = self._safe_child_path(html_path.parent, src)
            if target is not None and target.exists():
                roots.append(target)
        # Also inspect generated js/*.js modules next to the artifact.
        js_dir = html_path.parent / "js"
        if js_dir.is_dir():
            roots.extend(sorted(js_dir.glob("*.js"))[:50])
        seen: set[Path] = set()
        for js in roots:
            if js in seen:
                continue
            seen.add(js)
            text = js.read_text(encoding="utf-8", errors="replace")[:200000]
            for spec in re.findall(r"(?:import\s+(?:[^'\"]+?\s+from\s+)?|export\s+[^'\"]*?from\s+|import\s*\()\s*['\"]([^'\"]+)['\"]", text):
                if not spec.startswith(('.', '/')):
                    continue
                target = self._safe_child_path(js.parent, spec)
                if target and target.exists() and target.name != Path(spec).name:
                    return "import_path_case_mismatch"
                candidates = [target] if target else []
                if target and target.suffix == "":
                    candidates.extend([target.with_suffix(".js"), target / "index.js"])
                if not any(c.exists() for c in candidates if c is not None):
                    return self._missing_target_kind(candidates)
        return ""

    def _missing_target_kind(self, candidates: list[Path | None]) -> str:
        for candidate in candidates:
            if candidate is None:
                continue
            parent = candidate.parent
            if not parent.is_dir():
                continue
            wanted = candidate.name.lower()
            try:
                if any(child.name.lower() == wanted for child in parent.iterdir()):
                    return "import_path_case_mismatch"
            except Exception:  # noqa: BLE001
                pass
        return "missing_import_target"

    def _safe_child_path(self, root: Path, ref: str) -> Path | None:
        try:
            if not ref or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", ref) or ref.startswith("//"):
                return None
            clean = ref.split("#", 1)[0].split("?", 1)[0]
            target = (root / clean.lstrip("/")).resolve()
            target.relative_to(root.resolve())
            return target
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _diagnostics(payload: dict, serve_warnings: list[str]) -> dict:
        out = dict(payload)
        if serve_warnings:
            out["serve_warnings"] = list(serve_warnings)
        return out

    @staticmethod
    def _result(
        status: str,
        *,
        reason: str = "",
        console_errors: list | None = None,
        diagnostics: dict | str | None = None,
        contract_id: str | None = None,
    ) -> dict:
        out: dict = {"status": status}
        if reason:
            out["reason"] = reason
        if console_errors is not None:
            out["console_errors"] = console_errors
        if diagnostics:
            out["diagnostics"] = diagnostics
        if contract_id is not None:
            out["contract_id"] = contract_id
        return out
