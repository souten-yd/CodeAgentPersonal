<template>
  <StatusCard title="Level-1 Readiness Diagnostics (read-only)">
    <p><b>enabled:</b> {{ diagnostics?.enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>runtime_level:</b> {{ diagnostics?.runtime_level || 'unknown' }}</p>
    <p><b>level1_execution_enabled:</b> {{ diagnostics?.level1_execution_enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>callable_execution_endpoint_enabled:</b> {{ diagnostics?.callable_execution_endpoint_enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>vue_execution_controls_enabled:</b> {{ diagnostics?.vue_execution_controls_enabled === false ? 'false' : 'unknown' }}</p>
    <p><b>advisory_only:</b> {{ diagnostics?.advisory_only ? 'true' : 'false' }}</p>
    <p><b>mutation_performed:</b> {{ diagnostics?.mutation_performed === false ? 'false' : 'unknown' }}</p>
    <p><b>execution_performed:</b> {{ diagnostics?.execution_performed === false ? 'false' : 'unknown' }}</p>
    <p><b>required_gate_count:</b> {{ diagnostics?.required_gate_count ?? 0 }}</p>
    <p><b>missing_evidence_count:</b> {{ diagnostics?.missing_evidence_count ?? 0 }}</p>
    <p><b>satisfied_gate_count:</b> {{ diagnostics?.satisfied_gate_count ?? 0 }}</p>
    <p><b>unsatisfied_gate_count:</b> {{ diagnostics?.unsatisfied_gate_count ?? 0 }}</p>

    <p class="advisory-note"><b>Display note:</b> filters and grouping below are advisory display-only metadata views; backend workflow_state remains authoritative. Vue does not compute execution eligibility and does not decide readiness.</p>

    <div class="filters" role="group" aria-label="Readiness display filters">
      <span class="filter-label">Display filter:</span>
      <button v-for="option in filterOptions" :key="option.key" type="button" class="filter-btn" :class="{ active: activeFilter === option.key }" @click="activeFilter = option.key">
        {{ option.label }}
      </button>
    </div>

    <p><b>visible_gate_count:</b> {{ filteredGateSourceMap.length }}</p>

    <div class="summary-grid" v-if="gateSourceMap.length">
      <div>
        <h4>Summary by owner</h4>
        <ul><li v-for="entry in ownerSummary" :key="`owner-${entry.key}`">{{ entry.key }}: {{ entry.count }}</li></ul>
      </div>
      <div>
        <h4>Summary by source</h4>
        <ul><li v-for="entry in sourceSummary" :key="`source-${entry.key}`">{{ entry.key }}: {{ entry.count }}</li></ul>
      </div>
      <div>
        <h4>Summary by current_status</h4>
        <ul><li v-for="entry in statusSummary" :key="`status-${entry.key}`">{{ entry.key }}: {{ entry.count }}</li></ul>
      </div>
    </div>

    <table v-if="filteredGateSourceMap.length" class="gate-table">
      <thead>
        <tr>
          <th>gate_id</th><th>label</th><th>owner</th><th>source</th><th>evidence_required</th><th>evidence_available</th><th>current_status</th><th>blocker_reason</th><th>test_requirement</th><th>mutable</th><th>advisory_only</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="gate in filteredGateSourceMap" :key="gate.gate_id">
          <td>{{ gate.gate_id }}</td><td>{{ gate.label }}</td><td>{{ gate.owner }}</td><td>{{ gate.source }}</td><td>{{ gate.evidence_required }}</td><td>{{ gate.evidence_available }}</td><td>{{ gate.current_status }}</td><td>{{ gate.blocker_reason || '-' }}</td><td>{{ gate.test_requirement || '-' }}</td><td>{{ gate.mutable }}</td><td>{{ gate.advisory_only }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else>No gate-source mapping available for selected display filter.</p>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import StatusCard from './StatusCard.vue'
import { fetchLevel1ReadinessDiagnostics, type AtlasLevel1ReadinessDiagnostics, type AtlasLevel1ReadinessGateSource } from '../api/atlasClient'

type GateFilter = 'all' | 'missing_evidence' | 'backend_owned' | 'frontend_owned'

const diagnostics = ref<AtlasLevel1ReadinessDiagnostics | null>(null)
const gateSourceMap = computed(() => Array.isArray(diagnostics.value?.gate_source_map) ? diagnostics.value?.gate_source_map : [])
const activeFilter = ref<GateFilter>('all')

const filterOptions: Array<{ key: GateFilter, label: string }> = [
  { key: 'all', label: 'Show all gates' },
  { key: 'missing_evidence', label: 'Missing evidence only' },
  { key: 'backend_owned', label: 'Backend-owned only' },
  { key: 'frontend_owned', label: 'Frontend-owned only' }
]

function summarizeBy(items: AtlasLevel1ReadinessGateSource[], key: 'owner' | 'source' | 'current_status'): Array<{ key: string, count: number }> {
  const totals = new Map<string, number>()
  for (const item of items) totals.set(item[key], (totals.get(item[key]) ?? 0) + 1)
  return [...totals.entries()].map(([groupKey, count]) => ({ key: groupKey, count })).sort((a, b) => a.key.localeCompare(b.key))
}

const filteredGateSourceMap = computed(() => {
  const gates = gateSourceMap.value
  if (activeFilter.value === 'missing_evidence') return gates.filter((gate) => !gate.evidence_available)
  if (activeFilter.value === 'backend_owned') return gates.filter((gate) => gate.owner === 'backend')
  if (activeFilter.value === 'frontend_owned') return gates.filter((gate) => gate.owner === 'frontend')
  return gates
})

const ownerSummary = computed(() => summarizeBy(filteredGateSourceMap.value, 'owner'))
const sourceSummary = computed(() => summarizeBy(filteredGateSourceMap.value, 'source'))
const statusSummary = computed(() => summarizeBy(filteredGateSourceMap.value, 'current_status'))

onMounted(async () => {
  diagnostics.value = await fetchLevel1ReadinessDiagnostics()
})
</script>

<style scoped>
.gate-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.gate-table th, .gate-table td { border: 1px solid #e2e8f0; padding: 4px; text-align: left; vertical-align: top; }
.filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 8px 0; }
.filter-label { font-weight: 600; }
.filter-btn { border: 1px solid #cbd5e1; background: #f8fafc; border-radius: 6px; padding: 4px 8px; font-size: 12px; cursor: pointer; }
.filter-btn.active { background: #e2e8f0; border-color: #94a3b8; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 12px; margin-bottom: 8px; }
.summary-grid h4 { margin: 4px 0; font-size: 13px; }
.summary-grid ul { margin: 0; padding-left: 18px; }
.advisory-note { font-size: 12px; color: #334155; }
</style>
