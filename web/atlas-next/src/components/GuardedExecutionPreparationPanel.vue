<template>
  <StatusCard title="Guarded Execution Preparation (Display-only)">
    <p class="panel-note">Preparation summarizes backend gate readiness before any guarded execution surface is allowed. Vue does not approve, dry-run, execute, apply, verify, rollback, retry, or continue actions.</p>
    <dl class="prep-grid">
      <div>
        <dt>Gate readiness</dt>
        <dd>{{ readyCount }}/{{ totalCount }} ready</dd>
      </div>
      <div>
        <dt>Endpoint contract</dt>
        <dd>{{ review.endpointContractStatus }}</dd>
      </div>
      <div>
        <dt>Required dry-run</dt>
        <dd>{{ review.requiresDryRun ? 'required' : 'missing requirement metadata' }}</dd>
      </div>
      <div>
        <dt>Required approval</dt>
        <dd>{{ review.requiresApproval ? 'required' : 'missing requirement metadata' }}</dd>
      </div>
    </dl>
    <p class="panel-note"><b>Missing gates:</b> {{ missingGateSummary }}</p>
    <p v-if="review.blockedReasons.length" class="panel-note"><b>Blocked reasons:</b> {{ review.blockedReasons.join(' | ') }}</p>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatusCard from './StatusCard.vue'
import type { AtlasGuardedExecutionReviewState } from '../api/atlasClient'

const props = defineProps<{ review: AtlasGuardedExecutionReviewState }>()

const totalCount = computed(() => props.review.reviewItems.length)
const readyCount = computed(() => props.review.reviewItems.filter((item) => item.ready).length)
const missingGateSummary = computed(() => {
  const missing = props.review.reviewItems.filter((item) => !item.ready).map((item) => item.label)
  return missing.length ? missing.join(' / ') : 'No missing gate metadata reported.'
})
</script>

<style scoped>
.panel-note {
  color: #475569;
  font-size: 13px;
}
.prep-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 12px 0;
}
.prep-grid div {
  border-left: 3px solid #475569;
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
  .prep-grid {
    grid-template-columns: 1fr;
  }
}
</style>
