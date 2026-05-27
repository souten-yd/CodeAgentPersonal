<template>
  <StatusCard title="Start Atlas">
    <p class="safety-boundary"><b>Safety boundary:</b> Start Atlas creates planning metadata only. Execution/apply/approve/verify/rollback/retry/continue stay backend/manual. Execution controls are intentionally unavailable in Atlas Next.</p>
    <form id="start-atlas-form" @submit.prevent="submitPlanning" class="requirement-form">
      <label>
        Requirement
        <textarea v-model="form.input" rows="5" required placeholder="Describe the outcome Atlas should plan for."></textarea>
      </label>
      <details class="advanced-settings">
        <summary>Planning settings</summary>
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
      </details>
      <div class="form-actions">
        <button type="submit" :disabled="isSubmitting">{{ isSubmitting ? 'Starting Atlas...' : 'Start Atlas' }}</button>
      </div>
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
.requirement-form { display: grid; gap: 12px; }
.requirement-form label { display: grid; gap: 4px; font-weight: 600; }
.requirement-form input,
.requirement-form textarea {
  box-sizing: border-box;
  width: 100%;
  border: 1px solid #b7c5d6;
  border-radius: 6px;
  font: inherit;
  padding: 9px;
}
.form-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
button {
  border: 0;
  border-radius: 6px;
  padding: 10px 16px;
  background: #0f766e;
  color: #ffffff;
  font: inherit;
  font-weight: 700;
}
button:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}
.advanced-settings {
  border: 1px solid #d8e0ea;
  border-radius: 6px;
  padding: 10px;
  background: #ffffff;
}
.advanced-settings summary {
  cursor: pointer;
  font-weight: 700;
}
.advanced-settings label {
  margin-top: 10px;
}
.safety-boundary {
  color: #475569;
  font-size: 13px;
}
.error { color: #b91c1c; }
.result { margin-top: 8px; }
</style>