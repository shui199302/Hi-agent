<script setup lang="ts">
import AppIcon from './AppIcon.vue'

withDefaults(defineProps<{ icon?: string; title: string; description?: string }>(), { icon: 'sparkles' })
</script>

<template>
  <div class="empty-state">
    <div class="empty-icon"><AppIcon :name="icon" :size="24" /></div>
    <h3>{{ title }}</h3>
    <p v-if="description">{{ description }}</p>
    <slot />
  </div>
</template>
