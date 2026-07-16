<script setup lang="ts">
import { onDeactivated } from 'vue'
import AppIcon from './AppIcon.vue'

defineProps<{ open: boolean; title: string; description?: string; wide?: boolean }>()
const emit = defineEmits<{ close: [] }>()

onDeactivated(() => emit('close'))
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="modal-backdrop" @mousedown.self="$emit('close')">
        <section class="modal-panel" :class="{ 'modal-wide': wide }" role="dialog" aria-modal="true" :aria-label="title">
          <header class="modal-header">
            <div>
              <h2>{{ title }}</h2>
              <p v-if="description">{{ description }}</p>
            </div>
            <button class="icon-button" type="button" aria-label="关闭" @click="$emit('close')">
              <AppIcon name="close" />
            </button>
          </header>
          <div class="modal-body"><slot /></div>
          <footer v-if="$slots.footer" class="modal-footer"><slot name="footer" /></footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
