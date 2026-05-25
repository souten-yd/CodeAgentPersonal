<template>
  <aside class="progress-rail" aria-label="Atlas progress">
    <header>
      <p class="eyebrow">Progress</p>
      <h2>Atlas run path</h2>
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

const steps = computed(() => {
  const hasBackendSnapshot = props.snapshot.diagnostics.source === 'safe_get_adapter'
  const hasRequirement = hasBackendSnapshot && Boolean(props.snapshot.workflowMetadata.latestRequirementId || props.snapshot.goal)
  const hasPlanPool = hasBackendSnapshot && props.snapshot.workflowMetadata.planPoolAvailable
  const hasPlan = hasBackendSnapshot && props.snapshot.workflowMetadata.activePlanAvailable
  const hasDryRun = hasBackendSnapshot && props.snapshot.artifacts.dryRun === true
  return [
    {
      id: 'requirement',
      label: 'Requirement',
      detail: hasRequirement ? 'Requirement metadata available' : 'Start Atlas captures the requirement',
      state: hasRequirement ? 'done' : 'active'
    },
    {
      id: 'plan',
      label: 'Plan',
      detail: hasPlanPool || hasPlan ? 'Plan metadata is available for review' : 'Plan generation waits for Start Atlas',
      state: hasPlanPool || hasPlan ? 'done' : 'waiting'
    },
    {
      id: 'review',
      label: 'Review',
      detail: hasPlan ? 'Review the backend-owned plan' : 'Review begins after plan metadata exists',
      state: hasPlan ? 'active' : 'waiting'
    },
    {
      id: 'preview',
      label: 'Execute Preview',
      detail: hasDryRun ? 'Dry-run metadata available' : 'Dry-run remains gated',
      state: hasDryRun ? 'done' : 'waiting'
    },
    {
      id: 'execute',
      label: 'Guarded Execute',
      detail: 'Requires explicit approval and backend gate evidence',
      state: 'locked'
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
@media (max-width: 860px) {
  .progress-rail {
    position: static;
  }
}
</style>
