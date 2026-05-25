<template>
  <StatusCard title="Review Board">
    <p class="board-note">Review, approval, and preview are visible here as backend-owned context. Vue does not approve, execute, apply, verify, rollback, retry, or continue.</p>
    <div class="review-board-grid">
      <section class="review-panel">
        <p class="panel-kicker">Requirement</p>
        <h3>Plan Review</h3>
        <p>{{ planReviewDetail }}</p>
      </section>
      <section class="review-panel">
        <p class="panel-kicker">Human Gate</p>
        <h3>Approval Review</h3>
        <p>{{ approvalReviewDetail }}</p>
      </section>
      <section class="review-panel">
        <p class="panel-kicker">Dry-run</p>
        <h3>Execute Preview</h3>
        <p>{{ executePreviewDetail }}</p>
      </section>
    </div>
    <p class="backend-note"><b>Backend authority:</b> {{ snapshot.backendAuthorityNote }}</p>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatusCard from './StatusCard.vue'
import type { AtlasWorkflowSnapshot } from '../api/atlasClient'

const props = defineProps<{ snapshot: AtlasWorkflowSnapshot }>()

const planReviewDetail = computed(() => {
  if (props.snapshot.workflowMetadata.activePlanAvailable) return 'Active plan metadata is available for read-only review.'
  if (props.snapshot.workflowMetadata.planPoolAvailable) return 'PlanPool metadata is available; review the generated items before any approval step.'
  return 'Start Atlas first to create planning metadata for review.'
})

const approvalReviewDetail = computed(() => {
  const reviewItems = props.snapshot.guardedExecutionReview.reviewItems.length
  if (reviewItems > 0) return `${reviewItems} backend gate items are visible for human approval review.`
  return 'Approval context appears after backend-owned plan and gate metadata exist.'
})

const executePreviewDetail = computed(() => {
  if (props.snapshot.artifacts.dryRun === true) return 'Dry-run metadata exists; execution remains gated by approval and backend checks.'
  return 'Execute Preview waits for dry-run evidence. Vue does not start dry-run or execution from this board.'
})
</script>

<style scoped>
.board-note,
.backend-note {
  color: #475569;
  font-size: 13px;
}
.review-board-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 12px 0;
}
.review-panel {
  border: 1px solid #d8e0ea;
  border-radius: 6px;
  padding: 12px;
  background: #ffffff;
}
.panel-kicker {
  margin: 0 0 4px;
  color: #0f766e;
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
h3 {
  margin: 0 0 6px;
}
p {
  margin: 0;
}
@media (max-width: 720px) {
  .review-board-grid {
    grid-template-columns: 1fr;
  }
}
</style>
