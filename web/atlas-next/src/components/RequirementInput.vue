<template>
  <StatusCard title="Start Atlas Planning (PlanPool only)">
    <p><b>Safety boundary:</b> This Vue surface can create planning metadata only. Execution/apply/approve/verify/rollback/retry/continue stay backend/manual. Execution controls are intentionally unavailable in VUE16.</p>
    <form @submit.prevent="submitPlanning" class="requirement-form">
      <label>
        Requirement / goal
        <textarea v-model="form.input" rows="3" required placeholder="Describe the requirement or goal."></textarea>
      </label>
      <label>
        Project path
        <input v-model="form.project_path" type="text" placeholder="/workspace/CodeAgentPersonal" />
      </label>
      <label>
        Project name
        <input v-model="form.project_name" type="text" />
      </label>
      <label>
        Planning depth
        <input v-model="form.planning_depth" type="text" />
      </label>
      <label>
        Workspace ID
        <input v-model="form.workspace_id" type="text" />
      </label>
      <button type="submit" :disabled="isSubmitting">{{ isSubmitting ? 'Starting...' : 'Start Atlas Planning' }}</button>
    </form>

    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>

    <PlanReviewPanel v-if="result" :result="result" />
  </StatusCard>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import StatusCard from './StatusCard.vue'
import { createPlanPool, type CreatePlanPoolResponse } from '../api/atlasClient'
import PlanReviewPanel from './PlanReviewPanel.vue'

const form = reactive({
  input: '',
  project_path: '/workspace/CodeAgentPersonal',
  project_name: 'CodeAgentPersonal',
  planning_depth: 'standard',
  workspace_id: 'default'
})

const isSubmitting = ref(false)
const errorMessage = ref('')
const result = ref<CreatePlanPoolResponse | null>(null)

async function submitPlanning() {
  errorMessage.value = ''
  result.value = null
  if (!form.input.trim()) {
    errorMessage.value = 'Requirement / goal is required.'
    return
  }
  isSubmitting.value = true
  try {
    result.value = await createPlanPool({ ...form })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Failed to start Atlas planning.'
  } finally {
    isSubmitting.value = false
  }
}
</script>

<style scoped>
.requirement-form { display: grid; gap: 8px; }
.requirement-form label { display: grid; gap: 4px; font-weight: 600; }
.requirement-form input, .requirement-form textarea { font: inherit; padding: 6px; }
.error { color: #b91c1c; }
.result { margin-top: 8px; }
</style>
