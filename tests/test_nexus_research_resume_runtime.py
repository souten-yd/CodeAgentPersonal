from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = (ROOT / 'ui.html').read_text(encoding='utf-8')


def _extract(name: str) -> str:
    m = re.search(rf"(?:async\s+)?function\s+{name}\s*\([^)]*\)\s*{{", UI)
    assert m, f"missing function {name}"
    i = m.start()
    depth = 0
    j = m.end() - 1
    while j < len(UI):
        ch = UI[j]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return UI[i:j+1]
        j += 1
    raise AssertionError(f"unterminated function {name}")


def _run_node_test(js_test_body: str) -> dict:
    code = "\n".join([
        "const TERMINAL_RESEARCH_STATUSES = new Set(['completed','failed','cancelled','canceled','error','done']);",
        "let nexusDeepResearchResumeStarted = false;",
        "let nexusDeepResearchResumeCompleted = false;",
        "let nexusDeepResearchResumeRetryScheduled = false;",
        "let nexusDeepResearchJobId = '';",
        "let nexusDeepResearchCurrentRunMeta = null;",
        "let currentProject = 'default';",
        "const API = 'http://api';",
        "const logs = [];",
        "const previousRuns = [];",
        "const timeouts = [];",
        "globalThis.console = { debug: (...a) => logs.push(a.join(' ')), warn:()=>{}, log:(...a)=>process.stdout.write(a.join(' ') + '\\n') };",
        "globalThis.document = { getElementById: () => ({ disabled: true }) };",
        "globalThis.localStorage = { _m:new Map(), getItem(k){return this._m.get(k)||'';}, setItem(k,v){this._m.set(k,String(v));} };",
        "globalThis.setNexusDeepStatus = ()=>{};",
        "globalThis.refreshNexusDeepBundle = async ()=>{};",
        "globalThis.refreshNexusDeepDebug = async ()=>{};",
        "globalThis.pollNexusDeepResearch = async ()=>{};",
        "globalThis.pushNexusDeepPreviousRun = (j)=>previousRuns.push(j);",
        "globalThis.setTimeout = (fn, ms) => { timeouts.push(ms); return 1; };",
        "globalThis.clearTimeout = ()=>{};",
        _extract('setNexusDeepCurrentJob'),
        _extract('isNexusResearchJobLike'),
        _extract('isNexusResearchTerminalStatus'),
        _extract('rankNexusResearchJob'),
        _extract('hydrateNexusDeepTerminalLatest'),
        _extract('fetchWithTimeout'),
        _extract('resumeLatestNexusResearchJob'),
        js_test_body,
    ])
    proc = subprocess.run(['node', '-e', code], cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(proc.stdout.strip())


def test_runtime_resume_active_timeout_and_sources() -> None:
    result = _run_node_test(
        """
(async () => {
  let call = 0;
  globalThis.fetch = async (url) => {
    call += 1;
    if (url.includes('/active')) {
      if (call === 1) { const e = new Error('operation aborted'); e.name = 'AbortError'; throw e; }
      return { ok:true, json: async()=>({jobs:[{job_id:'research_srv',status:'running',metadata:{created_by:'nexus_research',query:'server query'}}]}) };
    }
    return { ok:true, json: async()=>({items:[{job_id:'ingest_terminal',status:'completed',metadata:{created_by:'uploader',query:'latest q'}}]}) };
  };
  await resumeLatestNexusResearchJob();
  const firstRetryScheduled = timeouts.includes(7000);
  await resumeLatestNexusResearchJob();
  const activePreferred = nexusDeepResearchJobId === 'research_srv' && nexusDeepResearchCurrentRunMeta.query === 'server query';
  console.log(JSON.stringify({ firstRetryScheduled, activePreferred, logsCount: logs.length }));
})();
"""
    )
    assert result['firstRetryScheduled'] is True
    assert result['activePreferred'] is True


def test_runtime_terminal_latest_hydration_and_non_research_skip() -> None:
    result = _run_node_test(
        """
(async () => {
  let answerCalls = 0;
  globalThis.refreshNexusDeepAnswer = async () => { answerCalls += 1; };
  globalThis.fetch = async (url) => {
    if (url.includes('/active')) return { ok:true, json: async()=>({jobs:[{job_id:'ingest_1',status:'running',metadata:{created_by:'uploader'}}]}) };
    return { ok:true, json: async()=>({items:[{job_id:'research_done',status:'completed',metadata:{created_by:'nexus_research',query:'terminal q'}}]}) };
  };
  await resumeLatestNexusResearchJob();
  const nonResearchNotRestored = nexusDeepResearchJobId === '';
  const pushedTerminal = previousRuns.length === 1 && previousRuns[0].query === 'terminal q';
  const answerHydrated = answerCalls === 1;
  delete globalThis.refreshNexusDeepAnswer;
  await hydrateNexusDeepTerminalLatest('research_done_2');
  console.log(JSON.stringify({ nonResearchNotRestored, pushedTerminal, answerHydrated }));
})();
"""
    )
    assert result['nonResearchNotRestored'] is True
    assert result['pushedTerminal'] is True
    assert result['answerHydrated'] is True
