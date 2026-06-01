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
    assert 'function visualFailureDetails' in js
    assert 'metadata.visual_contract' in js
    assert "w.startsWith('visual_missing:')" in js
    assert 'browser_smoke=' in js
    assert 'requestAnimationFrame loop' in js


def test_claude_panel_clarification_queue_and_dedupe_contract():
    js = Path('web/js/atlas_claude_panel.js').read_text(encoding='utf-8')
    assert 'function firstPendingClarificationQuestion' in js
    assert '確認が必要です: ${index}/${total}' in js
    assert 'question_id: questionId' in js
    assert 'answer_text: answerText' in js
    assert 'pending_question_count' in js
    assert "dataset.atlasClarificationPrompt = 'true'" in js
    assert "dataset.atlasPlanCard = 'true'" in js
    assert "dataset.planRevisionId" in js
    assert "dataset.atlasStageBlock = 'true'" in js
    assert 'clarification revision/gate rerun required' in js


def test_dashboard_recovery_uses_primary_verification_reason():
    js = Path('web/js/atlas_dashboard.js').read_text(encoding='utf-8')
    assert 'primary_verification_reason' in js
    assert 'Verification failed: ${primary}' in js
    assert 'console_errors:' in js
