<template>
  <StatusCard title="Patch Review (Display-only)">
    <p class="panel-note">Patch Review shows candidate readiness and missing evidence only. Vue does not generate, approve, apply, verify, rollback, retry, or continue patches.</p>
    <dl class="patch-grid">
      <div>
        <dt>Patch candidate</dt>
        <dd>{{ candidateState }}</dd>
      </div>
      <div>
        <dt>Preview status</dt>
        <dd>{{ previewStatus }}</dd>
      </div>
      <div>
        <dt>Risk class</dt>
        <dd>{{ riskClass }}</dd>
      </div>
      <div>
        <dt>Apply readiness</dt>
        <dd>{{ applyReadiness }}</dd>
      </div>
      <div>
        <dt>Verification evidence</dt>
        <dd>{{ verificationEvidence }}</dd>
      </div>
      <div>
        <dt>Rollback evidence</dt>
        <dd>{{ rollbackEvidence }}</dd>
      </div>
    </dl>
    <p class="backend-note"><b>Patch transaction source:</b> {{ snapshot.patchTransaction.source }}</p>
    <p v-if="warningSummary" class="backend-note"><b>Preview warnings:</b> {{ warningSummary }}</p>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatusCard from './StatusCard.vue'
import type { AtlasWorkflowSnapshot } from '../api/atlasClient'

const props = defineProps<{ snapshot: AtlasWorkflowSnapshot }>()

const candidateState = computed(() => {
  const transaction = props.snapshot.patchTransaction
  if (transaction.available) {
    const id = transaction.transactionId ? ` id=${transaction.transactionId}` : ''
    return `${transaction.candidateCount} backend candidate(s) available for review.${id}`
  }
  if (props.snapshot.workflowMetadata.activePlanAvailable) return 'No patch transaction metadata yet; review plan items first.'
  return 'Waiting for Start Atlas and Plan Review metadata.'
})

const previewStatus = computed(() => props.snapshot.patchTransaction.previewStatus)
const riskClass = computed(() => props.snapshot.patchTransaction.riskClass)
const warningSummary = computed(() => props.snapshot.patchTransaction.warnings.join(' / '))

const applyReadiness = computed(() => {
  const gates = props.snapshot.guardedExecutionReview.reviewItems
  const ready = gates.filter((item) => item.ready).length
  return gates.length > 0 ? `${ready}/${gates.length} guarded gate items ready` : 'No guarded apply metadata available.'
})

const verificationEvidence = computed(() => props.snapshot.patchTransaction.verificationEnabled === false ? 'Verification remains disabled; evidence is display-only.' : 'Unexpected verification capability metadata.')
const rollbackEvidence = computed(() => props.snapshot.patchTransaction.rollbackReady ? 'Rollback metadata is ready for manual review only.' : 'Rollback readiness metadata missing or not ready.')
</script>

<style scoped>
.panel-note,
.backend-note {
  color: #475569;
  font-size: 13px;
}
.patch-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 12px 0;
}
.patch-grid div {
  border-left: 3px solid #0f766e;
  padding: 8px 10px;
  background: #ffffff;
}
dt {
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
dd {
  margin: 4px 0 0;
}
@media (max-width: 720px) {
  .patch-grid {
    grid-template-columns: 1fr;
  }
}
</style>
