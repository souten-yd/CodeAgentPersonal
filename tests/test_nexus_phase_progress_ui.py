from pathlib import Path
import subprocess


def test_format_status_uses_phase_step_marker_contract():
    text = Path('web/js/nexus.js').read_text(encoding='utf-8')
    assert 'phaseIndex' in text
    assert 'phaseTotal' in text
    assert '`${phaseIndex}/${phaseTotal} ${phaseLabel}`' in text


def test_format_status_compact_renders_gap_analysis_phase_step():
    script = """
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('web/js/nexus.js', 'utf8');
const sandbox = { window: {}, document: { getElementById: () => null, createElement: () => ({style:{}, textContent:'', id:'', appendChild:()=>{}}), head: { appendChild: () => {} } } };
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const out = sandbox.formatNexusResearchStatusCompact(
  { status: 'running' },
  { health: { current_phase: 'gap_analysis', phase_index: 8, phase_total: 10, phase_label: '根拠検証・不足確認中' } },
  {}
);
if (!String(out.progress || '').includes('8/10 根拠検証・不足確認中')) process.exit(1);
"""
    completed = subprocess.run(["node", "-e", script], check=False)
    assert completed.returncode == 0


def test_format_status_compact_renders_followup_phase_step():
    script = """
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('web/js/nexus.js', 'utf8');
const sandbox = { window: {}, document: { getElementById: () => null, createElement: () => ({style:{}, textContent:'', id:'', appendChild:()=>{}}), head: { appendChild: () => {} } } };
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const out = sandbox.formatNexusResearchStatusCompact(
  { status: 'running' },
  { health: { current_phase: 'followup_searching', phase_index: 9, phase_total: 10, phase_label: '追加調査中' } },
  {}
);
if (!String(out.progress || '').includes('9/10 追加調査中')) process.exit(1);
"""
    completed = subprocess.run(["node", "-e", script], check=False)
    assert completed.returncode == 0
