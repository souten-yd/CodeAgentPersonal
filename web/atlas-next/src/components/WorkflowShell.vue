<template><StatusCard title="Workflow (Read-only)">
  <p><b>Goal:</b> {{ snapshot.goal || 'N/A' }}</p><p><b>Project path:</b> {{ snapshot.projectPath || 'N/A' }}</p>
  <p><b>Phase:</b> {{ snapshot.phase || 'unknown' }}</p><p><b>Status:</b> {{ snapshot.status || 'unknown' }}</p>
  <p><b>Primary CTA:</b> {{ snapshot.primaryCtaLabel || 'Read-only preview' }} ({{ snapshot.primaryCtaState || 'read_only' }})</p>
  <button disabled>Read-only preview (not wired)</button>
</StatusCard></template>
<script setup lang="ts">import StatusCard from './StatusCard.vue';import type { AtlasWorkflowSnapshot } from '../api/atlasClient';defineProps<{ snapshot: AtlasWorkflowSnapshot }>()</script>
