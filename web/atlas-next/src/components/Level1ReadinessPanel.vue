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
  changed_gates: Array<{ gate_id: string, before_status: string, after_status: string, before_evidence_available: boolean, after_evidence_available: boolean, before_blocker_reason: string, after_blocker_reason: string }>
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
  const changed_gates = after.gate_source_map
    .map((gate) => {
      const prior = beforeMap.get(gate.gate_id)
      if (!prior) return null
      const changed = prior.current_status !== gate.current_status || prior.evidence_available !== gate.evidence_available || (prior.blocker_reason || '') !== (gate.blocker_reason || '')
      return changed ? { gate_id: gate.gate_id, before_status: prior.current_status, after_status: gate.current_status, before_evidence_available: prior.evidence_available, after_evidence_available: gate.evidence_available, before_blocker_reason: prior.blocker_reason || '', after_blocker_reason: gate.blocker_reason || '' } : null
    })
    .filter((item): item is NonNullable<typeof item> => item !== null)

  return {
    summary_delta: {
      required_gate_count: (after.required_gate_count ?? 0) - (before.required_gate_count ?? 0),
      missing_evidence_count: (after.missing_evidence_count ?? 0) - (before.missing_evidence_count ?? 0),
      satisfied_gate_count: (after.satisfied_gate_count ?? 0) - (before.satisfied_gate_count ?? 0),
      unsatisfied_gate_count: (after.unsatisfied_gate_count ?? 0) - (before.unsatisfied_gate_count ?? 0)
    },
    changed_gates,
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
    comparisonResult.value = { summary_delta: null, changed_gates: [], comparison_available: false, comparison_error: error instanceof Error ? error.message : 'Unable to parse pasted JSON.' }
    comparisonStatus.value = 'Local comparison failed due to pasted JSON validation error.'
  }
}

function clearComparison(): void {
  comparisonResult.value = null
  pastedSnapshotJson.value = ''
  comparisonStatus.value = 'Local metadata comparison cleared.'
}

onMounted(async () => { diagnostics.value = await fetchLevel1ReadinessDiagnostics() })
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
