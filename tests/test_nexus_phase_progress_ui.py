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


def test_recursive_debug_details_are_included_in_debug_render_path():
    script = """
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync('web/js/nexus.js', 'utf8');
const sandbox = { window: {}, document: { getElementById: () => null, createElement: () => ({style:{}, textContent:'', id:'', appendChild:()=>{}}), head: { appendChild: () => {} } } };
vm.createContext(sandbox);
vm.runInContext(code, sandbox);
const answer = {
  followup_queries_generated: 8,
  followup_searches_executed: 1,
  recursive_reserved_downloads: 30,
  recursive_download_attempt_count: 12,
  recursive_download_budget_remaining: 18,
  recursive_followup_skip_reason: 'duplicate_followup_sources'
};
const details = sandbox.formatNexusRecursiveDebugDetails(answer);
const compact = sandbox.formatNexusResearchStatusCompact({ status: 'running' }, {}, answer);
const merged = (compact.debugDetails || []).join('\\n') + '\\n' + details.join('\\n');
const must = [
  'Follow-up queries generated: 8',
  'Follow-up searches executed: 1',
  'Recursive download reserved: 30',
  'Recursive downloads attempted: 12',
  'Recursive downloads remaining: 18',
  'Follow-up skip reason: duplicate_followup_sources'
];
if (!must.every((v) => merged.includes(v))) process.exit(1);
"""
    completed = subprocess.run(["node", "-e", script], check=False)
    assert completed.returncode == 0
