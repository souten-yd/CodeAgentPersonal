<template>
  <StatusCard title="Artifacts (Read-only)">
    <p><b>Readiness level:</b> {{ snapshot.readinessLevel || 'unknown' }}</p>
    <ul>
      <li v-for="(v,k) in snapshot.artifacts" :key="k">{{ k }}: {{ v ? 'available' : 'missing' }}</li>
    </ul>
  </StatusCard>
</template>

<script setup lang="ts">
import StatusCard from './StatusCard.vue'
import type { AtlasWorkflowSnapshot } from '../api/atlasClient'

defineProps<{ snapshot: AtlasWorkflowSnapshot }>()
</script>
