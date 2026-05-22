<template><section class="card"><h3>{{ title }}</h3><slot /></section></template>
<script setup lang="ts">defineProps<{ title: string }>()</script>
<style scoped>.card{border:1px solid #ccc;padding:12px;border-radius:8px;margin:8px 0}</style>
