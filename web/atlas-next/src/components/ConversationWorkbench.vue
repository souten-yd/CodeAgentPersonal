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

      <div class="review-strip" aria-label="Conversation safety state">
        <span>Plan metadata only</span>
        <span>Backend authoritative</span>
        <span>Vue execution disabled</span>
      </div>
    </div>
  </StatusCard>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import StatusCard from './StatusCard.vue'

const planMode = ref('standard')
const operationMode = ref('review_first')
const questions = ref('')
const details = ref('')
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
