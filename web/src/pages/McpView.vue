<script setup lang="ts">
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { formatApiError, jsonBody, listOf, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { notify } from '../notifications'
import type { McpServerConfig, McpTool } from '../types'

interface ProbeResponse { status: string; tools: McpTool[]; error?: string | null }

const servers = ref<McpServerConfig[]>([])
const loading = ref(true)
const loadError = ref('')
const modalOpen = ref(false)
const saving = ref(false)
const editingId = ref<string | null>(null)
const probingId = ref<string | null>(null)
const probeResults = reactive<Record<string, ProbeResponse>>({})
const expandedId = ref<string | null>(null)

const form = reactive({
  name: '',
  transport: 'stdio' as 'stdio' | 'streamable_http',
  command: '',
  argsText: '',
  url: '',
  enabled: false,
  allow_remote: false,
})

const transportHint = computed(() => form.transport === 'stdio'
  ? '命令以参数数组直接启动，不会经过 shell。'
  : '非本机地址必须使用 HTTPS，且需要明确允许远程连接。')

function openCreate(): void {
  editingId.value = null
  Object.assign(form, { name: '', transport: 'stdio', command: '', argsText: '', url: '', enabled: false, allow_remote: false })
  modalOpen.value = true
}

function openEdit(server: McpServerConfig): void {
  editingId.value = server.id
  Object.assign(form, {
    name: server.name,
    transport: server.transport,
    command: server.command ?? '',
    argsText: (server.args ?? []).join('\n'),
    url: server.url ?? '',
    enabled: server.enabled,
    allow_remote: Boolean(server.allow_remote),
  })
  modalOpen.value = true
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const data = await request<McpServerConfig[] | { items: McpServerConfig[] }>('/mcp/servers')
    servers.value = listOf(data)
  } catch (error) {
    loadError.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!form.name.trim() || (form.transport === 'stdio' ? !form.command.trim() : !form.url.trim())) {
    notify('请填写名称及传输连接信息', 'error')
    return
  }
  saving.value = true
  const payload: Record<string, unknown> = {
    name: form.name.trim(),
    command: form.transport === 'stdio' ? form.command.trim() : null,
    args: form.transport === 'stdio' ? form.argsText.split('\n').map((value) => value.trim()).filter(Boolean) : [],
    url: form.transport === 'streamable_http' ? form.url.trim() : null,
    env_refs: {},
    enabled: form.enabled,
    allow_remote: form.allow_remote,
  }
  if (!editingId.value) payload.transport = form.transport
  try {
    await request<McpServerConfig>(editingId.value ? `/mcp/servers/${editingId.value}` : '/mcp/servers', {
      method: editingId.value ? 'PATCH' : 'POST',
      ...jsonBody(payload),
    })
    notify(editingId.value ? 'MCP 配置已更新' : 'MCP 服务已添加', 'success')
    modalOpen.value = false
    await load()
  } catch (error) {
    notify(formatApiError(error), 'error')
  } finally {
    saving.value = false
  }
}

async function toggle(server: McpServerConfig): Promise<void> {
  try {
    await request<McpServerConfig>(`/mcp/servers/${server.id}`, { method: 'PATCH', ...jsonBody({ enabled: !server.enabled }) })
    notify(server.enabled ? 'MCP 服务已停用' : 'MCP 服务已启用', 'success')
    await load()
  } catch (error) {
    notify(formatApiError(error), 'error')
  }
}

async function probe(server: McpServerConfig): Promise<void> {
  probingId.value = server.id
  expandedId.value = server.id
  try {
    const data = await request<ProbeResponse>(`/mcp/servers/${server.id}/probe`, { method: 'POST' })
    probeResults[server.id] = data
    if (['online', 'connected', 'healthy'].includes(data.status)) notify(`已发现 ${data.tools.length} 个工具`, 'success')
    else notify(data.error || 'MCP 服务探测失败', 'error')
    await load()
  } catch (error) {
    probeResults[server.id] = { status: 'error', tools: [], error: formatApiError(error) }
    notify(formatApiError(error), 'error')
  } finally {
    probingId.value = null
  }
}

async function remove(server: McpServerConfig): Promise<void> {
  if (!window.confirm(`确认删除 MCP 服务“${server.name}”？`)) return
  try {
    await request<void>(`/mcp/servers/${server.id}`, { method: 'DELETE' })
    notify('MCP 服务已删除', 'success')
    await load()
  } catch (error) {
    notify(formatApiError(error), 'error')
  }
}

function riskLabel(risk?: string): string {
  return ({ read: '只读', network: '联网', write: '写入', execute: '执行' } as Record<string, string>)[risk ?? 'read'] ?? risk ?? '只读'
}

onMounted(load)
onActivated(() => { if (!loading.value) void load() })
</script>

