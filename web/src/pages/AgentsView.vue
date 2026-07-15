<script setup lang="ts">
import { onActivated, onMounted, reactive, ref } from 'vue'
import { formatApiError, jsonBody, listOf, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { notify } from '../notifications'
import type { AgentConfig, KnowledgeBase, McpServerConfig, ModelEndpoint, SkillMetadata } from '../types'

const agents = ref<AgentConfig[]>([])
const models = ref<ModelEndpoint[]>([])
const knowledgeBases = ref<KnowledgeBase[]>([])
const skills = ref<SkillMetadata[]>([])
const mcpServers = ref<McpServerConfig[]>([])
const loading = ref(true)
const loadError = ref('')
const saving = ref(false)
const modalOpen = ref(false)
const editingId = ref<string | null>(null)

const form = reactive({
  name: '',
  description: '',
  system_prompt: '你是一个可靠、审慎的智能助理。请基于可验证的信息回答，并在使用知识库时保留引用。',
  model_endpoint_id: '',
  knowledge_base_id: '',
  enabled_skills: [] as string[],
  enabled_mcp_servers: [] as string[],
  allow_network: false,
})

function resetForm(): void {
  editingId.value = null
  Object.assign(form, {
    name: '',
    description: '',
    system_prompt: '你是一个可靠、审慎的智能助理。请基于可验证的信息回答，并在使用知识库时保留引用。',
    model_endpoint_id: models.value.find((item) => item.is_default)?.id ?? models.value[0]?.id ?? '',
    knowledge_base_id: '',
    enabled_skills: [],
    enabled_mcp_servers: [],
    allow_network: false,
  })
}

function openCreate(): void {
  resetForm()
  modalOpen.value = true
}

function openEdit(agent: AgentConfig): void {
  editingId.value = agent.id
  Object.assign(form, {
    name: agent.name,
    description: agent.description ?? '',
    system_prompt: agent.system_prompt,
    model_endpoint_id: agent.model_endpoint_id ?? '',
    knowledge_base_id: agent.knowledge_base_id ?? '',
    enabled_skills: [...(agent.skills ?? agent.enabled_skills ?? [])],
    enabled_mcp_servers: [...(agent.mcp_servers ?? agent.enabled_mcp_servers ?? [])],
    allow_network: Boolean(agent.tool_policy?.allow_network ?? agent.allow_network),
  })
  modalOpen.value = true
}

function toggleList(list: string[], value: string): void {
  const index = list.indexOf(value)
  if (index >= 0) list.splice(index, 1)
  else list.push(value)
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const [agentData, modelData, kbData, skillData, mcpData] = await Promise.all([
      request<AgentConfig[] | { items: AgentConfig[] }>('/agents'),
      request<ModelEndpoint[] | { items: ModelEndpoint[] }>('/models'),
      request<KnowledgeBase[] | { items: KnowledgeBase[] }>('/knowledge-bases'),
      request<SkillMetadata[] | { items: SkillMetadata[] }>('/skills'),
      request<McpServerConfig[] | { items: McpServerConfig[] }>('/mcp/servers'),
    ])
    agents.value = listOf(agentData)
    models.value = listOf(modelData)
    knowledgeBases.value = listOf(kbData)
    skills.value = listOf(skillData)
    mcpServers.value = listOf(mcpData)
  } catch (error) {
    loadError.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!form.name.trim() || !form.system_prompt.trim()) {
    notify('请填写智能体名称和系统提示词', 'error')
    return
  }
  saving.value = true
  const payload = {
    name: form.name.trim(),
    description: form.description.trim(),
    system_prompt: form.system_prompt.trim(),
    model_endpoint_id: form.model_endpoint_id || null,
    knowledge_base_id: form.knowledge_base_id || null,
    skills: form.enabled_skills,
    mcp_servers: form.enabled_mcp_servers,
    tool_policy: { allow_network: form.allow_network },
    max_tool_loops: 12,
    enabled: true,
  }
  try {
    await request<AgentConfig>(editingId.value ? `/agents/${editingId.value}` : '/agents', {
      method: editingId.value ? 'PATCH' : 'POST',
      ...jsonBody(payload),
    })
    notify(editingId.value ? '智能体配置已更新' : '智能体已创建', 'success')
    modalOpen.value = false
    await load()
  } catch (error) {
    notify(formatApiError(error), 'error')
  } finally {
    saving.value = false
  }
}

async function remove(agent: AgentConfig): Promise<void> {
  if (!window.confirm(`确认删除智能体“${agent.name}”？已有会话快照不会受影响。`)) return
  try {
    await request<void>(`/agents/${agent.id}`, { method: 'DELETE' })
    notify('智能体已删除', 'success')
    await load()
  } catch (error) {
    notify(formatApiError(error), 'error')
  }
}

