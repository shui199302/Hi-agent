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
import type { AgentConfig, KnowledgeBase, Project, SessionItem } from '../types'

interface RunItem { id: string; agent_id: string; status: string; input: string; created_at: string }

const projects = ref<Project[]>([])
const agents = ref<AgentConfig[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const sessions = ref<SessionItem[]>([])
const runs = ref<RunItem[]>([])
const loading = ref(true)
const selectedId = ref('')
const modalOpen = ref(false)
const editingId = ref('')
const saving = ref(false)
const assignOpen = ref(false)
const assigning = ref(false)
const selectedAgentIds = ref<string[]>([])
const form = reactive({ name: '', description: '' })
const selected = computed(() => projects.value.find((item) => item.id === selectedId.value) ?? null)
const projectAgents = computed(() => agents.value.filter((item) => item.project_id === selectedId.value))
const projectKnowledge = computed(() => knowledgeBases.value.filter((item) => item.project_id === selectedId.value))
const projectSessions = computed(() => sessions.value.filter((item) => projectAgents.value.some((agent) => agent.id === item.agent_id)))
const recentRuns = computed(() => runs.value.filter((item) => projectAgents.value.some((agent) => agent.id === item.agent_id)).slice(0, 5))
const assignableAgents = computed(() => agents.value.filter((item) => item.project_id !== selectedId.value))

async function load(): Promise<void> {
  loading.value = true
  try {
    const [projectData, agentData, kbData, sessionData, runData] = await Promise.all([request<Project[]>('/projects'), request<AgentConfig[]>('/agents'), request<KnowledgeBase[]>('/knowledge-bases'), request<SessionItem[]>('/sessions'), request<RunItem[]>('/runs')])
    projects.value = listOf(projectData); agents.value = listOf(agentData); knowledgeBases.value = listOf(kbData); sessions.value = listOf(sessionData); runs.value = listOf(runData)
    if (!projects.value.some((item) => item.id === selectedId.value)) selectedId.value = projects.value[0]?.id ?? ''
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { loading.value = false }
}

function openCreate(): void { editingId.value = ''; Object.assign(form, { name: '', description: '' }); modalOpen.value = true }
function openEdit(project: Project): void { editingId.value = project.id; Object.assign(form, { name: project.name, description: project.description }); modalOpen.value = true }
async function save(): Promise<void> {
  if (!form.name.trim()) return
  saving.value = true
  try {
    const project = await request<Project>(editingId.value ? `/projects/${editingId.value}` : '/projects', { method: editingId.value ? 'PATCH' : 'POST', ...jsonBody({ name: form.name.trim(), description: form.description.trim() }) })
    modalOpen.value = false; selectedId.value = project.id; notify(editingId.value ? '项目已更新' : '项目已创建', 'success'); await load()
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { saving.value = false }
}
async function toggleArchive(project: Project): Promise<void> {
  const status = project.status === 'active' ? 'archived' : 'active'
  try { await request(`/projects/${project.id}`, { method: 'PATCH', ...jsonBody({ status }) }); notify(status === 'archived' ? '项目已归档' : '项目已恢复', 'success'); await load() }
  catch (error) { notify(formatApiError(error), 'error') }
}
function openAssign(): void { selectedAgentIds.value = []; assignOpen.value = true }
function hasForeignKnowledge(agent: AgentConfig): boolean {
  if (!agent.knowledge_base_id) return false
  return knowledgeBases.value.find((item) => item.id === agent.knowledge_base_id)?.project_id !== selectedId.value
}
function toggleAgent(id: string): void {
  const index = selectedAgentIds.value.indexOf(id)
  if (index >= 0) selectedAgentIds.value.splice(index, 1)
  else selectedAgentIds.value.push(id)
}
async function assignAgents(): Promise<void> {
  if (!selected.value || !selectedAgentIds.value.length) return
  assigning.value = true
  try {
    const moved = await request<AgentConfig[]>(`/projects/${selected.value.id}/agents:assign`, { method: 'POST', ...jsonBody({ agent_ids: selectedAgentIds.value }) })
    assignOpen.value = false
    notify(`已将 ${moved.length} 个智能体加入“${selected.value.name}”`, 'success')
    await load()
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { assigning.value = false }
}
function projectName(id: string): string { return projects.value.find((item) => item.id === id)?.name ?? '未知项目' }
function goAgents(): void { navigateTo('agents') }
function goKnowledge(id: string): void { navigateTo(`knowledge/${encodeURIComponent(id)}`) }

onMounted(load)
onActivated(() => { if (!loading.value) void load() })
</script>

<template>
  <div class="page">
    <div class="page-inner">
      <header class="page-header"><div class="page-title-group"><div class="eyebrow">Project workspace</div><h1>项目</h1><p>用项目统一管理智能体、知识库及其会话和运行记录；资源在用户之间完全隔离。</p></div><div class="page-actions"><button class="button secondary" @click="load"><AppIcon name="refresh" :size="15" />刷新</button><button class="button" @click="openCreate"><AppIcon name="plus" :size="15" />新建项目</button></div></header>
      <LoadingState v-if="loading" :rows="4" />
      <EmptyState v-else-if="!projects.length" icon="file" title="还没有项目" description="创建项目后再添加智能体和知识库。"><button class="button" @click="openCreate">新建项目</button></EmptyState>
      <div v-else class="project-layout">
        <aside class="project-list"><button v-for="project in projects" :key="project.id" :class="{ active: selectedId === project.id }" @click="selectedId = project.id"><span><strong>{{ project.name }}</strong><small>{{ project.agent_count }} 智能体 · {{ project.knowledge_base_count }} 知识库</small></span><StatusBadge :status="project.status === 'active' ? 'ready' : 'disabled'" :label="project.status === 'active' ? '运行中' : '已归档'" /></button></aside>
        <section v-if="selected" class="panel panel-padded project-detail">
          <div class="section-heading"><div><h2>{{ selected.name }}</h2><p>{{ selected.description || '暂无项目说明' }}</p></div><div class="heading-actions"><button v-if="selected.status === 'active'" class="button small" @click="openAssign">批量添加智能体</button><button class="button secondary small" @click="openEdit(selected)">编辑</button><button class="button secondary small" @click="toggleArchive(selected)">{{ selected.status === 'active' ? '归档' : '恢复' }}</button></div></div>
          <div class="stats-grid"><article><strong>{{ selected.agent_count }}</strong><span>智能体</span></article><article><strong>{{ selected.knowledge_base_count }}</strong><span>知识库</span></article><article><strong>{{ selected.session_count }}</strong><span>会话</span></article><article><strong>{{ selected.run_count }}</strong><span>Run</span></article></div>
          <div class="project-resources"><section><h3>智能体</h3><button v-for="agent in projectAgents" :key="agent.id" @click="goAgents"><AppIcon name="agents" :size="16" /><span><strong>{{ agent.name }}</strong><small>{{ agent.description || '无说明' }}</small></span></button><p v-if="!projectAgents.length">暂无智能体</p></section><section><h3>知识库</h3><button v-for="kb in projectKnowledge" :key="kb.id" @click="goKnowledge(kb.id)"><AppIcon name="database" :size="16" /><span><strong>{{ kb.name }}</strong><small>{{ kb.document_count || 0 }} 个文档</small></span></button><p v-if="!projectKnowledge.length">暂无知识库</p></section></div>
          <section class="recent-activity"><h3>最近运行</h3><article v-for="run in recentRuns" :key="run.id"><StatusBadge :status="run.status" /><span><strong>{{ projectAgents.find((agent) => agent.id === run.agent_id)?.name }}</strong><small>{{ run.input.slice(0, 80) }} · {{ new Date(run.created_at).toLocaleString('zh-CN') }}</small></span></article><p v-if="!recentRuns.length">暂无运行记录；当前项目共有 {{ projectSessions.length }} 个会话。</p></section>
        </section>
      </div>
    </div>
    <ModalDialog :open="modalOpen" :title="editingId ? '编辑项目' : '新建项目'" description="项目名称在当前用户下唯一" @close="modalOpen=false"><form class="form-grid" @submit.prevent="save"><div class="field full"><label>项目名称</label><input v-model="form.name" class="input" maxlength="120" /></div><div class="field full"><label>项目说明</label><textarea v-model="form.description" class="textarea" maxlength="4000" /></div></form><template #footer><button class="button secondary" @click="modalOpen=false">取消</button><button class="button" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存' }}</button></template></ModalDialog>
    <ModalDialog :open="assignOpen" title="批量添加智能体" :description="`将多个智能体迁移到“${selected?.name || ''}”；历史会话和 Run 仍保留原项目归属`" wide @close="assignOpen=false"><EmptyState v-if="!assignableAgents.length" icon="agents" title="没有可迁移的智能体" description="当前用户的全部智能体已经在这个项目中。" /><div v-else class="agent-select-grid"><label v-for="agent in assignableAgents" :key="agent.id" :class="{ selected: selectedAgentIds.includes(agent.id), disabled: hasForeignKnowledge(agent) }"><input type="checkbox" :disabled="hasForeignKnowledge(agent)" :checked="selectedAgentIds.includes(agent.id)" @change="toggleAgent(agent.id)" /><span><strong>{{ agent.name }}</strong><small>当前：{{ projectName(agent.project_id) }}<template v-if="hasForeignKnowledge(agent)"> · 请先解绑其他项目知识库</template></small></span></label></div><template #footer><span class="selection-count">已选择 {{ selectedAgentIds.length }} 个</span><button class="button secondary" @click="assignOpen=false">取消</button><button class="button" :disabled="assigning || !selectedAgentIds.length" @click="assignAgents">{{ assigning ? '迁移中…' : '确认批量添加' }}</button></template></ModalDialog>
  </div>
</template>

<style scoped>
.project-layout{display:grid;grid-template-columns:280px 1fr;gap:16px}.project-list{display:grid;align-content:start;gap:8px}.project-list>button{display:flex;justify-content:space-between;gap:10px;padding:14px;text-align:left;background:var(--panel);border:1px solid var(--line);border-radius:11px}.project-list>button.active{border-color:#76a88d;box-shadow:0 0 0 3px rgba(31,115,84,.08)}.project-list span,.project-resources span{display:grid;gap:4px}.project-list small,.project-resources small{color:var(--muted)}.stats-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:18px 0}.stats-grid article{display:grid;gap:5px;padding:14px;background:#f6f8f4;border-radius:10px}.stats-grid strong{font-size:22px;color:var(--green)}.project-resources{display:grid;grid-template-columns:1fr 1fr;gap:20px}.project-resources section{display:grid;align-content:start;gap:8px}.project-resources button{display:flex;gap:10px;padding:11px;text-align:left;background:white;border:1px solid var(--line);border-radius:9px}@media(max-width:800px){.project-layout,.project-resources{grid-template-columns:1fr}.stats-grid{grid-template-columns:repeat(2,1fr)}}
.recent-activity{display:grid;gap:8px;margin-top:22px}.recent-activity article{display:flex;align-items:center;gap:10px;padding:10px;border-top:1px solid var(--line)}.recent-activity span{display:grid;gap:3px}.recent-activity small{color:var(--muted)}
.agent-select-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.agent-select-grid label{display:flex;gap:10px;padding:13px;border:1px solid var(--line);border-radius:10px}.agent-select-grid label.selected{border-color:#76a88d;background:var(--green-soft)}.agent-select-grid label.disabled{opacity:.55}.agent-select-grid span{display:grid;gap:4px}.agent-select-grid small,.selection-count{color:var(--muted);font-size:9px}.selection-count{margin-right:auto}@media(max-width:650px){.agent-select-grid{grid-template-columns:1fr}}
</style>
