<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import { request } from './api'
import AppIcon from './components/AppIcon.vue'
import { dismissNotice, notificationState } from './notifications'
import type { SystemStatus } from './types'

const ChatView = defineAsyncComponent(() => import('./pages/ChatView.vue'))
const AgentsView = defineAsyncComponent(() => import('./pages/AgentsView.vue'))
const KnowledgeView = defineAsyncComponent(() => import('./pages/KnowledgeView.vue'))
const McpView = defineAsyncComponent(() => import('./pages/McpView.vue'))
const SkillsView = defineAsyncComponent(() => import('./pages/SkillsView.vue'))
const ModelsView = defineAsyncComponent(() => import('./pages/ModelsView.vue'))
const OperationsView = defineAsyncComponent(() => import('./pages/OperationsView.vue'))

const navigation = [
  { id: 'chat', label: '对话', hint: '运行智能体', icon: 'chat', component: ChatView },
  { id: 'agents', label: '智能体', hint: '提示词与能力', icon: 'agents', component: AgentsView },
  { id: 'knowledge', label: '知识库', hint: '文档与检索', icon: 'database', component: KnowledgeView },
  { id: 'mcp', label: 'MCP', hint: '服务与工具', icon: 'plug', component: McpView },
  { id: 'skills', label: 'Skills', hint: '技能目录', icon: 'sparkles', component: SkillsView },
  { id: 'models', label: '模型与系统', hint: '端点与状态', icon: 'server', component: ModelsView },
  { id: 'operations', label: '运行与质量', hint: 'Trace 与评测', icon: 'activity', component: OperationsView },
] as const

const active = ref('chat')
const mobileNavOpen = ref(false)
const systemOnline = ref<boolean | null>(null)
const status = ref<SystemStatus | null>(null)
let statusTimer: number | undefined

const current = computed(() => navigation.find((item) => item.id === active.value) ?? navigation[0])

function syncHash(): void {
  const id = window.location.hash.replace('#/', '').replace('#', '').split('/')[0]
  if (navigation.some((item) => item.id === id)) active.value = id
}

function navigate(id: string): void {
  active.value = id
  window.location.hash = `/${id}`
  mobileNavOpen.value = false
}

async function refreshStatus(): Promise<void> {
  try {
    status.value = await request<SystemStatus>('/system/status')
    systemOnline.value = true
  } catch {
    systemOnline.value = false
  }
}

onMounted(() => {
  syncHash()
  window.addEventListener('hashchange', syncHash)
  void refreshStatus()
  statusTimer = window.setInterval(refreshStatus, 30_000)
})

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncHash)
  if (statusTimer) window.clearInterval(statusTimer)
})
</script>

<template>
  <div class="app-shell">
    <div v-if="mobileNavOpen" class="mobile-scrim" @click="mobileNavOpen = false" />
    <aside class="sidebar" :class="{ 'sidebar-open': mobileNavOpen }">
      <div class="brand">
        <div class="brand-mark">
          <span class="brand-orbit" />
          <span class="brand-core">H</span>
        </div>
        <div class="brand-copy">
          <strong>Hi-agent</strong>
          <span>LOCAL AI STUDIO</span>
        </div>
        <button class="icon-button mobile-close" type="button" aria-label="关闭菜单" @click="mobileNavOpen = false">
          <AppIcon name="close" />
        </button>
      </div>

      <nav class="primary-nav" aria-label="主导航">
        <p class="nav-eyebrow">工作空间</p>
        <button
          v-for="item in navigation"
          :key="item.id"
          class="nav-item"
          :class="{ active: active === item.id }"
          type="button"
          @click="navigate(item.id)"
        >
          <span class="nav-icon"><AppIcon :name="item.icon" /></span>
          <span class="nav-copy">
            <strong>{{ item.label }}</strong>
            <small>{{ item.hint }}</small>
          </span>
          <AppIcon v-if="active === item.id" name="chevron" :size="15" />
        </button>
      </nav>

      <div class="sidebar-footer">
        <div class="service-indicator">
          <span class="service-dot" :class="systemOnline === true ? 'online' : systemOnline === false ? 'offline' : ''" />
          <div>
            <strong>{{ systemOnline === true ? '本地服务正常' : systemOnline === false ? '服务未连接' : '正在检测服务' }}</strong>
            <span>{{ status?.version ? `Hi-agent ${status.version}` : '127.0.0.1:8787' }}</span>
          </div>
          <button class="icon-button small" type="button" aria-label="刷新状态" @click="refreshStatus">
            <AppIcon name="refresh" :size="16" />
          </button>
        </div>
        <div class="privacy-note">
          <span class="privacy-lock">●</span>
          数据保留在本机
        </div>
      </div>
    </aside>

    <main class="main-area">
      <header class="mobile-header">
        <button class="icon-button" type="button" aria-label="打开菜单" @click="mobileNavOpen = true">
          <AppIcon name="menu" />
        </button>
        <div class="mobile-brand"><span>H</span> Hi-agent</div>
        <span class="service-dot" :class="systemOnline ? 'online' : 'offline'" />
      </header>
      <Suspense>
        <KeepAlive>
          <component :is="current.component" :key="current.id" />
        </KeepAlive>
        <template #fallback>
          <div class="page-loading">
            <span class="spinner" />
            正在准备工作台…
          </div>
        </template>
      </Suspense>
    </main>

    <div class="toast-stack" aria-live="polite">
      <TransitionGroup name="toast">
        <button
          v-for="notice in notificationState"
          :key="notice.id"
          class="toast"
          :class="`toast-${notice.tone}`"
          type="button"
          @click="dismissNotice(notice.id)"
        >
          <span class="toast-icon"><AppIcon :name="notice.tone === 'error' ? 'alert' : notice.tone === 'success' ? 'check' : 'info'" :size="17" /></span>
          {{ notice.message }}
          <AppIcon name="close" :size="15" />
        </button>
      </TransitionGroup>
    </div>
  </div>
</template>
