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

    <table v-if="gateSourceMap.length" class="gate-table">
      <thead>
        <tr>
          <th>gate_id</th><th>label</th><th>owner</th><th>source</th><th>evidence_required</th><th>evidence_available</th><th>current_status</th><th>blocker_reason</th><th>test_requirement</th><th>mutable</th><th>advisory_only</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="gate in gateSourceMap" :key="gate.gate_id">
          <td>{{ gate.gate_id }}</td><td>{{ gate.label }}</td><td>{{ gate.owner }}</td><td>{{ gate.source }}</td><td>{{ gate.evidence_required }}</td><td>{{ gate.evidence_available }}</td><td>{{ gate.current_status }}</td><td>{{ gate.blocker_reason || '-' }}</td><td>{{ gate.test_requirement || '-' }}</td><td>{{ gate.mutable }}</td><td>{{ gate.advisory_only }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else>No gate-source mapping available.</p>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import StatusCard from './StatusCard.vue'
import { fetchLevel1ReadinessDiagnostics, type AtlasLevel1ReadinessDiagnostics } from '../api/atlasClient'

const diagnostics = ref<AtlasLevel1ReadinessDiagnostics | null>(null)
const gateSourceMap = computed(() => Array.isArray(diagnostics.value?.gate_source_map) ? diagnostics.value?.gate_source_map : [])

onMounted(async () => {
  diagnostics.value = await fetchLevel1ReadinessDiagnostics()
})
</script>

<style scoped>
.gate-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.gate-table th, .gate-table td { border: 1px solid #e2e8f0; padding: 4px; text-align: left; vertical-align: top; }
</style>