<template>
  <div class="page">
    <div class="page-inner">
      <header class="page-header">
        <div class="page-title-group">
          <div class="eyebrow">Model Context Protocol</div>
          <h1>MCP 服务</h1>
          <p>连接标准 MCP 工具服务。只读工具可自动执行，写入与执行类工具始终需要人工审批。</p>
        </div>
        <div class="page-actions">
          <button class="button secondary" type="button" @click="load"><AppIcon name="refresh" :size="16" />刷新</button>
          <button class="button" type="button" @click="openCreate"><AppIcon name="plus" :size="16" />添加服务</button>
        </div>
      </header>

      <section class="security-banner">
        <span><AppIcon name="check" :size="17" /></span>
        <div><strong>安全边界已启用</strong><p>stdio 使用参数数组直启；远程 HTTP 默认关闭；密钥只通过环境变量引用。</p></div>
      </section>

      <LoadingState v-if="loading" :rows="4" />
      <EmptyState v-else-if="loadError" icon="alert" title="无法加载 MCP 配置" :description="loadError">
        <button class="button secondary" type="button" @click="load">重新连接</button>
      </EmptyState>
      <EmptyState v-else-if="servers.length === 0" icon="plug" title="尚未连接 MCP 服务" description="可先添加项目内置的只读 workspace 服务，或连接兼容的 Streamable HTTP 服务。">
        <button class="button" type="button" @click="openCreate"><AppIcon name="plus" :size="16" />添加服务</button>
      </EmptyState>
      <div v-else class="server-list">
        <article v-for="server in servers" :key="server.id" class="panel server-card">
          <div class="server-main">
            <div class="server-icon"><AppIcon name="plug" :size="21" /></div>
            <div class="server-copy">
              <div class="server-title"><h2>{{ server.name }}</h2><StatusBadge :status="probeResults[server.id]?.status || server.status || (server.enabled ? 'enabled' : 'disabled')" /></div>
              <code>{{ server.transport === 'stdio' ? [server.command, ...(server.args ?? [])].filter(Boolean).join(' ') : server.url }}</code>
              <div class="server-tags"><span>{{ server.transport === 'stdio' ? 'STDIO' : 'STREAMABLE HTTP' }}</span><span v-if="server.allow_remote">REMOTE ALLOWED</span><span v-else>LOCAL ONLY</span></div>
            </div>
            <div class="server-actions">
              <button class="button secondary small" type="button" :disabled="probingId === server.id" @click="probe(server)">
                <span v-if="probingId === server.id" class="mini-spinner" />
                <AppIcon v-else name="activity" :size="14" />{{ probingId === server.id ? '探测中' : '探测工具' }}
              </button>
              <button class="switch" :class="{ on: server.enabled }" type="button" :aria-label="server.enabled ? '停用服务' : '启用服务'" :aria-pressed="server.enabled" @click="toggle(server)" />
              <button class="icon-button" type="button" aria-label="编辑服务" @click="openEdit(server)"><AppIcon name="edit" :size="16" /></button>
              <button class="icon-button remove" type="button" aria-label="删除服务" @click="remove(server)"><AppIcon name="trash" :size="16" /></button>
            </div>
          </div>

          <div v-if="expandedId === server.id" class="tool-panel">
            <div class="tool-panel-head"><span>发现的工具</span><button class="icon-button" type="button" aria-label="收起" @click="expandedId = null"><AppIcon name="close" :size="15" /></button></div>
            <p v-if="probeResults[server.id]?.error" class="probe-error"><AppIcon name="alert" :size="15" />{{ probeResults[server.id]?.error }}</p>
            <div v-else-if="probeResults[server.id]?.tools.length" class="tool-grid">
              <div v-for="tool in probeResults[server.id].tools" :key="tool.name" class="tool-item">
                <div><strong>mcp.{{ server.name }}.{{ tool.name }}</strong><p>{{ tool.description || '无工具说明' }}</p></div>
                <span :class="`risk-${tool.risk || 'read'}`">{{ riskLabel(tool.risk) }}</span>
              </div>
            </div>
            <p v-else class="no-tools">探测成功后，工具清单会显示在这里。</p>
          </div>
        </article>
      </div>
    </div>

    <ModalDialog :open="modalOpen" :title="editingId ? '编辑 MCP 服务' : '添加 MCP 服务'" :description="transportHint" @close="modalOpen = false">
      <form class="form-grid" @submit.prevent="save">
        <div class="field full"><label for="mcp-name">服务名称</label><input id="mcp-name" v-model="form.name" class="input" maxlength="120" placeholder="例如：workspace" /></div>
        <div class="field full">
          <span class="field-label">传输方式</span>
          <div class="segment-control">
            <button type="button" :disabled="Boolean(editingId)" :class="{ active: form.transport === 'stdio' }" @click="form.transport = 'stdio'">stdio</button>
            <button type="button" :disabled="Boolean(editingId)" :class="{ active: form.transport === 'streamable_http' }" @click="form.transport = 'streamable_http'">Streamable HTTP</button>
          </div>
        </div>
        <template v-if="form.transport === 'stdio'">
          <div class="field full"><label for="mcp-command">可执行命令</label><input id="mcp-command" v-model="form.command" class="input mono" placeholder="例如：uv" /><span class="field-hint">仅填写可执行文件，不支持管道、重定向或 shell 表达式。</span></div>
          <div class="field full"><label for="mcp-args">参数（每行一个）</label><textarea id="mcp-args" v-model="form.argsText" class="textarea mono" placeholder="run&#10;python&#10;mcp_servers/workspace_server.py" /></div>
        </template>
        <template v-else>
          <div class="field full"><label for="mcp-url">服务地址</label><input id="mcp-url" v-model="form.url" class="input mono" type="url" placeholder="https://mcp.example.com/mcp" /></div>
          <div class="field full"><div class="switch-row"><span class="switch-copy"><strong>允许远程地址</strong><span>非 localhost 地址需要 HTTPS，并明确开启此项</span></span><button class="switch" :class="{ on: form.allow_remote }" type="button" @click="form.allow_remote = !form.allow_remote" /></div></div>
        </template>
        <div class="field full"><div class="switch-row"><span class="switch-copy"><strong>立即启用</strong><span>启用后才允许 Agent 连接这个服务</span></span><button class="switch" :class="{ on: form.enabled }" type="button" @click="form.enabled = !form.enabled" /></div></div>
      </form>
      <template #footer>
        <button class="button secondary" type="button" @click="modalOpen = false">取消</button>
        <button class="button" type="button" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存服务' }}</button>
      </template>
    </ModalDialog>
  </div>
