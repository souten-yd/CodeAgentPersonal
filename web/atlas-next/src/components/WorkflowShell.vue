<template>
  <StatusCard title="Current Atlas State">
    <dl class="workflow-grid">
      <div>
        <dt>Goal</dt>
        <dd>{{ snapshot.goal || 'Not started' }}</dd>
      </div>
      <div>
        <dt>Phase</dt>
        <dd>{{ snapshot.phase || snapshot.workflowMetadata.currentPhase || 'idle' }}</dd>
      </div>
      <div>
        <dt>Status</dt>
        <dd>{{ snapshot.status || snapshot.workflowMetadata.latestStatus || 'waiting for Start Atlas' }}</dd>
      </div>
      <div>
        <dt>Project</dt>
        <dd>{{ snapshot.projectPath || 'Default workspace' }}</dd>
      </div>
    </dl>
    <p class="authority">{{ snapshot.backendAuthorityNote }}</p>
  </StatusCard>

  <StatusCard title="Backend Action Metadata">
    <p class="metadata-note">These are backend-reported actions for review only. Start Atlas is the single Vue entry point on this screen.</p>
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

<style scoped>
.workflow-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin: 0;
}
.workflow-grid div {
  min-width: 0;
  border-left: 3px solid #0f766e;
  padding: 8px 10px;
  background: #ffffff;
}
dt {
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}
dd {
  margin: 4px 0 0;
  overflow-wrap: anywhere;
}
.authority,
.metadata-note {
  color: #475569;
  font-size: 13px;
}
</style>
