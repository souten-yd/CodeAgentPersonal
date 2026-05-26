<template>
  <aside class="progress-rail" aria-label="Atlas progress">
    <header>
      <p class="eyebrow">Progress</p>
      <h2>Atlas workflow path</h2>
    </header>

    <ol>
      <li v-for="step in steps" :key="step.id" :class="step.state">
        <span class="dot" aria-hidden="true"></span>
        <div>
          <p class="step-title">{{ step.label }}</p>
          <p class="step-detail">{{ step.detail }}</p>
        </div>
      </li>
    </ol>

    <section class="rail-panel readiness-panel">
      <h3>Guarded readiness</h3>
      <p><b>Gates:</b> {{ guardedReadyCount }}/{{ guardedTotalCount }} ready</p>
      <p><b>Endpoint:</b> {{ guardedReview.endpointContractStatus }}</p>
      <p><b>Missing:</b> {{ guardedMissingSummary }}</p>
      <p v-if="guardedReview.blockedReasons.length"><b>Blocked:</b> {{ guardedBlockedSummary }}</p>
    </section>

    <section class="rail-panel">
      <h3>Current state</h3>
      <p><b>Phase:</b> {{ snapshot.phase || snapshot.workflowMetadata.currentPhase || 'idle' }}</p>
      <p><b>Status:</b> {{ snapshot.status || snapshot.workflowMetadata.latestStatus || 'waiting for Start Atlas' }}</p>
      <p><b>Runtime:</b> {{ snapshot.safety.runtimeLevel }}</p>
    </section>

    <section class="rail-panel">
      <h3>Safety locks</h3>
      <ul>
        <li>Backend authoritative</li>
        <li>Vue execution controls disabled</li>
        <li>Approval/apply/rollback remain manual</li>
      </ul>
    </section>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AtlasWorkflowSnapshot } from '../api/atlasClient'

const props = defineProps<{ snapshot: AtlasWorkflowSnapshot }>()

const guardedReview = computed(() => props.snapshot.guardedExecutionReview)
const guardedTotalCount = computed(() => guardedReview.value.reviewItems.length)
const guardedReadyCount = computed(() => guardedReview.value.reviewItems.filter((item) => item.ready).length)
const guardedMissingSummary = computed(() => {
  const missing = guardedReview.value.reviewItems.filter((item) => !item.ready).map((item) => item.label)
  return missing.length ? missing.slice(0, 3).join(' | ') : 'No missing gate metadata reported.'
})
const guardedBlockedSummary = computed(() => guardedReview.value.blockedReasons.slice(0, 2).join(' | '))

const steps = computed(() => {
  const hasBackendSnapshot = props.snapshot.diagnostics.source === 'safe_get_adapter'
  const hasRequirement = hasBackendSnapshot && Boolean(props.snapshot.workflowMetadata.latestRequirementId || props.snapshot.goal)
  const hasPlanPool = hasBackendSnapshot && props.snapshot.workflowMetadata.planPoolAvailable
  const hasPlan = hasBackendSnapshot && props.snapshot.workflowMetadata.activePlanAvailable
  const hasDryRun = hasBackendSnapshot && props.snapshot.artifacts.dryRun === true
  const review = guardedReview.value
  const hasApprovalReview = hasPlan && review.reviewItems.length > 0
  return [
    {
      id: 'start-atlas',
      label: 'Start Atlas',
      detail: hasRequirement ? 'Requirement metadata available' : 'Requirement input starts the backend-owned planning flow',
      state: hasRequirement ? 'done' : 'active'
    },
    {
      id: 'plan-review',
      label: 'Plan Review',
      detail: hasPlanPool || hasPlan ? 'Plan metadata is available for review' : 'Plan review waits for Start Atlas',
      state: hasPlanPool || hasPlan ? 'done' : 'waiting'
    },
    {
      id: 'approval-review',
      label: 'Approval Review',
      detail: hasApprovalReview ? 'Approval context is visible for human review' : 'Approval remains review-only until backend metadata exists',
      state: hasApprovalReview ? 'active' : 'waiting'
    },
    {
      id: 'execute-preview',
      label: 'Execute Preview',
      detail: hasDryRun ? 'Dry-run metadata available' : 'Dry-run and execution preview remain gated',
      state: hasDryRun ? 'done' : 'waiting'
    },
    {
      id: 'patch-review',
      label: 'Patch Review',
      detail: 'Patch candidates remain review-only; Vue does not apply changes',
      state: 'locked'
    },
    {
      id: 'guarded-execute',
      label: 'Guarded Execute',
      detail: review.executionEnabled ? 'Backend reports guarded execution ready' : 'Requires explicit approval, dry-run evidence, and backend gate checks',
      state: review.executionEnabled ? 'active' : 'locked'
    }
  ]
})
</script>

<style scoped>
.progress-rail {
  position: sticky;
  top: 16px;
  align-self: start;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  padding: 16px;
  background: #f8fbff;
}
.eyebrow {
  margin: 0 0 4px;
  color: #0f766e;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}
h2,
h3 {
  margin: 0;
}
ol {
  display: grid;
  gap: 12px;
  margin: 16px 0;
  padding: 0;
  list-style: none;
}
li {
  display: grid;
  grid-template-columns: 14px 1fr;
  gap: 10px;
}
.dot {
  width: 10px;
  height: 10px;
  margin-top: 5px;
  border: 2px solid #94a3b8;
  border-radius: 999px;
  background: #ffffff;
}
.done .dot {
  border-color: #0f766e;
  background: #0f766e;
}
.active .dot {
  border-color: #2563eb;
  background: #bfdbfe;
}
.locked .dot {
  border-color: #64748b;
  background: #e2e8f0;
}
.step-title {
  margin: 0;
  font-weight: 800;
}
.step-detail {
  margin: 2px 0 0;
  color: #475569;
  font-size: 13px;
}
.rail-panel {
  border-top: 1px solid #d8e0ea;
  padding-top: 12px;
  margin-top: 12px;
}
.rail-panel p,
.rail-panel ul {
  margin: 8px 0 0;
}
.rail-panel ul {
  padding-left: 18px;
}
.readiness-panel {
  background: #eef6f2;
  border: 1px solid #c7ddd3;
  border-radius: 8px;
  padding: 12px;
}
.readiness-panel h3 {
  color: #0f5132;
}
@media (max-width: 860px) {
  .progress-rail {
    position: static;
  }
}
</style>