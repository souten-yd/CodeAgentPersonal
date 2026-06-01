from __future__ import annotations
from pathlib import Path


def test_claude_panel_renders_precise_verification_reason_and_recovery_primary():
    js = Path('web/js/atlas_claude_panel.js').read_text(encoding='utf-8')
    assert 'function preciseVerificationReason' in js
    assert "reason.startsWith('verification_failed:')" in js
    assert 'primary_verification_reason' in js
    assert 'Verification failed: ${primary}' in js
    assert 'console_errors:' in js
    assert 'verification_failed:${precise}' in js
    assert 'function verificationConsoleErrors' in js


def test_dashboard_recovery_uses_primary_verification_reason():
    js = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    assert 'primary_verification_reason' in js
    assert 'Verification failed: ${primary}' in js
    assert 'console_errors:' in js
