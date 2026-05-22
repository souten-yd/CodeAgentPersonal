<template>
  <StatusCard title="Workflow (Read-only)">
    <p><b>Goal:</b> {{ snapshot.goal || 'N/A' }}</p>
    <p><b>Project path:</b> {{ snapshot.projectPath || 'N/A' }}</p>
    <p><b>Phase:</b> {{ snapshot.phase || 'unknown' }}</p>
    <p><b>Status:</b> {{ snapshot.status || 'unknown' }}</p>
    <p><b>Primary CTA:</b> {{ snapshot.primaryCtaLabel || 'Read-only preview' }} ({{ snapshot.primaryCtaState || 'read_only' }})</p>
    <p><b>Backend authority:</b> {{ snapshot.backendAuthorityNote }}</p>
    <button disabled aria-disabled="true">Read-only preview (not wired)</button>
  </StatusCard>

  <StatusCard title="Available Actions (metadata only)">
    <p><b>Metadata-only badge:</b> Every action is read-only and disabled in Vue Next.</p>
    <ul>
      <li v-for="action in snapshot.availableActions" :key="action.id">
        <b>{{ action.label }}</b> [{{ action.kind || 'read_only' }}] - {{ action.reason }}
      </li>
      <li v-if="snapshot.availableActions.length === 0">No available actions provided by current read-only payload.</li>
    </ul>
  </StatusCard>
</template>

<script setup lang="ts">
import StatusCard from './StatusCard.vue'
import type { AtlasWorkflowSnapshot } from '../api/atlasClient'

defineProps<{ snapshot: AtlasWorkflowSnapshot }>()
</script>
