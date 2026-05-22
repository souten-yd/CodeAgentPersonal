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
  <StatusCard title="Workflow State Metadata (read-only)">
    <p><b>Current phase:</b> {{ snapshot.workflowMetadata.currentPhase || 'unknown' }}</p>
    <p><b>Latest status:</b> {{ snapshot.workflowMetadata.latestStatus || 'unknown' }}</p>
    <p><b>Continuation:</b> {{ snapshot.workflowMetadata.continuationState || 'unknown' }} | <b>Recovery:</b> {{ snapshot.workflowMetadata.recoveryState || 'unknown' }}</p>
    <p><b>Plan pool available:</b> {{ snapshot.workflowMetadata.planPoolAvailable ? 'yes' : 'no' }} | <b>Active plan:</b> {{ snapshot.workflowMetadata.activePlanAvailable ? 'yes' : 'no' }}</p>
    <p><b>Last report:</b> {{ snapshot.workflowMetadata.lastReportAvailable ? 'available' : 'unavailable' }} | <b>Freshness:</b> {{ snapshot.workflowMetadata.dataFreshness }}</p>
  </StatusCard>
</template>

<script setup lang="ts">
import StatusCard from './StatusCard.vue'
import type { AtlasWorkflowSnapshot } from '../api/atlasClient'

defineProps<{ snapshot: AtlasWorkflowSnapshot }>()
</script>
