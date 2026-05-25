<template>
  <StatusCard title="Guarded Execution Review (Display-only)">
    <ul>
      <li><b>Checkpoint:</b> {{ review.checkpoint }}</li>
      <li><b>Endpoint contract:</b> {{ review.endpointContractStatus }}</li>
      <li><b>Backend authoritative:</b> yes</li>
      <li><b>Vue authoritative:</b> no</li>
      <li><b>Callable execution route:</b> disabled</li>
      <li><b>Runtime transition required:</b> yes</li>
    </ul>

    <p><b>Review evidence:</b></p>
    <ul class="compact-list">
      <li v-for="item in review.reviewItems" :key="item.label">
        {{ item.label }}: {{ item.ready ? 'ready' : 'missing' }} ({{ item.source }})
      </li>
    </ul>

    <p v-if="review.blockedReasons.length"><b>Blocked reasons:</b> {{ review.blockedReasons.join(' | ') }}</p>
    <p><b>Actions unavailable in Vue:</b> approve, start dry-run, execute, apply, verify, rollback/restore, retry, and continue.</p>
  </StatusCard>
</template>

<script setup lang="ts">
import type { AtlasGuardedExecutionReviewState } from '../api/atlasClient'
import StatusCard from './StatusCard.vue'

defineProps<{ review: AtlasGuardedExecutionReviewState }>()
</script>

<style scoped>
.compact-list { margin: 4px 0 8px 16px; }
</style>
