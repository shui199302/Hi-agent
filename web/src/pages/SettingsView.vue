<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { SETTINGS_DEFAULT_SECTION, hashSegments, isSettingsSection, navigateTo, type SettingsSectionId } from '../navigation'

const McpView = defineAsyncComponent(() => import('./McpView.vue'))
const SkillsView = defineAsyncComponent(() => import('./SkillsView.vue'))
const ModelsView = defineAsyncComponent(() => import('./ModelsView.vue'))
const PromptsView = defineAsyncComponent(() => import('./PromptsView.vue'))
const DigitalHumanView = defineAsyncComponent(() => import('./DigitalHumanView.vue'))

const sections = [
  { id: 'mcp', label: 'MCP', hint: '服务与工具', icon: 'plug', component: McpView },
  { id: 'skills', label: 'Skills', hint: '技能目录', icon: 'sparkles', component: SkillsView },
  { id: 'models', label: '模型与系统', hint: '模型端点与系统状态', icon: 'server', component: ModelsView },
  { id: 'prompts', label: '提示词模板', hint: '复用与版本基线', icon: 'sparkles', component: PromptsView },
  { id: 'digital-human', label: '数字人工作台', hint: '动态 2D 形象生成', icon: 'portrait', component: DigitalHumanView },
] as const

const active = ref<SettingsSectionId>(SETTINGS_DEFAULT_SECTION)
const current = computed(() => sections.find((item) => item.id === active.value) ?? sections[2])

function sectionFromHash(): SettingsSectionId {
  const parts = hashSegments()
  const candidate = parts[0] === 'settings' ? parts[1] : parts[0]
  return isSettingsSection(candidate) ? candidate : SETTINGS_DEFAULT_SECTION
}

function syncHash(): void {
  active.value = sectionFromHash()
}

function navigate(id: SettingsSectionId): void {
  active.value = id
  navigateTo(`settings/${id}`)
}

onMounted(() => {
  syncHash()
  window.addEventListener('hashchange', syncHash)
})

onBeforeUnmount(() => window.removeEventListener('hashchange', syncHash))
</script>

<template>
  <div class="settings-shell">
    <nav class="settings-nav" aria-label="设置分类">
      <div class="settings-heading">
        <span class="settings-icon"><AppIcon name="settings" :size="18" /></span>
        <div><strong>设置</strong><small>配置本地智能体运行环境</small></div>
      </div>
      <div class="settings-tabs">
        <button
          v-for="item in sections"
          :key="item.id"
          type="button"
          :class="{ active: active === item.id }"
          @click="navigate(item.id)"
        >
          <AppIcon :name="item.icon" :size="16" />
          <span><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
        </button>
      </div>
    </nav>
    <div class="settings-content">
      <Suspense>
        <KeepAlive>
          <component :is="current.component" :key="current.id" />
        </KeepAlive>
        <template #fallback><div class="page-loading"><span class="spinner" />正在加载设置…</div></template>
      </Suspense>
    </div>
  </div>
</template>

<style scoped>
.settings-shell{display:flex;height:100%;flex-direction:column}.settings-nav{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:14px 38px;background:rgba(255,254,250,.94);border-bottom:1px solid var(--line);box-shadow:var(--shadow-sm)}.settings-heading{display:flex;align-items:center;gap:10px;white-space:nowrap}.settings-heading>div{display:flex;flex-direction:column}.settings-heading strong{font-size:13px}.settings-heading small{margin-top:2px;color:var(--muted);font-size:9px}.settings-icon{display:grid;width:34px;height:34px;place-items:center;color:var(--green);background:var(--green-soft);border-radius:9px}.settings-tabs{display:flex;gap:5px;padding:4px;background:#f1f3ee;border-radius:11px}.settings-tabs button{display:flex;min-width:135px;align-items:center;gap:8px;padding:7px 10px;color:var(--muted);text-align:left;background:transparent;border:0;border-radius:8px;cursor:pointer}.settings-tabs button:hover{color:var(--ink);background:rgba(255,255,255,.55)}.settings-tabs button.active{color:var(--green);background:#fff;box-shadow:0 2px 8px rgba(24,45,34,.08)}.settings-tabs span{display:flex;flex-direction:column}.settings-tabs strong{font-size:10px}.settings-tabs small{margin-top:2px;color:inherit;font-size:8px;opacity:.7}.settings-content{min-height:0;flex:1}.settings-content :deep(.page-inner){padding-top:27px}@media(max-width:900px){.settings-nav{align-items:flex-start;flex-direction:column;padding-inline:27px}.settings-tabs{width:100%}.settings-tabs button{min-width:0;flex:1}}@media(max-width:760px){.settings-nav{position:sticky;z-index:10;top:57px;padding:10px 16px}.settings-heading{display:none}.settings-tabs{overflow-x:auto}.settings-tabs button{min-width:110px}.settings-content :deep(.page-inner){padding-top:22px}}
</style>
