<template>
  <StatusCard title="FastUI Shell MVP">
    <div class="fastui-shell" aria-label="Atlas FastUI shell MVP">
      <section class="conversation-panel" aria-label="Conversation first Atlas shell">
        <div class="message-row operator">
          <p class="speaker">Operator</p>
          <p>{{ operatorPrompt }}</p>
        </div>
        <div class="message-row atlas">
          <p class="speaker">Atlas</p>
          <p>{{ atlasReply }}</p>
        </div>
      </section>

      <section class="work-target" aria-label="Work target mode">
        <div>
          <p class="section-label">Work target</p>
          <p class="section-copy">{{ selectedTarget.description }}</p>
        </div>
        <div class="segmented-control" role="group" aria-label="Select work target mode">
          <button
            v-for="target in workTargets"
            :key="target.id"
            type="button"
            :class="{ selected: target.id === workTargetMode }"
            @click="workTargetMode = target.id"
          >
            {{ target.label }}
          </button>
        </div>
      </section>

      <div class="summary-grid" aria-label="Atlas summary">
        <section class="summary-panel">
          <p class="section-label">Current phase</p>
          <p>{{ currentPhase }}</p>
        </section>
        <section class="summary-panel">
          <p class="section-label">Next action</p>
          <p>{{ nextAction }}</p>
        </section>
        <section class="summary-panel safety">
          <p class="section-label">Safety profile</p>
          <p>{{ safetyProfile }}</p>
        </section>
      </div>

      <div class="summary-grid" aria-label="Atlas practical loop summary">
        <section class="summary-panel loop">
          <p class="section-label">Loop</p>
          <p>{{ loopSummary }}</p>
        </section>
        <section class="summary-panel">
          <p class="section-label">Changed files</p>
          <p>{{ changedFilesSummary }}</p>
        </section>
        <section class="summary-panel">
          <p class="section-label">Verification</p>
          <p>{{ verificationSummary }}</p>
        </section>
        <section class="summary-panel">
          <p class="section-label">Recovery</p>
          <p>{{ recoverySummary }}</p>
        </section>
        <section class="summary-panel">
          <p class="section-label">Draft PR</p>
          <p>{{ draftPrSummary }}</p>
        </section>
      </div>

      <section class="artifact-details" aria-label="Loop artifact details">
        <div>
          <p class="section-label">Loop artifact</p>
          <p class="section-copy">Read-only identifiers from the latest guarded operator loop artifact.</p>
        </div>
        <dl class="artifact-grid">
          <div v-for="detail in loopArtifactDetails" :key="detail.label" class="artifact-row">
            <dt>{{ detail.label }}</dt>
            <dd>{{ detail.value }}</dd>
          </div>
        </dl>
      </section>

      <div class="shell-actions">
        <button type="button" class="primary-action" @click="focusStartAtlas">Start Atlas</button>
        <button type="button" class="secondary-action" @click="settingsOpen = !settingsOpen">Settings</button>
      </div>

      <section v-if="settingsOpen" class="settings-drawer" aria-label="Atlas settings">
        <p><b>Plan depth:</b> selected in Start Atlas form.</p>
        <p><b>Authority:</b> backend workflow state remains authoritative.</p>
        <p><b>Execution:</b> Vue controls remain disabled.</p>
      </section>
    </div>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { AtlasWorkflowSnapshot } from '../api/atlasClient'
import StatusCard from './StatusCard.vue'

type WorkTargetMode = 'software_development_or_repair' | 'platform_self_improvement'

const props = defineProps<{ snapshot: AtlasWorkflowSnapshot }>()

const settingsOpen = ref(false)
const workTargetMode = ref<WorkTargetMode>('software_development_or_repair')

const workTargets: Array<{ id: WorkTargetMode; label: string; description: string }> = [
  {
    id: 'software_development_or_repair',
    label: 'Software',
    description: 'Plan ordinary software development or repair work with backend gates.'
  },
  {
    id: 'platform_self_improvement',
    label: 'Platform',
    description: 'Plan platform self-improvement intent without granting self-apply authority.'
  }
]

