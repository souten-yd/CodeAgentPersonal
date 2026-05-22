<template>
  <StatusCard title="Diagnostics Notice">
    <ul>
      <li>This is the parallel Vue Atlas Next read-only shell.</li>
      <li>Existing ui.html remains default (Vue is not default).</li>
      <li>Static mount deferred while dist/static artifact strategy is not locked.</li>
      <li>No mutation endpoints are called from Vue; execution controls are intentionally omitted.</li>
      <li>Source: {{ snapshot.diagnostics.source }}; routeMounted={{ snapshot.diagnostics.routeMounted }}; staticMountDeferred={{ snapshot.diagnostics.staticMountDeferred }}.</li>
      <li>Backend contract ready: {{ snapshot.diagnostics.backendContractReady ? 'yes' : 'no' }}.</li>
      <li v-for="(warning, idx) in snapshot.diagnostics.warnings" :key="idx">Warning: {{ warning }}</li>
    </ul>
  </StatusCard>
</template>

<script setup lang="ts">
import StatusCard from './StatusCard.vue'
import type { AtlasWorkflowSnapshot } from '../api/atlasClient'

defineProps<{ snapshot: AtlasWorkflowSnapshot }>()
</script>
