<template>
  <StatusCard title="Safety Summary">
    <ul>
      <li>Runtime remains {{ snapshot.safety.runtimeLevel }}.</li>
      <li>Automatic execution is disabled.</li>
      <li>EXECUTE ONE ACTION and dry-run-first behavior are preserved in classic flow.</li>
      <li>Backend workflow state remains authoritative.</li>
    </ul>
  </StatusCard>
</template>

<script setup lang="ts">
import StatusCard from './StatusCard.vue'
import type { AtlasWorkflowSnapshot } from '../api/atlasClient'

defineProps<{ snapshot: AtlasWorkflowSnapshot }>()
</script>