</template>

<style scoped>
.security-banner { display: flex; align-items: center; gap: 11px; margin: -7px 0 18px; padding: 12px 14px; color: #275a46; background: linear-gradient(90deg, #e8f3ec, #f2f7e9); border: 1px solid #d8eadf; border-radius: 12px; }
.security-banner > span { display: grid; width: 30px; height: 30px; flex: 0 0 30px; place-items: center; background: rgba(255,255,255,.65); border-radius: 9px; }
.security-banner strong { font-size: 10px; }
.security-banner p { margin: 3px 0 0; color: #608071; font-size: 9px; }
.server-list { display: grid; gap: 10px; }
.server-card { overflow: hidden; }
.server-main { display: flex; align-items: center; gap: 14px; padding: 16px; }
.server-icon { display: grid; width: 44px; height: 44px; flex: 0 0 44px; place-items: center; color: var(--green); background: var(--green-soft); border-radius: 12px; }
.server-copy { min-width: 0; flex: 1; }
.server-title { display: flex; align-items: center; gap: 9px; }
.server-title h2 { margin: 0; font-size: 13px; }
.server-copy code { display: block; max-width: 640px; margin-top: 5px; overflow: hidden; color: var(--muted); font-family: 'DM Mono', monospace; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.server-tags { display: flex; gap: 5px; margin-top: 8px; }
.server-tags span { padding: 3px 6px; color: #6d776e; font-family: 'DM Mono', monospace; font-size: 6px; letter-spacing: .07em; background: #f1f3ee; border-radius: 5px; }
.server-actions { display: flex; align-items: center; gap: 5px; }
.server-actions .remove:hover { color: var(--red); background: var(--red-soft); }
.mini-spinner { width: 12px; height: 12px; border: 1.5px solid #ccd7cf; border-top-color: var(--green); border-radius: 50%; animation: spin .7s linear infinite; }
.tool-panel { padding: 0 16px 15px 74px; border-top: 1px solid var(--line); }
.tool-panel-head { display: flex; align-items: center; justify-content: space-between; padding: 9px 0 7px; color: var(--muted); font-size: 9px; }
.tool-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 7px; }
.tool-item { display: flex; min-width: 0; align-items: flex-start; justify-content: space-between; gap: 10px; padding: 10px; background: #f8faf6; border: 1px solid var(--line); border-radius: 9px; }
.tool-item > div { min-width: 0; }
.tool-item strong { display: block; overflow: hidden; font-family: 'DM Mono', monospace; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.tool-item p { display: -webkit-box; margin: 4px 0 0; overflow: hidden; color: var(--muted); font-size: 8px; line-height: 1.45; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.tool-item > span { padding: 3px 6px; font-size: 7px; border-radius: 5px; white-space: nowrap; }
.risk-read { color: var(--green); background: var(--green-soft); }
.risk-network { color: var(--blue); background: var(--blue-soft); }
.risk-write, .risk-execute { color: var(--red); background: var(--red-soft); }
.probe-error { display: flex; align-items: center; gap: 7px; color: var(--red); font-size: 9px; }
.no-tools { color: var(--faint); font-size: 9px; }
.segment-control { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding: 4px; background: #f0f2ed; border-radius: 10px; }
.segment-control button { padding: 8px; color: var(--muted); font-size: 10px; background: transparent; border: 0; border-radius: 7px; cursor: pointer; }
.segment-control button.active { color: var(--ink); font-weight: 650; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
@media (max-width: 700px) { .server-main { align-items: flex-start; flex-wrap: wrap; } .server-copy { min-width: calc(100% - 60px); } .server-actions { width: 100%; justify-content: flex-end; padding-left: 58px; } .tool-panel { padding-left: 16px; } .tool-grid { grid-template-columns: 1fr; } }
</style>
