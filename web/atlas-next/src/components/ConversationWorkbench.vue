<template>
  <StatusCard title="Atlas Conversation">
    <div class="conversation-stack">
      <section class="message operator">
        <p class="speaker">Operator</p>
        <p>Define the requirement, choose planning behavior, answer questions, then review the backend-owned plan before any guarded execution step.</p>
      </section>

      <section class="message atlas">
        <p class="speaker">Atlas</p>
        <p>I can prepare planning metadata and organize the review path. Execution controls stay unavailable in Vue.</p>
      </section>

      <div class="conversation-grid">
        <label>
          Plan setting
          <select v-model="planMode">
            <option value="standard">Standard plan</option>
            <option value="careful">Careful plan</option>
            <option value="minimal">Minimal plan</option>
          </select>
        </label>
        <label>
          Operation setting
          <select v-model="operationMode">
            <option value="review_first">Review first</option>
            <option value="preview_only">Execute preview only</option>
            <option value="manual_gate">Manual gate required</option>
          </select>
        </label>
      </div>

      <label>
        Questions for Atlas
        <textarea v-model="questions" rows="3" placeholder="Ask what Atlas should clarify before creating or reviewing the plan."></textarea>
      </label>

      <label>
        Detailed definition
        <textarea v-model="details" rows="4" placeholder="Add constraints, acceptance criteria, files, or behavior that must be preserved."></textarea>
      </label>

      <section class="requirement-summary" aria-label="Requirement summary">
        <p class="speaker">Requirement summary</p>
        <dl>
          <div>
            <dt>Plan</dt>
            <dd>{{ planModeLabel }}</dd>
          </div>
          <div>
            <dt>Operation</dt>
            <dd>{{ operationModeLabel }}</dd>
          </div>
          <div>
            <dt>Questions</dt>
            <dd>{{ questionsSummary }}</dd>
          </div>
          <div>
            <dt>Definition</dt>
            <dd>{{ detailsSummary }}</dd>
          </div>
        </dl>
      </section>

      <div class="review-strip" aria-label="Conversation safety state">
        <span>Plan metadata only</span>
        <span>Backend authoritative</span>
        <span>Vue execution disabled</span>
      </div>
    </div>
  </StatusCard>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import StatusCard from './StatusCard.vue'

const planMode = ref('standard')
const operationMode = ref('review_first')
const questions = ref('')
const details = ref('')

const planModeLabel = computed(() => {
  if (planMode.value === 'careful') return 'Careful plan with expanded review context'
  if (planMode.value === 'minimal') return 'Minimal plan with tight scope'
  return 'Standard plan with normal review depth'
})
const operationModeLabel = computed(() => {
  if (operationMode.value === 'preview_only') return 'Preview-only operation review'
  if (operationMode.value === 'manual_gate') return 'Manual gate required before any next step'
  return 'Review-first planning flow'
})
const questionsSummary = computed(() => questions.value.trim() || 'No clarification questions entered yet.')
const detailsSummary = computed(() => details.value.trim() || 'No acceptance criteria or file constraints entered yet.')
</script>

<style scoped>
.conversation-stack {
  display: grid;
  gap: 12px;
}
.message {
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  padding: 12px;
  background: #ffffff;
}
.message.atlas {
  border-left: 4px solid #0f766e;
}
.message.operator {
  border-left: 4px solid #2563eb;
}
.speaker {
  margin: 0 0 4px;
  color: #475569;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}
.conversation-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
label {
  display: grid;
  gap: 6px;
  font-weight: 700;
}
select,
textarea {
  box-sizing: border-box;
  width: 100%;
  border: 1px solid #b7c5d6;
  border-radius: 6px;
  font: inherit;
  padding: 9px;
}
.requirement-summary {
  border: 1px solid #d8e0ea;
  border-radius: 8px;
  padding: 12px;
  background: #ffffff;
}
.requirement-summary dl {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin: 8px 0 0;
}
.requirement-summary div {
  min-width: 0;
  border-left: 3px solid #2563eb;
  padding: 8px 10px;
  background: #f8fbff;
}
dt {
  color: #64748b;
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}
dd {
  margin: 4px 0 0;
  overflow-wrap: anywhere;
}
.review-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.review-strip span {
  border: 1px solid #a7f3d0;
  border-radius: 999px;
  padding: 4px 10px;
  background: #ecfdf5;
  color: #065f46;
  font-size: 12px;
  font-weight: 700;
}
</style>
