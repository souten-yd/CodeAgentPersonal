from __future__ import annotations

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

                # Check for JS errors (ReferenceError / SyntaxError are hard failures)
                js_errors = [e for e in console_errors if "ReferenceError" in e or "SyntaxError" in e]
                if js_errors:
                    browser.close()
                    return self._result("browser_smoke_failed", reason="js_error",
                                        console_errors=console_errors)

                # Check expected visible text
                if expected_text:
                    try:
                        page.wait_for_selector(f"text={expected_text}", timeout=3000)
                    except Exception:
                        browser.close()
                        return self._result("browser_smoke_failed", reason="expected_text_missing",
                                            console_errors=console_errors)

                # For animation tasks: check that computed transform or color changes over time
                if is_anim:
                    changed = self._check_style_changes_over_time(page)
                    browser.close()
                    if not changed:
                        return self._result("browser_smoke_failed",
                                            reason="animation_not_detected_no_style_change",
                                            console_errors=console_errors)
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

    @staticmethod
    def _result(status: str, *, reason: str = "", console_errors: list | None = None) -> dict:
        out: dict = {"status": status}
        if reason:
            out["reason"] = reason
        if console_errors is not None:
            out["console_errors"] = console_errors
        return out
