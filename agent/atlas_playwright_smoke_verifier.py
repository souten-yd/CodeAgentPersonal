from __future__ import annotations

import contextlib
import re
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

# Animation tasks require computed style changes over time
_ANIMATION_TASK_HINT = ("animat", "wave", "oscillat", "bounce", "spin", "rotat", "pulse", "fade",
                        "move", "motion", "color chang", "hue")

# How long to wait for animations to produce a change (ms). Generous enough for slow
# first-frame animations and games that start a beat after load.
_ANIMATION_POLL_INTERVAL_MS = 100
_ANIMATION_MAX_WAIT_MS = 3500


def _is_animation_task(task_description: str) -> bool:
    desc = task_description.lower()
    return any(hint in desc for hint in _ANIMATION_TASK_HINT)


class _QuietHTTPRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler that doesn't spam stderr with per-request log lines."""

    def log_message(self, *_args) -> None:  # noqa: D401 — silence access logs
        return


@contextlib.contextmanager
def _serve_artifact_dir(root: Path):
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
    except Exception:  # noqa: BLE001 — any bind/serve failure falls back to file://
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

    def verify(self, html_path: str | Path, *, task_description: str = "",
               expected_text: str | None = None) -> dict:
        html_path = Path(html_path).resolve()
        if not html_path.exists():
            return self._result("browser_smoke_failed", reason="html_file_missing")

        if not _PLAYWRIGHT_AVAILABLE:
            return self._result("browser_smoke_skipped", reason="playwright_not_installed")

        is_anim = _is_animation_task(task_description)
        console_errors: list[str] = []

        try:
            with sync_playwright() as pw, _serve_artifact_dir(html_path.parent) as base_url:
                target = f"{base_url}/{quote(html_path.name)}" if base_url else html_path.as_uri()
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.on("console", lambda msg: console_errors.append(msg.text)
                        if msg.type in ("error", "warning") else None)
                page.on("pageerror", lambda err: console_errors.append(str(err)))

                page.goto(target, wait_until="domcontentloaded", timeout=10000)

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
                                        console_errors=console_errors, diagnostics=diagnostic)

                # Check expected visible text
                if expected_text:
                    try:
                        page.wait_for_selector(f"text={expected_text}", timeout=3000)
                    except Exception:
                        browser.close()
                        return self._result("browser_smoke_failed", reason="expected_text_missing",
                                            console_errors=console_errors)

                # For animation/canvas-game tasks: computed style alone misses most
                # canvas games because pixels mutate while canvas CSS stays constant.
                # First check styles, then sample canvas pixels/toDataURL over file:// only.
                if is_anim:
                    # Many generated games gate their loop on a first interaction (click to
                    # start / key to move). A single guarded nudge starts them before sampling
                    # so an interaction-gated animation isn't reported as "not detected".
                    self._nudge_interaction(page)
                    style_changed = self._check_style_changes_over_time(page)
                    canvas = self._check_canvas_changes_over_time(page)
                    browser.close()
                    if style_changed or canvas.get("changed"):
                        return self._result("browser_smoke_passed", console_errors=console_errors,
                                            diagnostics={"style_changed": style_changed, "canvas": canvas})
                    if canvas.get("warning"):
                        return self._result("browser_smoke_failed",
                                            reason=f"animation_not_detected:{canvas['warning']}",
                                            console_errors=console_errors, diagnostics={"canvas": canvas})
                    return self._result("browser_smoke_failed",
                                        reason="animation_not_detected",
                                        console_errors=console_errors, diagnostics={"canvas": canvas})
                else:
                    browser.close()
                    # Static HTML with no animation — would fail for animation tasks, but here
                    # task is not animation, so we just verify page loaded without errors
                    if js_errors:
                        return self._result("browser_smoke_failed", reason="js_error",
                                            console_errors=console_errors)

                return self._result("browser_smoke_passed", console_errors=console_errors)

        except Exception as exc:  # noqa: BLE001
            return self._result("browser_smoke_failed", reason=f"playwright_error: {exc}",
                                console_errors=console_errors)

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
            deadline = time.time() + _ANIMATION_MAX_WAIT_MS / 1000
            while time.time() < deadline:
                time.sleep(_ANIMATION_POLL_INTERVAL_MS / 1000)
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
            deadline = time.time() + _ANIMATION_MAX_WAIT_MS / 1000
            while time.time() < deadline:
                time.sleep(_ANIMATION_POLL_INTERVAL_MS / 1000)
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
    def _result(status: str, *, reason: str = "", console_errors: list | None = None, diagnostics: dict | str | None = None) -> dict:
        out: dict = {"status": status}
        if reason:
            out["reason"] = reason
        if console_errors is not None:
            out["console_errors"] = console_errors
        if diagnostics:
            out["diagnostics"] = diagnostics
        return out
