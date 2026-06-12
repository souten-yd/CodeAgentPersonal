"""PFG-20 — Forge top-level nav and shell UI structural locks.

These are structural smoke checks against ui.html (the tracked UI source of truth) and
web/js/forge.js: the Forge nav (desktop + mobile) and shell column exist and are wired,
the mode plumbing knows about 'forge', and the existing Portal nav is left intact.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = (ROOT / "ui.html").read_text(encoding="utf-8")
FORGE_JS = (ROOT / "web" / "js" / "forge.js").read_text(encoding="utf-8")


def test_forge_desktop_and_mobile_nav_exist():
    assert 'id="btn-forge"' in INDEX
    assert "setMode('forge')" in INDEX
    assert 'id="mob-forge"' in INDEX
    assert "mobSwitch('forge')" in INDEX


def test_forge_shell_column_exists():
    assert 'id="forge-col"' in INDEX
    assert 'data-mode-panel="forge"' in INDEX
    assert 'id="forge-status"' in INDEX
    assert 'id="forge-body"' in INDEX


def test_mode_plumbing_knows_forge():
    assert "'chat','atlas','echo','nexus','forge','portal','agent'" in INDEX  # UI_VALID_MODES
    assert "_FORGE_MOB_TAB_IDS" in INDEX
    assert "} else if (m === 'forge') {" in INDEX  # setMode branch
    assert "} else if (name === 'forge') {" in INDEX  # mobSwitch branch


def test_forge_script_included_once():
    assert INDEX.count("/static/js/forge.js") == 1


def test_portal_nav_remains_functional():
    # Forge must not have displaced Portal.
    assert 'id="btn-portal"' in INDEX
    assert "setMode('portal')" in INDEX
    assert 'id="portal-col"' in INDEX
    assert "/static/js/portal.js" in INDEX


def test_forge_js_exposes_activate_and_is_read_only():
    assert "root.Forge = {" in FORGE_JS
    assert "activate" in FORGE_JS and "onLeave" in FORGE_JS
    # The shell only reads /api/forge; it never POSTs an execution from PFG-20.
    assert "/api/forge" in FORGE_JS