const selectedTarget = computed(() => workTargets.find((target) => target.id === workTargetMode.value) ?? workTargets[0])
const operatorPrompt = computed(() => props.snapshot.goal || 'Describe the development goal, constraints, and expected outcome.')
const atlasReply = computed(() => props.snapshot.backendAuthorityNote || 'I will prepare a bounded plan and keep approval, apply, and execution behind backend gates.')
const currentPhase = computed(() => props.snapshot.phase || props.snapshot.workflowMetadata.currentPhase || 'Waiting for requirement')
const nextAction = computed(() => props.snapshot.primaryCtaLabel || 'Start Atlas')
const safetyProfile = computed(() => {
  const runtime = props.snapshot.safety.runtimeLevel || 'unknown'
  return `${runtime}; backend authoritative; Vue execution disabled`
})
const loopSummary = computed(() => {
  const loop = props.snapshot.practicalLoop
  const bound = loop.boundedLoop ? 'bounded' : 'not started'
  return `${loop.status}; ${bound}; iteration ${loop.currentIteration}/${loop.maxIterations}; stop: ${loop.stopCondition}`
})
const changedFilesSummary = computed(() => {
  if (props.snapshot.practicalLoop.changedFilesCount > 0) {
    return `${props.snapshot.practicalLoop.changedFilesCount} changed file(s) reported by loop metadata`
  }
  return props.snapshot.patchTransaction.available
    ? `${props.snapshot.patchTransaction.candidateCount} patch candidate file group(s) reported`
    : 'No patch candidates reported yet'
})
const verificationSummary = computed(() => props.snapshot.practicalLoop.verificationState || 'Verification waits for backend dry-run or check metadata')
const recoverySummary = computed(() => props.snapshot.practicalLoop.recoveryState || props.snapshot.workflowMetadata.recoveryState || 'No recovery state reported yet')
const draftPrSummary = computed(() => props.snapshot.practicalLoop.draftPrState || 'not_prepared')
const loopArtifactDetails = computed(() => {
  const loop = props.snapshot.practicalLoop
  const empty = 'not reported'
  return [
    { label: 'Pool', value: loop.latestLoopPoolId || empty },
    { label: 'Run', value: loop.latestLoopRunId || empty },
    { label: 'Mode', value: loop.latestLoopMode || empty },
    { label: 'Result', value: loop.latestLoopResultPath || empty },
    { label: 'Source', value: loop.latestLoopSourceDetail || props.snapshot.workflowMetadata.sourceDetail || empty },
    { label: 'Action executed', value: loop.latestLoopActionExecuted ? 'true' : 'false' },
    { label: 'Recovery run', value: loop.latestRecoveryRunId || empty },
    { label: 'Recovery artifact', value: loop.recoveryArtifactAvailable ? 'available' : 'not available' },
    { label: 'Recovery summary', value: loop.recoveryArtifactSummary || empty },
    { label: 'Draft PR artifact', value: loop.latestDraftPrArtifactId || empty },
    { label: 'Draft PR artifact status', value: loop.draftPrArtifactAvailable ? 'available' : 'not available' },
    { label: 'Draft PR summary', value: loop.draftPrArtifactSummary || empty }
  ]
})

function focusStartAtlas() {
  const target = document.getElementById('start-atlas-form')
  if (target instanceof HTMLElement) {
    target.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
</script>

<style scoped>
.fastui-shell {
  display: grid;
  gap: 14px;
}
.conversation-panel {
  display: grid;
  gap: 10px;
}
.message-row {
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  padding: 12px;
  background: #ffffff;
}
.message-row.operator {
  border-left: 4px solid #2563eb;
}
.message-row.atlas {
  border-left: 4px solid #0f766e;
}
.speaker,
.section-label {
  margin: 0 0 5px;
  color: #475569;
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
.message-row p,
.summary-panel p,
.work-target p,
.settings-drawer p,
.artifact-details p {
  margin: 0;
}
.work-target,
.settings-drawer,
.artifact-details {
  display: grid;
  gap: 10px;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  padding: 12px;
  background: #f8fbff;
}
.segmented-control {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  max-width: 360px;
}
.segmented-control button,
.primary-action,
.secondary-action {
  border: 1px solid #b7c5d6;
  border-radius: 6px;
  padding: 10px 12px;
  font: inherit;
  font-weight: 800;
}
.segmented-control button {
  background: #ffffff;
  color: #334155;
}
.segmented-control button.selected {
  border-color: #0f766e;
  background: #dff7ed;
  color: #064e3b;
}
.summary-grid,
.artifact-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.summary-panel,
.artifact-row {
  min-width: 0;
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  padding: 12px;
  background: #ffffff;
}
.artifact-grid {
  margin: 0;
}
.artifact-row dt {
  margin: 0 0 5px;
  color: #475569;
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
.artifact-row dd {
  margin: 0;
  overflow-wrap: anywhere;
}
.summary-panel.safety,
.summary-panel.loop {
  border-color: #a7f3d0;
  background: #ecfdf5;
}
.shell-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.primary-action {
  border-color: #0f766e;
  background: #0f766e;
  color: #ffffff;
}
.secondary-action {
  background: #ffffff;
  color: #334155;
}
@media (prefers-reduced-motion: no-preference) {
  .summary-panel.safety,
  .summary-panel.loop {
    transition: border-color 160ms ease, background-color 160ms ease;
  }
}
</style>