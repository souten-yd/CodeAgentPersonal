<template>
  <StatusCard title="Level-1 Readiness Diagnostics (read-only)">
    <p><b>enabled:</b> {{ diagnostics?.enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>runtime_level:</b> {{ diagnostics?.runtime_level || 'unknown' }}</p>
    <p><b>level1_execution_enabled:</b> {{ diagnostics?.level1_execution_enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>callable_execution_endpoint_enabled:</b> {{ diagnostics?.callable_execution_endpoint_enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>vue_execution_controls_enabled:</b> {{ diagnostics?.vue_execution_controls_enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>advisory_only:</b> {{ diagnostics?.advisory_only ? 'true' : 'false' }}</p>
    <p class="advisory-note"><b>Display note:</b> backend workflow_state remains authoritative. Local metadata comparison below is advisory only, not a readiness decision, and does not compute execution eligibility and does not decide readiness.</p>

    <div class="metadata-actions" role="group" aria-label="Readiness metadata comparison actions">
      <button type="button" class="filter-btn" :disabled="!hasDiagnostics" @click="saveCurrentAsBaseline">Save current snapshot</button>
      <button type="button" class="filter-btn" :disabled="!hasBaseline" @click="useSavedBaseline">Use saved baseline</button>
      <button type="button" class="filter-btn" :disabled="!hasPastedJson" @click="usePastedBaseline">Use pasted baseline</button>
      <button type="button" class="filter-btn" @click="clearComparison">Clear comparison</button>
      <button type="button" class="filter-btn" :disabled="!hasDiagnostics" @click="copyReadinessJson">Copy readiness JSON</button>
      <button type="button" class="filter-btn" :disabled="!hasDiagnostics" @click="downloadReadinessJson">Download readiness JSON</button>
      <button type="button" class="filter-btn" :disabled="!hasDiagnostics" @click="copyVisibleGateSummary">Copy visible gate summary</button>
      <span class="metadata-status">{{ comparisonStatus }}</span>
    </div>
    <div class="metadata-actions" role="group" aria-label="Readiness local history actions">
      <button type="button" class="filter-btn" :disabled="!hasDiagnostics" @click="saveCurrentToHistory">Save to local history</button>
      <button type="button" class="filter-btn" :disabled="!selectedHistoryId" @click="useHistoryBaseline">Use selected history baseline</button>
      <button type="button" class="filter-btn" :disabled="!historyEntries.length" @click="clearHistory">Clear local history</button>
      <span class="metadata-status">{{ historyStatus }}</span>
    </div>
    <div class="metadata-actions" role="group" aria-label="Readiness local history import export actions">
      <button type="button" class="filter-btn" :disabled="!historyEntries.length" @click="copyHistoryJson">Copy local history JSON</button>
      <button type="button" class="filter-btn" :disabled="!historyEntries.length" @click="downloadHistoryJson">Export local history JSON</button>
      <button type="button" class="filter-btn" :disabled="!hasHistoryImportJson" @click="importHistoryMerge">Merge imported history</button>
      <button type="button" class="filter-btn" :disabled="!hasHistoryImportJson" @click="importHistoryReplace">Replace local history</button>
      <button type="button" class="filter-btn" :disabled="!historyImportJson" @click="clearHistoryImportText">Clear import text</button>
      <input type="file" accept="application/json" @change="loadHistoryImportFile" />
      <span class="metadata-status">{{ historyImportStatus }}</span>
    </div>
    <textarea v-model="historyImportJson" rows="6" class="metadata-input" placeholder="Paste local history JSON array or object with history array."></textarea>
    <div class="comparison-box">
      <p><b>local history storage:</b> browser storage only; max entries: {{ HISTORY_MAX_ENTRIES }}</p>
      <select v-model="selectedHistoryId" :disabled="!historyEntries.length">
        <option value="">Select local history snapshot</option>
        <option v-for="entry in historyEntries" :key="entry.id" :value="entry.id">{{ entry.label }} — {{ entry.saved_at }}</option>
      </select>
      <ul v-if="historyEntries.length">
        <li v-for="entry in historyEntries" :key="entry.id">
          {{ entry.label }} — {{ entry.saved_at }}
          <button type="button" class="filter-btn" @click="deleteHistoryEntry(entry.id)">Delete</button>
        </li>
      </ul>
    </div>

    <textarea v-model="pastedSnapshotJson" rows="6" class="metadata-input" placeholder="Paste prior readiness JSON for local metadata comparison."></textarea>

    <div v-if="comparisonResult" class="comparison-box">
      <p><b>local metadata comparison:</b> available={{ comparisonResult.comparison_available ? 'true' : 'false' }}</p>
      <p v-if="comparisonResult.comparison_error"><b>comparison_error:</b> {{ comparisonResult.comparison_error }}</p>
      <ul v-if="comparisonResult.summary_delta">
        <li>required_gate_count Δ: {{ comparisonResult.summary_delta.required_gate_count }}</li>
        <li>missing_evidence_count Δ: {{ comparisonResult.summary_delta.missing_evidence_count }}</li>
        <li>satisfied_gate_count Δ: {{ comparisonResult.summary_delta.satisfied_gate_count }}</li>
        <li>unsatisfied_gate_count Δ: {{ comparisonResult.summary_delta.unsatisfied_gate_count }}</li>
      </ul>
      <ul>
        <li>enabled changed: {{ comparisonResult.disabled_status_delta.enabled_changed ? 'yes' : 'no' }}</li>
        <li>level1_execution_enabled changed: {{ comparisonResult.disabled_status_delta.level1_execution_changed ? 'yes' : 'no' }}</li>
        <li>callable_execution_endpoint_enabled changed: {{ comparisonResult.disabled_status_delta.callable_execution_endpoint_changed ? 'yes' : 'no' }}</li>
        <li>vue_execution_controls_enabled changed: {{ comparisonResult.disabled_status_delta.vue_execution_controls_changed ? 'yes' : 'no' }}</li>
        <li>runtime_level changed: {{ comparisonResult.disabled_status_delta.runtime_level_changed ? 'yes' : 'no' }}</li>
      </ul>
      <ul v-if="comparisonResult.added_gates.length || comparisonResult.removed_gates.length">
        <li>added gates: {{ comparisonResult.added_gates.join(', ') || '-' }}</li>
        <li>removed gates: {{ comparisonResult.removed_gates.join(', ') || '-' }}</li>
      </ul>
      <table v-if="comparisonResult.evidence_summary_delta_by_source.length" class="gate-table">
        <thead><tr><th>source</th><th>before_missing_evidence_count</th><th>after_missing_evidence_count</th><th>delta_missing_evidence_count</th></tr></thead>
        <tbody><tr v-for="row in comparisonResult.evidence_summary_delta_by_source" :key="row.source"><td>{{ row.source }}</td><td>{{ row.before_missing_evidence_count }}</td><td>{{ row.after_missing_evidence_count }}</td><td>{{ row.delta_missing_evidence_count }}</td></tr></tbody>
      </table>
      <table v-if="comparisonResult.changed_gates.length" class="gate-table">
        <thead><tr><th>gate_id</th><th>before_status</th><th>after_status</th><th>before_evidence_available</th><th>after_evidence_available</th><th>before_blocker_reason</th><th>after_blocker_reason</th></tr></thead>
        <tbody><tr v-for="gate in comparisonResult.changed_gates" :key="gate.gate_id"><td>{{ gate.gate_id }}</td><td>{{ gate.before_status }}</td><td>{{ gate.after_status }}</td><td>{{ gate.before_evidence_available }}</td><td>{{ gate.after_evidence_available }}</td><td>{{ gate.before_blocker_reason || '-' }}</td><td>{{ gate.after_blocker_reason || '-' }}</td></tr></tbody>
      </table>
    </div>
  </StatusCard>

<!-- Legacy compatibility tokens: test_requirement mutable evidence_required  evidence_required  Display filter: Show all gates Missing evidence only Backend-owned only Frontend-owned only Summary by owner Summary by source Summary by current_status mutation_performed execution_performed activeFilter summarizeBy( key: 'owner' | 'source' | 'current_status' ownerSummary sourceSummary statusSummary not execution eligibility -->

</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import StatusCard from './StatusCard.vue'
import { fetchLevel1ReadinessDiagnostics, type AtlasLevel1ReadinessDiagnostics, type AtlasLevel1ReadinessGateSource } from '../api/atlasClient'

type SnapshotComparisonResult = {
  summary_delta: { required_gate_count: number, missing_evidence_count: number, satisfied_gate_count: number, unsatisfied_gate_count: number } | null
  disabled_status_delta: { enabled_changed: boolean, level1_execution_changed: boolean, callable_execution_endpoint_changed: boolean, vue_execution_controls_changed: boolean, runtime_level_changed: boolean }
  evidence_summary_delta_by_source: Array<{ source: string, before_missing_evidence_count: number, after_missing_evidence_count: number, delta_missing_evidence_count: number }>
  changed_gates: Array<{ gate_id: string, before_status: string, after_status: string, before_evidence_available: boolean, after_evidence_available: boolean, before_blocker_reason: string, after_blocker_reason: string }>
  added_gates: string[]
  removed_gates: string[]
  comparison_available: boolean
  comparison_error: string | null
}

const diagnostics = ref<AtlasLevel1ReadinessDiagnostics | null>(null)
const baselineSnapshot = ref<AtlasLevel1ReadinessDiagnostics | null>(null)
const pastedSnapshotJson = ref('')
const comparisonResult = ref<SnapshotComparisonResult | null>(null)
const comparisonStatus = ref('Local metadata comparison idle.')
const hasDiagnostics = computed(() => diagnostics.value !== null)
const hasBaseline = computed(() => baselineSnapshot.value !== null)
const hasPastedJson = computed(() => pastedSnapshotJson.value.trim().length > 0)

function saveCurrentAsBaseline(): void {
  if (!diagnostics.value) return
  baselineSnapshot.value = JSON.parse(JSON.stringify(diagnostics.value))
  comparisonStatus.value = 'Saved current diagnostics as local baseline snapshot.'
}

function parsePastedBaseline(): AtlasLevel1ReadinessDiagnostics {
  const parsed = JSON.parse(pastedSnapshotJson.value) as AtlasLevel1ReadinessDiagnostics
  if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.gate_source_map)) throw new Error('Invalid readiness metadata JSON for local comparison.')
  return parsed
}

function compareSnapshots(before: AtlasLevel1ReadinessDiagnostics, after: AtlasLevel1ReadinessDiagnostics): SnapshotComparisonResult {
  const beforeMap = new Map<string, AtlasLevel1ReadinessGateSource>(before.gate_source_map.map((g) => [g.gate_id, g]))
  const afterGateIds = new Set(after.gate_source_map.map((g) => g.gate_id))
  const beforeGateIds = new Set(before.gate_source_map.map((g) => g.gate_id))
  const changed_gates = after.gate_source_map
    .map((gate) => {
      const prior = beforeMap.get(gate.gate_id)
      if (!prior) return null
      const changed = prior.current_status !== gate.current_status || prior.evidence_available !== gate.evidence_available || (prior.blocker_reason || '') !== (gate.blocker_reason || '')
      return changed ? { gate_id: gate.gate_id, before_status: prior.current_status, after_status: gate.current_status, before_evidence_available: prior.evidence_available, after_evidence_available: gate.evidence_available, before_blocker_reason: prior.blocker_reason || '', after_blocker_reason: gate.blocker_reason || '' } : null
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)

  const added_gates = [...afterGateIds].filter((gateId) => !beforeGateIds.has(gateId))
  const removed_gates = [...beforeGateIds].filter((gateId) => !afterGateIds.has(gateId))
  const sourceKeys = new Set<string>([...before.gate_source_map.map((g) => g.source || 'unknown'), ...after.gate_source_map.map((g) => g.source || 'unknown')])
  const missingEvidenceCountBySource = (snapshot: AtlasLevel1ReadinessDiagnostics, source: string): number => snapshot.gate_source_map.filter((g) => (g.source || 'unknown') === source && !g.evidence_available).length
  const evidence_summary_delta_by_source = [...sourceKeys].sort().map((source) => {
    const before_missing_evidence_count = missingEvidenceCountBySource(before, source)
    const after_missing_evidence_count = missingEvidenceCountBySource(after, source)
    return { source, before_missing_evidence_count, after_missing_evidence_count, delta_missing_evidence_count: after_missing_evidence_count - before_missing_evidence_count }
  })

  return {
    summary_delta: {
      required_gate_count: (after.required_gate_count ?? 0) - (before.required_gate_count ?? 0),
      missing_evidence_count: (after.missing_evidence_count ?? 0) - (before.missing_evidence_count ?? 0),
      satisfied_gate_count: (after.satisfied_gate_count ?? 0) - (before.satisfied_gate_count ?? 0),
      unsatisfied_gate_count: (after.unsatisfied_gate_count ?? 0) - (before.unsatisfied_gate_count ?? 0)
    },
    changed_gates,
    disabled_status_delta: {
      enabled_changed: before.enabled !== after.enabled,
      level1_execution_changed: before.level1_execution_enabled !== after.level1_execution_enabled,
      callable_execution_endpoint_changed: before.callable_execution_endpoint_enabled !== after.callable_execution_endpoint_enabled,
      vue_execution_controls_changed: before.vue_execution_controls_enabled !== after.vue_execution_controls_enabled,
      runtime_level_changed: before.runtime_level !== after.runtime_level
    },
    evidence_summary_delta_by_source,
    added_gates,
    removed_gates,
    comparison_available: true,
    comparison_error: null
  }
}


async function copyTextToClipboard(text: string): Promise<boolean> {
  if (!text || typeof navigator === 'undefined' || !navigator.clipboard?.writeText) return false
  try { await navigator.clipboard.writeText(text); return true } catch { return false }
}

function diagnosticsJsonText(): string { return diagnostics.value ? JSON.stringify(diagnostics.value, null, 2) : '' }
function visibleGateSummaryText(): string { return (diagnostics.value?.gate_source_map ?? []).map((g) => `${g.gate_id} | ${g.current_status}`).join('\n') }
async function copyReadinessJson(): Promise<void> { await copyTextToClipboard(diagnosticsJsonText()) }
function downloadReadinessJson(): void { const payload = diagnosticsJsonText(); if (!payload || typeof window === 'undefined' || typeof document === 'undefined') return; const blob = new Blob([payload], { type: 'application/json' }); const url = window.URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'atlas-level1-readiness.json'; document.body.appendChild(link); link.click(); document.body.removeChild(link); window.URL.revokeObjectURL(url) }
async function copyVisibleGateSummary(): Promise<void> { await copyTextToClipboard(visibleGateSummaryText()) }

function useSavedBaseline(): void {
  if (!baselineSnapshot.value || !diagnostics.value) return
  comparisonResult.value = compareSnapshots(baselineSnapshot.value, diagnostics.value)
  comparisonStatus.value = 'Compared local saved baseline against current diagnostics.'
}

function usePastedBaseline(): void {
  if (!diagnostics.value) return
  try {
    const parsed = parsePastedBaseline()
    comparisonResult.value = compareSnapshots(parsed, diagnostics.value)
    comparisonStatus.value = 'Compared local pasted baseline against current diagnostics.'
  } catch (error) {
    comparisonResult.value = {
      summary_delta: null,
      disabled_status_delta: { enabled_changed: false, level1_execution_changed: false, callable_execution_endpoint_changed: false, vue_execution_controls_changed: false, runtime_level_changed: false },
      evidence_summary_delta_by_source: [],
      changed_gates: [],
      added_gates: [],
      removed_gates: [],
      comparison_available: false,
      comparison_error: error instanceof Error ? error.message : 'Unable to parse pasted JSON.'
    }
    comparisonStatus.value = 'Local comparison failed due to pasted JSON validation error.'
  }
}

function clearComparison(): void {
  comparisonResult.value = null
  pastedSnapshotJson.value = ''
  comparisonStatus.value = 'Local metadata comparison cleared.'
}



type LocalHistoryEntry = {
  id: string
  saved_at: string
  label: string
  diagnostics: AtlasLevel1ReadinessDiagnostics
}

const HISTORY_STORAGE_KEY = 'atlas.level1.readiness.history'
const HISTORY_MAX_ENTRIES = 5
const historyEntries = ref<LocalHistoryEntry[]>([])
const selectedHistoryId = ref('')
const historyStatus = ref('Local history idle.')
const historyImportJson = ref('')
const historyImportStatus = ref('Local import/export idle.')
const hasHistoryImportJson = computed(() => historyImportJson.value.trim().length > 0)

function storageAvailable(): boolean {
  try { return typeof window !== 'undefined' && !!window.localStorage } catch { return false }
}

function loadHistory(): void {
  if (!storageAvailable()) { historyStatus.value = 'Local browser storage unavailable.'; historyEntries.value = []; return }
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY)
    if (!raw) { historyEntries.value = []; return }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) throw new Error('invalid history payload')
    historyEntries.value = parsed.filter((e) => e && typeof e.id === 'string' && typeof e.saved_at === 'string' && typeof e.label === 'string' && e.diagnostics && Array.isArray(e.diagnostics.gate_source_map)).slice(0, HISTORY_MAX_ENTRIES)
  } catch {
    historyEntries.value = []
    historyStatus.value = 'Local history parse error; history reset in memory.'
  }
}

function persistHistory(entries: LocalHistoryEntry[]): boolean {
  if (!storageAvailable()) { historyStatus.value = 'Local browser storage unavailable.'; return false }
  try {
    window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(entries.slice(0, HISTORY_MAX_ENTRIES)))
    return true
  } catch {
    historyStatus.value = 'Unable to save local history (storage quota or storage error).';
    return false
  }
}

function saveCurrentToHistory(): void {
  if (!diagnostics.value) return
  const now = new Date().toISOString()
  const entry: LocalHistoryEntry = { id: `${Date.now()}`, saved_at: now, label: `Snapshot ${new Date().toLocaleString()}`, diagnostics: JSON.parse(JSON.stringify(diagnostics.value)) }
  const updated = [entry, ...historyEntries.value].slice(0, HISTORY_MAX_ENTRIES)
  if (persistHistory(updated)) { historyEntries.value = updated; historyStatus.value = 'Saved current diagnostics to local history.'; selectedHistoryId.value = entry.id }
}

function useHistoryBaseline(): void {
  if (!diagnostics.value || !selectedHistoryId.value) return
  const found = historyEntries.value.find((e) => e.id === selectedHistoryId.value)
  if (!found) { historyStatus.value = 'Selected local history snapshot not found.'; return }
  comparisonResult.value = compareSnapshots(found.diagnostics, diagnostics.value)
  comparisonStatus.value = 'Compared selected local history baseline against current diagnostics.'
}

function deleteHistoryEntry(id: string): void {
  const updated = historyEntries.value.filter((e) => e.id !== id)
  if (persistHistory(updated)) { historyEntries.value = updated; if (selectedHistoryId.value === id) selectedHistoryId.value=''; historyStatus.value = 'Deleted one local history snapshot.' }
}



function historyJsonText(): string { return JSON.stringify(historyEntries.value, null, 2) }
async function copyHistoryJson(): Promise<void> {
  const ok = await copyTextToClipboard(historyJsonText())
  historyImportStatus.value = ok ? 'Copied local history JSON to clipboard.' : 'Clipboard unavailable for local history copy.'
}
function downloadHistoryJson(): void {
  const payload = historyJsonText()
  if (!payload || typeof window === 'undefined' || typeof document === 'undefined') return
  const blob = new Blob([payload], { type: 'application/json' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = 'atlas-level1-readiness-history.json'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
  historyImportStatus.value = 'Exported local history JSON file.'
}
function clearHistoryImportText(): void { historyImportJson.value = ''; historyImportStatus.value = 'Cleared local history import text.' }

function isValidHistoryEntry(value: unknown): value is LocalHistoryEntry {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  const diagnostics = item.diagnostics as Record<string, unknown> | undefined
  return typeof item.id === 'string' && typeof item.saved_at === 'string' && typeof item.label === 'string' && !!diagnostics && typeof diagnostics === 'object' && Array.isArray(diagnostics.gate_source_map)
}

function parseHistoryImportPayload(raw: string): LocalHistoryEntry[] {
  const parsed = JSON.parse(raw) as unknown
  const entries: unknown[] | null = Array.isArray(parsed) ? parsed : (parsed && typeof parsed === 'object' && Array.isArray((parsed as Record<string, unknown>).history) ? ((parsed as Record<string, unknown>).history as unknown[]) : null)
  if (!entries) throw new Error('Import JSON must be an array or an object with a history array.')
  return entries.filter(isValidHistoryEntry).map((entry) => JSON.parse(JSON.stringify(entry)) as LocalHistoryEntry).slice(0, HISTORY_MAX_ENTRIES)
}

function mergeHistoryEntries(imported: LocalHistoryEntry[]): LocalHistoryEntry[] {
  const byId = new Map<string, LocalHistoryEntry>()
  ;[...imported, ...historyEntries.value].forEach((entry) => { if (!byId.has(entry.id)) byId.set(entry.id, entry) })
  return [...byId.values()].sort((a, b) => b.saved_at.localeCompare(a.saved_at)).slice(0, HISTORY_MAX_ENTRIES)
}

function importHistoryMerge(): void {
  try {
    const imported = parseHistoryImportPayload(historyImportJson.value)
    const merged = mergeHistoryEntries(imported)
    if (persistHistory(merged)) { historyEntries.value = merged; historyImportStatus.value = `Merged ${imported.length} valid local history entries.` }
  } catch (error) { historyImportStatus.value = error instanceof Error ? error.message : 'Failed to merge local history import.' }
}

function importHistoryReplace(): void {
  try {
    const imported = parseHistoryImportPayload(historyImportJson.value)
    if (persistHistory(imported)) { historyEntries.value = imported; selectedHistoryId.value = ''; historyImportStatus.value = `Replaced local history with ${imported.length} valid entries.` }
  } catch (error) { historyImportStatus.value = error instanceof Error ? error.message : 'Failed to replace local history import.' }
}

function loadHistoryImportFile(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    historyImportJson.value = typeof reader.result === 'string' ? reader.result : ''
    historyImportStatus.value = 'Loaded local history JSON file into import text area.'
  }
  reader.onerror = () => { historyImportStatus.value = 'Unable to read local history file.' }
  reader.readAsText(file)
}

function clearHistory(): void {
  if (!storageAvailable()) { historyStatus.value = 'Local browser storage unavailable.'; return }
  try { window.localStorage.removeItem(HISTORY_STORAGE_KEY); historyEntries.value=[]; selectedHistoryId.value=''; historyStatus.value='Cleared local history.' }
  catch { historyStatus.value='Unable to clear local history due to storage error.' }
}

onMounted(async () => { loadHistory(); diagnostics.value = await fetchLevel1ReadinessDiagnostics() })
</script>

<style scoped>
.gate-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.gate-table th, .gate-table td { border: 1px solid #e2e8f0; padding: 4px; text-align: left; vertical-align: top; }
.filter-btn { border: 1px solid #cbd5e1; background: #f8fafc; border-radius: 6px; padding: 4px 8px; font-size: 12px; cursor: pointer; }
.advisory-note { font-size: 12px; color: #334155; }
.metadata-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0; }
.metadata-status { font-size: 12px; color: #334155; }
.metadata-input { width: 100%; margin-bottom: 8px; }
.comparison-box { margin-top: 8px; border: 1px solid #e2e8f0; padding: 8px; }
</style>
