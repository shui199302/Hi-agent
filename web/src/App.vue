<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import { request } from './api'
import AppIcon from './components/AppIcon.vue'
import { hashSegments, isSettingsSection, navigateTo } from './navigation'
import { dismissNotice, notificationState } from './notifications'
import type { SystemStatus, UserProfile } from './types'

const ChatView = defineAsyncComponent(() => import('./pages/ChatView.vue'))
const ProjectsView = defineAsyncComponent(() => import('./pages/ProjectsView.vue'))
const ArtifactsView = defineAsyncComponent(() => import('./pages/ArtifactsView.vue'))
const AgentsView = defineAsyncComponent(() => import('./pages/AgentsView.vue'))
const KnowledgeView = defineAsyncComponent(() => import('./pages/KnowledgeView.vue'))
const OperationsView = defineAsyncComponent(() => import('./pages/OperationsView.vue'))
const SettingsView = defineAsyncComponent(() => import('./pages/SettingsView.vue'))
const LoginView = defineAsyncComponent(() => import('./pages/LoginView.vue'))

const navigation = [
  { id: 'chat', label: '对话', hint: '运行智能体', icon: 'chat', component: ChatView },
  { id: 'projects', label: '项目', hint: '资源与运行空间', icon: 'file', component: ProjectsView },
  { id: 'agents', label: '智能体', hint: '提示词与能力', icon: 'agents', component: AgentsView },
  { id: 'knowledge', label: '知识库', hint: '文档与检索', icon: 'database', component: KnowledgeView },
  { id: 'artifacts', label: '内容生成', hint: '图片、报告与演示', icon: 'sparkles', component: ArtifactsView },
  { id: 'operations', label: '运行监测', hint: 'Run Trace 与质量', icon: 'activity', component: OperationsView },
  { id: 'settings', label: '设置', hint: '模型、工具与工作台', icon: 'settings', component: SettingsView },
] as const

const active = ref('chat')
const mobileNavOpen = ref(false)
const systemOnline = ref<boolean | null>(null)
const status = ref<SystemStatus | null>(null)
let statusTimer: number | undefined
const authLoading = ref(true)
const user = ref<UserProfile | null>(null)

const current = computed(() => navigation.find((item) => item.id === active.value) ?? navigation[0])

function syncHash(): void {
  const id = hashSegments()[0] ?? ''
  const normalized = isSettingsSection(id) ? 'settings' : id
  if (navigation.some((item) => item.id === normalized)) active.value = normalized
}

function navigate(id: string): void {
  active.value = id
  navigateTo(id)
  mobileNavOpen.value = false
}

async function refreshStatus(): Promise<void> {
  if (!user.value) return
  try {
    status.value = await request<SystemStatus>('/system/status')
    systemOnline.value = true
  } catch {
    systemOnline.value = false
  }
}

async function refreshUser(): Promise<void> {
  try {
    user.value = await request<UserProfile>('/auth/me')
  } catch {
    user.value = null
  } finally {
    authLoading.value = false
  }
}

function authenticated(profile: UserProfile): void {
  user.value = profile
  authLoading.value = false
  void refreshStatus()
}

async function logout(): Promise<void> {
  try {
    await request('/auth/logout', { method: 'POST' })
  } finally {
    user.value = null
    status.value = null
    systemOnline.value = null
  }
}

onMounted(async () => {
  syncHash()
  window.addEventListener('hashchange', syncHash)
  await refreshUser()
  void refreshStatus()
  statusTimer = window.setInterval(refreshStatus, 30_000)
})

onBeforeUnmount(() => {
  window.removeEventListener('hashchange', syncHash)
  if (statusTimer) window.clearInterval(statusTimer)
})
</script>

<template>
  <div v-if="authLoading" class="auth-loading"><span class="spinner" /><strong>正在验证本地登录状态…</strong></div>
  <LoginView v-else-if="!user" @authenticated="authenticated" />
  <div v-else class="app-shell">
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
        <div class="account-card">
          <span class="account-avatar">{{ user?.username?.slice(0, 1) }}</span>
          <div><strong>{{ user?.username }}</strong><span>{{ user?.role === 'admin' ? '管理员' : '个人账号' }}</span></div>
          <button class="account-logout" type="button" @click="logout">退出</button>
        </div>
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