function modelName(id?: string | null): string {
  const model = models.value.find((item) => item.id === id)
  return model?.name ?? model?.model ?? '未绑定模型'
}

onMounted(load)
onActivated(() => { if (!loading.value) void load() })
</script>

<template>
  <div class="page">
    <div class="page-inner">
      <header class="page-header">
        <div class="page-title-group">
          <div class="eyebrow">Agent Studio</div>
          <h1>智能体</h1>
          <p>将模型、知识库、Skills 与 MCP 工具组合成可复用的运行配置。每次运行都会保存当时的配置快照。</p>
        </div>
        <div class="page-actions">
          <button class="button secondary" type="button" :disabled="loading" @click="load">
            <AppIcon name="refresh" :size="16" />刷新
          </button>
          <button class="button" type="button" @click="openCreate">
            <AppIcon name="plus" :size="16" />新建智能体
          </button>
        </div>
      </header>

      <LoadingState v-if="loading" :rows="4" />
      <EmptyState v-else-if="loadError" icon="alert" title="无法加载智能体" :description="loadError">
        <button class="button secondary" type="button" @click="load">重新连接</button>
      </EmptyState>
      <EmptyState v-else-if="agents.length === 0" icon="agents" title="还没有智能体" description="创建第一个智能体，将模型、知识与工具装配起来。">
        <button class="button" type="button" @click="openCreate"><AppIcon name="plus" :size="16" />新建智能体</button>
      </EmptyState>
      <div v-else class="grid three">
        <article v-for="agent in agents" :key="agent.id" class="card agent-card">
          <div class="card-header">
            <div class="agent-avatar"><AppIcon name="agents" :size="22" /></div>
            <StatusBadge status="enabled" label="可运行" />
          </div>
          <div class="agent-copy">
            <h3>{{ agent.name }}</h3>
            <p>{{ agent.description || '尚未填写智能体说明。' }}</p>
          </div>
          <div class="agent-model">
            <span>MODEL</span>
            <strong>{{ modelName(agent.model_endpoint_id) }}</strong>
          </div>
          <div class="chip-list agent-chips">
            <span v-if="agent.knowledge_base_id" class="chip"><AppIcon name="database" :size="11" /> RAG</span>
            <span v-for="skill in (agent.skills ?? agent.enabled_skills ?? []).slice(0, 2)" :key="skill" class="chip">{{ skill }}</span>
            <span v-if="(agent.skills ?? agent.enabled_skills ?? []).length > 2" class="chip">+{{ (agent.skills ?? agent.enabled_skills ?? []).length - 2 }}</span>
            <span v-if="agent.tool_policy?.allow_network ?? agent.allow_network" class="chip">网络已启用</span>
          </div>
          <footer class="card-meta">
            <span><AppIcon name="sparkles" :size="13" />{{ (agent.skills ?? agent.enabled_skills ?? []).length }} Skills</span>
            <span><AppIcon name="plug" :size="13" />{{ (agent.mcp_servers ?? agent.enabled_mcp_servers ?? []).length }} MCP</span>
            <span class="agent-actions">
              <button class="icon-button" type="button" aria-label="编辑智能体" @click="openEdit(agent)"><AppIcon name="edit" :size="16" /></button>
              <button class="icon-button remove" type="button" aria-label="删除智能体" @click="remove(agent)"><AppIcon name="trash" :size="16" /></button>
            </span>
          </footer>
        </article>
      </div>
    </div>

    <ModalDialog
      :open="modalOpen"
      :title="editingId ? '编辑智能体' : '新建智能体'"
      description="配置会在新 Run 创建时固化为快照"
      wide
      @close="modalOpen = false"
    >
      <form class="form-grid" @submit.prevent="save">
        <div class="field">
          <label for="agent-name">名称</label>
          <input id="agent-name" v-model="form.name" class="input" maxlength="80" placeholder="例如：研究助理" />
        </div>
        <div class="field">
          <label for="agent-model">模型端点</label>
          <select id="agent-model" v-model="form.model_endpoint_id" class="select">
            <option value="">未绑定</option>
            <option v-for="model in models" :key="model.id" :value="model.id">{{ model.name }} · {{ model.model }}</option>
          </select>
        </div>
        <div class="field full">
          <label for="agent-description">说明</label>
          <input id="agent-description" v-model="form.description" class="input" maxlength="240" placeholder="这个智能体擅长什么？" />
        </div>
        <div class="field full">
          <label for="agent-prompt">系统提示词</label>
          <textarea id="agent-prompt" v-model="form.system_prompt" class="textarea prompt-textarea" />
          <span class="field-hint">提示词会与会话上下文、RAG 片段和工具结果一起送入模型。</span>
        </div>
        <div class="field">
          <label for="agent-kb">知识库</label>
          <select id="agent-kb" v-model="form.knowledge_base_id" class="select">
            <option value="">不使用 RAG</option>
            <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">{{ kb.name }}</option>
          </select>
        </div>
        <div class="field">
          <span class="field-label">联网权限</span>
          <div class="switch-row compact-switch">
            <span class="switch-copy"><strong>允许联网工具</strong><span>Web Research 等网络工具才能运行</span></span>
            <button class="switch" :class="{ on: form.allow_network }" type="button" :aria-pressed="form.allow_network" @click="form.allow_network = !form.allow_network" />
          </div>
        </div>
        <div class="field full">
          <span class="field-label">Skills</span>
          <div v-if="skills.length" class="option-grid">
            <label v-for="skill in skills" :key="skill.name" class="check-option" :class="{ selected: form.enabled_skills.includes(skill.name) }">
              <input type="checkbox" :checked="form.enabled_skills.includes(skill.name)" @change="toggleList(form.enabled_skills, skill.name)" />
              <span><strong>{{ skill.display_name || skill.name }}</strong><small>{{ skill.description }}</small></span>
            </label>
          </div>
          <span v-else class="field-hint">暂未发现 Skills。</span>
        </div>
        <div class="field full">
          <span class="field-label">MCP 服务</span>
          <div v-if="mcpServers.length" class="option-grid">
            <label v-for="server in mcpServers" :key="server.id" class="check-option" :class="{ selected: form.enabled_mcp_servers.includes(server.id) }">
              <input type="checkbox" :checked="form.enabled_mcp_servers.includes(server.id)" @change="toggleList(form.enabled_mcp_servers, server.id)" />
              <span><strong>{{ server.name }}</strong><small>{{ server.transport }} · {{ server.enabled ? '已启用' : '已停用' }}</small></span>
            </label>
          </div>
          <span v-else class="field-hint">暂未配置 MCP 服务。</span>
        </div>
      </form>
      <template #footer>
        <button class="button secondary" type="button" @click="modalOpen = false">取消</button>
        <button class="button" type="button" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存配置' }}</button>
      </template>
    </ModalDialog>
  </div>
