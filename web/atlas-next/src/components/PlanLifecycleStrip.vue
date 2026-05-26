<template>
  <StatusCard title="Plan Lifecycle">
    <ol class="lifecycle-strip" aria-label="Read-only Atlas plan lifecycle">
      <li v-for="item in lifecycleItems" :key="item.id" :class="item.state">
        <p class="item-label">{{ item.label }}</p>
        <p class="item-detail">{{ item.detail }}</p>
      </li>
    </ol>
    <p class="lifecycle-note">Lifecycle status is backend-owned and read-only. Vue does not approve, dry-run, execute, apply, verify, rollback, retry, or continue actions.</p>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatusCard from './StatusCard.vue'
import type { AtlasWorkflowSnapshot } from '../api/atlasClient'

const props = defineProps<{ snapshot: AtlasWorkflowSnapshot }>()

const lifecycleItems = computed(() => {
  const hasBackendSnapshot = props.snapshot.diagnostics.source === 'safe_get_adapter'
  const hasRequirement = hasBackendSnapshot && Boolean(props.snapshot.workflowMetadata.latestRequirementId || props.snapshot.goal)
  const hasPlanPool = hasBackendSnapshot && props.snapshot.workflowMetadata.planPoolAvailable
  const hasPlan = hasBackendSnapshot && props.snapshot.workflowMetadata.activePlanAvailable
  const hasReviewItems = hasPlan && props.snapshot.guardedExecutionReview.reviewItems.length > 0
  const hasDryRun = hasBackendSnapshot && props.snapshot.artifacts.dryRun === true
  const hasPatchPreview = props.snapshot.patchTransaction.available || props.snapshot.patchTransaction.candidateCount > 0
  return [
    {
      id: 'start-atlas',
      label: 'Start Atlas',
      detail: hasRequirement ? 'Requirement metadata exists' : 'Waiting for requirement input',
      state: hasRequirement ? 'done' : 'active'
    },
    {
      id: 'plan-review',
      label: 'Plan Review',
      detail: hasPlanPool || hasPlan ? 'Plan metadata ready for review' : 'Waiting for backend plan metadata',
      state: hasPlanPool || hasPlan ? 'done' : 'waiting'
    },
    {
      id: 'approval-review',
      label: 'Approval Review',
      detail: hasReviewItems ? 'Backend gate context visible' : 'Human approval remains pending metadata',
      state: hasReviewItems ? 'active' : 'waiting'
    },
    {
      id: 'execute-preview',
      label: 'Execute Preview',
      detail: hasDryRun ? 'Dry-run evidence visible' : 'Dry-run evidence required before execution',
      state: hasDryRun ? 'done' : 'waiting'
    },
    {
      id: 'patch-review',
      label: 'Patch Review',
      detail: hasPatchPreview ? 'Patch preview metadata visible' : 'Patch review remains metadata-only',
      state: hasPatchPreview ? 'active' : 'locked'
    }
  ]
})
</script>

<style scoped>
.lifecycle-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.lifecycle-strip li {
  min-width: 0;
  border-top: 4px solid #94a3b8;
  border-radius: 6px;
  padding: 10px;
  background: #ffffff;
}
.lifecycle-strip li.done {
  border-color: #0f766e;
}
.lifecycle-strip li.active {
  border-color: #2563eb;
}
.lifecycle-strip li.locked {
  border-color: #64748b;
  background: #f8fafc;
}
.item-label {
  margin: 0;
  font-weight: 800;
}
.item-detail,
.lifecycle-note {
  color: #475569;
  font-size: 13px;
}
.item-detail {
  margin: 4px 0 0;
}
.lifecycle-note {
  margin: 10px 0 0;
}
@media (max-width: 860px) {
  .lifecycle-strip {
    grid-template-columns: 1fr;
  }
}
</style>
