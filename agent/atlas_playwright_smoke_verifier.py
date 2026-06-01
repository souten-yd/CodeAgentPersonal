from __future__ import annotations

import re
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright  # type: ignore[import]
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

# Animation tasks require computed style changes over time
_ANIMATION_TASK_HINT = ("animat", "wave", "oscillat", "bounce", "spin", "rotat", "pulse", "fade",
                        "move", "motion", "color chang", "hue")

# How long to wait for animations to produce a change (ms)
_ANIMATION_POLL_INTERVAL_MS = 100
_ANIMATION_MAX_WAIT_MS = 2000


def _is_animation_task(task_description: str) -> bool:
    desc = task_description.lower()
    return any(hint in desc for hint in _ANIMATION_TASK_HINT)


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

        uri = html_path.as_uri()
        is_anim = _is_animation_task(task_description)
        console_errors: list[str] = []

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page()
                page.on("console", lambda msg: console_errors.append(msg.text)
                        if msg.type in ("error", "warning") else None)
                page.on("pageerror", lambda err: console_errors.append(str(err)))

                page.goto(uri, wait_until="domcontentloaded", timeout=10000)

                # Check for JS errors (ReferenceError / SyntaxError are hard failures).
                # Add local static diagnostics so repair planning can target common
                # generated-game wiring mistakes instead of producing generic tests.
                js_errors = self._hard_js_errors(console_errors)
                if js_errors:
                    diagnostic = self._diagnose_js_wiring(html_path, console_errors)
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
                    const pts = [[0.25,0.25],[0.5,0.5],[0.75,0.75],[0.5,0.25],[0.25,0.75]];
                    const pixels = pts.map(([px, py]) => {
                        const x = Math.max(0, Math.min(w - 1, Math.floor(w * px)));
                        const y = Math.max(0, Math.min(h - 1, Math.floor(h * py)));
                        return Array.from(ctx.getImageData(x, y, 1, 1).data).join(',');
                    }).join('|');
                    let dataHash = '';
                    try { dataHash = canvas.toDataURL('image/png').slice(0, 256); } catch (_e) {}
                    out.push({width:w, height:h, pixels, dataHash});
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

    def _hard_js_errors(self, console_errors: list[str]) -> list[str]:
        markers = ("ReferenceError", "SyntaxError", "TypeError", "Cannot use import statement", "Unexpected token 'export'", "Failed to resolve module specifier", "Failed to load resource", "ERR_FILE_NOT_FOUND", "net::")
        return [e for e in console_errors if any(m in e for m in markers)]

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
        if "Failed to resolve module specifier" in joined or "ERR_FILE_NOT_FOUND" in joined:
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
                    return "case_sensitive_import_path_mismatch"
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
