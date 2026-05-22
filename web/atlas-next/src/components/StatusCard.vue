<template>
  <section class="card">
    <header class="card-header">
      <h3>{{ title }}</h3>
      <span class="badge">Read-only</span>
    </header>
    <slot />
  </section>
</template>

<script setup lang="ts">
defineProps<{ title: string }>()
</script>

<style scoped>
.card {
  border: 1px solid #d8e0ea;
  padding: 14px;
  border-radius: 10px;
  margin: 10px 0;
  background: #f9fbff;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid #9db4d2;
  color: #2d4f78;
  background: #edf4ff;
}
</style>
