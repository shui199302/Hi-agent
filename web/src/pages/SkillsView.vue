<script setup lang="ts">
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { formatApiError, jsonBody, listOf, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { notify } from '../notifications'
import { navigateTo } from '../navigation'
import type { RemoteSkill, SkillMetadata } from '../types'

interface SkillDetail extends SkillMetadata {
  instructions?: string
  references?: string[]
  assets?: string[]
  directory?: string
  scripts_allowed?: boolean
  valid?: boolean
  error?: string | null
}

const skills = ref<SkillMetadata[]>([])
const loading = ref(true)
const loadError = ref('')
const query = ref('')
const selected = ref<SkillDetail | null>(null)
const detailOpen = ref(false)
const detailLoading = ref(false)
const remoteOpen = ref(false)
const remoteQuery = ref('')
const remoteSource = ref<'all' | 'github' | 'clawhub'>('all')
const remoteLoading = ref(false)
const remoteResults = ref<RemoteSkill[]>([])
const installing = ref('')
const reviewOpen = ref(false)
const reviewLoading = ref(false)
const reviewSkill = ref<RemoteSkill | null>(null)
const creatorOpen = ref(false)
const creating = ref(false)
const createForm = reactive({ name: '', display_name: '', description: '', short_description: '', default_prompt: '', instructions: '# 工作流\n\n1. 明确任务目标。\n2. 执行并校验结果。' })

const filtered = computed(() => {
  const value = query.value.trim().toLowerCase()
  if (!value) return skills.value
  return skills.value.filter((skill) => `${skill.name} ${skill.display_name ?? ''} ${skill.description}`.toLowerCase().includes(value))
})

function displayName(skill: SkillMetadata): string {
  const builtins: Record<string, string> = {
    'knowledge-base-qa': '知识库问答',
    'document-summary': '文档摘要',
    'web-research': '网络调研',
    'codebase-analysis': '代码库分析',
    'data-analysis': '数据分析',
    'report-writing': '报告撰写',
    'task-planning': '任务规划',
    'find-skills': '发现 Skills',
    'skill-creator': '创建 Skill',
  }
  return skill.display_name || builtins[skill.name] || skill.name
}

async function searchRemote(): Promise<void> {
  if (remoteQuery.value.trim().length < 2) return
  remoteLoading.value = true
  remoteResults.value = []
  try {
    remoteResults.value = await request<RemoteSkill[]>(`/skills-remote/search?q=${encodeURIComponent(remoteQuery.value.trim())}&source=${remoteSource.value}`)
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { remoteLoading.value = false }
}

async function openRemoteReview(skill: RemoteSkill): Promise<void> {
  reviewSkill.value = skill
  reviewOpen.value = true
  if (skill.source !== 'clawhub' || !skill.slug) return
  reviewLoading.value = true
  try { reviewSkill.value = await request<RemoteSkill>(`/skills-remote/clawhub/${encodeURIComponent(skill.slug)}`) }
  catch (error) { notify(formatApiError(error), 'error'); reviewOpen.value = false }
  finally { reviewLoading.value = false }
}

async function installRemote(): Promise<void> {
  const skill = reviewSkill.value
  if (!skill) return
  installing.value = skill.name
  try {
    await request('/skills-remote/install', { method: 'POST', ...jsonBody({ source: skill.source, catalog: skill.catalog, path: skill.path, slug: skill.slug, version: skill.version, confirm: true, replace: false }) })
    reviewOpen.value = false
    notify(`${skill.name} 已安装，尚未绑定任何智能体`, 'success')
    await load()
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { installing.value = '' }
}

async function createSkill(): Promise<void> {
  creating.value = true
  try {
    await request('/skills', { method: 'POST', ...jsonBody({ ...createForm, confirm: true }) })
    creatorOpen.value = false
    notify(`${createForm.name} 已创建，尚未绑定任何智能体`, 'success')
    Object.assign(createForm, { name: '', display_name: '', description: '', short_description: '', default_prompt: '', instructions: '# 工作流\n\n1. 明确任务目标。\n2. 执行并校验结果。' })
    await load()
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { creating.value = false }
}

function category(skill: SkillMetadata): string {
  if (skill.name.includes('web')) return 'NETWORK'
  if (skill.name.includes('code') || skill.name.includes('data')) return 'ANALYSIS'
  if (skill.name.includes('writing') || skill.name.includes('summary')) return 'CONTENT'
  if (skill.name.includes('planning')) return 'WORKFLOW'
  return 'KNOWLEDGE'
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    skills.value = listOf(await request<SkillMetadata[] | { items: SkillMetadata[] }>('/skills'))
  } catch (error) {
    loadError.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

async function openDetail(skill: SkillMetadata): Promise<void> {
  detailOpen.value = true
  detailLoading.value = true
  selected.value = skill
  try {
    selected.value = await request<SkillDetail>(`/skills/${encodeURIComponent(skill.name)}`)
  } catch {
    selected.value = skill
  } finally {
    detailLoading.value = false
  }
}

function goAgents(): void {
  detailOpen.value = false
  navigateTo('agents')
}

onMounted(load)
onActivated(() => { if (!loading.value) void load() })
</script>

<template>
  <div class="page">
    <div class="page-inner">
      <header class="page-header">
        <div class="page-title-group">
          <div class="eyebrow">Progressive Skill Loading</div>
          <h1>Skills</h1>
          <p>Skills 用标准 SKILL.md 描述专业工作流；只有被智能体选中的技能才会按需加载完整指令。</p>
        </div>
        <div class="page-actions">
          <button class="button secondary" type="button" @click="load"><AppIcon name="refresh" :size="16" />重新扫描</button>
          <button class="button secondary" type="button" @click="remoteOpen = true"><AppIcon name="search" :size="16" />远程发现</button>
          <button class="button" type="button" @click="creatorOpen = true"><AppIcon name="plus" :size="16" />创建 Skill</button>
          <button class="button" type="button" @click="goAgents"><AppIcon name="agents" :size="16" />配置智能体</button>
        </div>
      </header>

      <div class="skill-toolbar">
        <div class="skill-search"><AppIcon name="search" :size="17" /><input v-model="query" placeholder="搜索名称或能力…" /></div>
        <div class="skill-count"><strong>{{ skills.length }}</strong><span>已发现</span><i /><strong>{{ skills.filter((skill: any) => skill.valid !== false).length }}</strong><span>有效</span></div>
      </div>

      <LoadingState v-if="loading" :rows="4" />
      <EmptyState v-else-if="loadError" icon="alert" title="无法扫描 Skills" :description="loadError">
        <button class="button secondary" type="button" @click="load">重试</button>
      </EmptyState>
      <EmptyState v-else-if="filtered.length === 0" icon="search" title="没有匹配的 Skill" description="清除搜索条件后再试。" />
      <div v-else class="grid three skill-grid">
        <button v-for="skill in filtered" :key="skill.name" class="skill-card" type="button" @click="openDetail(skill)">
          <header>
            <div class="skill-symbol"><AppIcon :name="skill.name.includes('code') ? 'server' : skill.name.includes('knowledge') ? 'database' : 'sparkles'" :size="20" /></div>
            <StatusBadge :status="(skill as any).valid === false ? 'error' : 'ready'" :label="(skill as any).valid === false ? '无效' : '可用'" />
          </header>
          <span class="skill-category">{{ category(skill) }}</span>
          <h2>{{ displayName(skill) }}</h2>
          <code>{{ skill.name }}</code>
          <p>{{ skill.description }}</p>
          <footer>
            <span><AppIcon name="file" :size="13" /> SKILL.md</span>
            <span v-if="skill.has_scripts"><AppIcon name="activity" :size="13" /> 包含脚本</span>
            <AppIcon class="arrow" name="chevron" :size="15" />
          </footer>
        </button>
      </div>
    </div>

    <ModalDialog :open="detailOpen" :title="selected ? displayName(selected) : 'Skill 详情'" :description="selected?.name" wide @close="detailOpen = false">
      <LoadingState v-if="detailLoading" :rows="3" />
      <div v-else-if="selected" class="skill-detail">
        <div class="detail-facts">
          <div><span>状态</span><StatusBadge :status="selected.valid === false ? 'error' : 'ready'" /></div>
          <div><span>脚本</span><strong>{{ selected.has_scripts ? (selected.scripts_allowed ? '允许执行' : '默认禁用') : '无' }}</strong></div>
          <div><span>引用资料</span><strong>{{ selected.references?.length ?? 0 }}</strong></div>
        </div>
        <section><h3>能力说明</h3><p>{{ selected.description }}</p></section>
        <section v-if="selected.instructions"><h3>SKILL.md 指令</h3><pre>{{ selected.instructions }}</pre></section>
        <section v-if="selected.error" class="detail-error"><h3>校验错误</h3><p>{{ selected.error }}</p></section>
        <div class="safety-note"><AppIcon name="check" :size="16" /><span>Skill 脚本默认禁用；即使开启，也只允许内置白名单脚本在超时与审批策略下运行。</span></div>
      </div>
      <template #footer>
        <button class="button secondary" type="button" @click="detailOpen = false">关闭</button>
        <button class="button" type="button" @click="goAgents">在智能体中启用</button>
      </template>
    </ModalDialog>

    <ModalDialog :open="remoteOpen" title="远程发现 Skills" description="支持 ClawHub 与批准的 GitHub 目录；安装版本固定并经过平台安全验证和本地扫描" wide @close="remoteOpen = false">
      <form class="remote-search" @submit.prevent="searchRemote"><select v-model="remoteSource" class="select"><option value="all">全部来源</option><option value="clawhub">ClawHub</option><option value="github">GitHub 白名单</option></select><input v-model="remoteQuery" class="input" placeholder="例如：browser automation、PDF、数据分析" /><button class="button" :disabled="remoteLoading" type="submit">{{ remoteLoading ? '搜索中…' : '搜索' }}</button></form>
      <div v-if="remoteResults.length" class="remote-results">
        <article v-for="skill in remoteResults" :key="`${skill.source}-${skill.slug || skill.repository}-${skill.path}`">
          <div><strong>{{ skill.name }}</strong><small v-if="skill.source === 'clawhub'">ClawHub · {{ skill.publisher || '未知发布者' }} · {{ skill.version || '安装时锁定版本' }}<template v-if="skill.downloads"> · {{ skill.downloads }} 下载</template></small><small v-else>{{ skill.repository }}@{{ skill.ref }} · {{ skill.path }}</small><p>{{ skill.description }}</p></div>
          <button class="button secondary small" :disabled="installing === skill.name" type="button" @click="openRemoteReview(skill)">查看证据</button>
        </article>
      </div>
      <EmptyState v-else-if="!remoteLoading" icon="search" title="输入能力关键词" description="远程 Skill 在安装后仍需手动绑定到智能体。" />
      <template #footer><button class="button secondary" type="button" @click="remoteOpen = false">关闭</button></template>
    </ModalDialog>

    <ModalDialog :open="reviewOpen" title="审查远程 Skill" description="安装前核对发布者、锁定版本、来源和安全边界" wide @close="reviewOpen = false">
      <LoadingState v-if="reviewLoading" :rows="3" />
      <div v-else-if="reviewSkill" class="skill-detail">
        <div class="detail-facts"><div><span>来源</span><strong>{{ reviewSkill.source === 'clawhub' ? 'ClawHub' : 'GitHub 白名单' }}</strong></div><div><span>发布者</span><strong>{{ reviewSkill.publisher || reviewSkill.repository || '未知' }}</strong></div><div><span>锁定版本</span><strong>{{ reviewSkill.version || reviewSkill.ref || '安装时锁定 commit' }}</strong></div></div>
        <section><h3>{{ reviewSkill.name }}</h3><p>{{ reviewSkill.description }}</p></section>
        <section v-if="reviewSkill.instructions_preview"><h3>发布者说明预览</h3><pre>{{ reviewSkill.instructions_preview }}</pre></section>
        <section><h3>来源与许可</h3><p><a :href="reviewSkill.source_url" target="_blank" rel="noopener noreferrer">打开来源页面</a> · {{ reviewSkill.license || '未声明许可，安装后仍需自行核验使用权' }}</p></section>
        <div class="safety-note"><AppIcon name="alert" :size="16" /><span>ClawHub 自动扫描信号不等同于人工安全担保。Hi-agent 安装时还会执行版本锁定、路径约束、体积限制和本地策略扫描；远程脚本不会进入内置脚本白名单。</span></div>
      </div>
      <template #footer><button class="button secondary" type="button" @click="reviewOpen = false">取消</button><button class="button" type="button" :disabled="reviewLoading || !reviewSkill || installing === reviewSkill?.name" @click="installRemote">{{ installing ? '验证并安装中…' : '确认风险并安装' }}</button></template>
    </ModalDialog>

    <ModalDialog :open="creatorOpen" title="创建 Skill" description="写入严格限制在项目 skills/ 目录；脚本不会自动生成或启用" wide @close="creatorOpen = false">
      <div class="form-grid">
        <div class="field"><label>标准名称</label><input v-model="createForm.name" class="input" placeholder="customer-support" /></div>
        <div class="field"><label>显示名称</label><input v-model="createForm.display_name" class="input" placeholder="客户支持" /></div>
        <div class="field full"><label>触发描述</label><textarea v-model="createForm.description" class="textarea" placeholder="说明能力以及何时应使用该 Skill" /></div>
        <div class="field full"><label>列表简介</label><input v-model="createForm.short_description" class="input" /></div>
        <div class="field full"><label>默认提示</label><input v-model="createForm.default_prompt" class="input" /></div>
        <div class="field full"><label>SKILL.md 指令</label><textarea v-model="createForm.instructions" class="textarea creator-instructions" /></div>
      </div>
      <template #footer><button class="button secondary" type="button" @click="creatorOpen = false">取消</button><button class="button" :disabled="creating" type="button" @click="createSkill">{{ creating ? '校验并创建中…' : '确认创建' }}</button></template>
    </ModalDialog>
  </div>
</template>

<style scoped>
.skill-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 15px; margin-bottom: 16px; }
.skill-search { display: flex; width: min(360px,100%); align-items: center; gap: 8px; padding: 9px 11px; color: var(--muted); background: var(--panel); border: 1px solid var(--line-strong); border-radius: 10px; }
.skill-search:focus-within { border-color: #70a98d; box-shadow: 0 0 0 3px rgba(31,115,84,.07); }
.skill-search input { min-width: 0; flex: 1; background: transparent; border: 0; outline: none; font-size: 11px; }
.skill-count { display: flex; align-items: baseline; gap: 6px; color: var(--muted); }
.skill-count strong { color: var(--green); font-family: 'DM Mono', monospace; font-size: 12px; }
.skill-count span { font-size: 8px; }
.skill-count i { width: 1px; height: 15px; margin: 0 5px; background: var(--line-strong); }
.skill-card { display: flex; min-height: 270px; flex-direction: column; padding: 18px; color: var(--ink); text-align: left; background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius); box-shadow: var(--shadow-sm); cursor: pointer; transition: .18s ease; }
.skill-card:hover { border-color: #c4d5c8; box-shadow: 0 12px 32px rgba(33,39,30,.07); transform: translateY(-2px); }
.skill-card header { display: flex; align-items: center; justify-content: space-between; }
.skill-symbol { display: grid; width: 41px; height: 41px; place-items: center; color: var(--green); background: var(--green-soft); border-radius: 12px; }
.skill-category { margin-top: 15px; color: var(--green); font-family: 'DM Mono', monospace; font-size: 7px; letter-spacing: .1em; }
.skill-card h2 { margin: 7px 0 2px; font-size: 15px; letter-spacing: -.02em; }
.skill-card code { color: var(--faint); font-family: 'DM Mono', monospace; font-size: 8px; }
.skill-card > p { display: -webkit-box; margin: 11px 0; overflow: hidden; color: var(--muted); font-size: 10px; line-height: 1.65; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
.skill-card footer { display: flex; align-items: center; gap: 11px; margin-top: auto; padding-top: 12px; color: var(--muted); font-size: 8px; border-top: 1px solid var(--line); }
.skill-card footer span { display: flex; align-items: center; gap: 4px; }
.skill-card footer .arrow { margin-left: auto; }
.skill-detail { display: grid; gap: 18px; }
.detail-facts { display: grid; grid-template-columns: repeat(3,1fr); gap: 8px; }
.detail-facts > div { display: flex; flex-direction: column; gap: 7px; padding: 11px; background: #f7f9f5; border-radius: 9px; }
.detail-facts span { color: var(--muted); font-size: 8px; }
.detail-facts strong { font-size: 10px; }
.skill-detail section h3 { margin: 0 0 7px; font-size: 11px; }
.skill-detail section p { margin: 0; color: var(--muted); font-size: 10px; line-height: 1.65; }
.skill-detail pre { max-height: 310px; overflow: auto; margin: 0; padding: 13px; color: #39433c; font-family: 'DM Mono', monospace; font-size: 9px; line-height: 1.65; white-space: pre-wrap; background: #f5f7f3; border: 1px solid var(--line); border-radius: 10px; }
.detail-error { padding: 11px; color: var(--red); background: var(--red-soft); border-radius: 9px; }
.safety-note { display: flex; align-items: flex-start; gap: 8px; padding: 11px; color: #4f6f60; font-size: 9px; line-height: 1.55; background: var(--green-soft); border-radius: 9px; }
.safety-note svg { flex: 0 0 auto; }
.remote-search { display: flex; width: 100%; align-items: stretch; gap: 12px; }
.remote-search select { width: 210px; flex: 0 0 210px; }
.remote-search input { min-width: 280px; flex: 1 1 auto; }
.remote-search .button { min-width: 92px; flex: 0 0 auto; white-space: nowrap; }
.remote-results { display: grid; max-height: 430px; gap: 9px; margin-top: 14px; overflow: auto; }
.remote-results article { display: flex; align-items: center; justify-content: space-between; gap: 15px; padding: 13px; border: 1px solid var(--line); border-radius: 10px; }
.remote-results article > div { min-width: 0; }
.remote-results strong,.remote-results small { display: block; }
.remote-results small { margin-top: 3px; color: var(--muted); font: 8px 'DM Mono',monospace; }
.remote-results p { margin: 7px 0 0; color: var(--muted); font-size: 9px; line-height: 1.5; }
.creator-instructions { min-height: 180px; font-family: 'DM Mono',monospace; }
@media (max-width: 700px) { .remote-search { flex-wrap: wrap; } .remote-search select { width: 100%; flex-basis: 100%; } .remote-search input { min-width: 0; } }
@media (max-width: 600px) { .skill-toolbar { align-items: stretch; flex-direction: column; } .skill-count { justify-content: flex-end; } .detail-facts { grid-template-columns: 1fr; } }
</style>
