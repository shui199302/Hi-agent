<script setup lang="ts">
withDefaults(defineProps<{ rows?: number }>(), { rows: 3 })
</script>

<template>
  <div class="loading-state" aria-label="正在加载">
    <div v-for="row in rows" :key="row" class="skeleton-row" :style="{ width: `${100 - (row % 3) * 9}%` }" />
  </div>
</template>