</template>

<style scoped>
.agent-card { min-height: 275px; display: flex; flex-direction: column; }
.agent-avatar { display: grid; width: 44px; height: 44px; place-items: center; color: #225f49; background: linear-gradient(145deg, #dceee4, #f0f7e9); border: 1px solid #d2e6d8; border-radius: 13px; }
.agent-copy { margin-top: 17px; }
.agent-copy h3 { margin: 0; font-size: 16px; letter-spacing: -.025em; }
.agent-copy p { display: -webkit-box; min-height: 35px; margin: 6px 0 0; overflow: hidden; color: var(--muted); font-size: 11px; line-height: 1.6; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.agent-model { display: flex; align-items: center; gap: 9px; margin-top: 15px; padding: 9px 10px; background: #f7f8f4; border-radius: 9px; }
.agent-model span { color: var(--faint); font-family: 'DM Mono', monospace; font-size: 7px; letter-spacing: .08em; }
.agent-model strong { overflow: hidden; font-family: 'DM Mono', monospace; font-size: 9px; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.agent-chips { min-height: 24px; margin-top: 12px; }
.card-meta { margin-top: auto; align-items: center; }
.agent-actions { margin-left: auto; }
.agent-actions .icon-button { width: 29px; height: 29px; }
.agent-actions .remove:hover { color: var(--red); background: var(--red-soft); }
.prompt-textarea { min-height: 135px; }
.compact-switch { min-height: 39px; padding: 0 3px; }
.option-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.check-option { display: flex; min-width: 0; align-items: flex-start; gap: 9px; padding: 10px; background: #fafbf8; border: 1px solid var(--line); border-radius: 9px; cursor: pointer; transition: .15s; }
.check-option:hover { border-color: #b9cdbf; }
.check-option.selected { background: var(--green-soft); border-color: #bcdac8; }
.check-option input { margin: 2px 0 0; accent-color: var(--green); }
.check-option span { display: flex; min-width: 0; flex-direction: column; }
.check-option strong { font-size: 10px; }
.check-option small { display: -webkit-box; margin-top: 3px; overflow: hidden; color: var(--muted); font-size: 8px; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
@media (max-width: 560px) { .option-grid { grid-template-columns: 1fr; } }
</style>
