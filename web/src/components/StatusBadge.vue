<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ status?: string; label?: string }>(), { status: 'unknown' })

const tone = computed(() => {
  const value = props.status.toLowerCase()
  if (['healthy', 'ready', 'online', 'connected', 'enabled', 'completed', 'indexed', 'ok', 'success'].includes(value)) return 'positive'
  if (['running', 'pending', 'indexing', 'connecting', 'waiting_approval'].includes(value)) return 'progress'
  if (['failed', 'error', 'offline', 'unhealthy', 'interrupted'].includes(value)) return 'negative'
  return 'neutral'
})

const text = computed(() => props.label ?? ({
  healthy: '健康', ready: '就绪', online: '在线', connected: '已连接', enabled: '已启用', completed: '已完成',
  indexed: '已索引', running: '运行中', pending: '等待中', indexing: '索引中', failed: '失败', error: '异常',
  offline: '离线', disabled: '已停用', unknown: '未知', waiting_approval: '等待审批', cancelled: '已取消',
}[props.status.toLowerCase()] ?? props.status))
</script>

<template>
  <span class="status-badge" :class="`status-${tone}`">
    <i />
    {{ text }}
  </span>
</template>
