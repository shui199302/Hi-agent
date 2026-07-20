<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { formatApiError, jsonBody, listOf, openRunEventStream, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { notify } from '../notifications'
import { navigateTo } from '../navigation'
import type { AgentConfig, Approval, ArtifactItem, ChatMessage, Citation, Project, RunEvent, RunResponse, SessionItem } from '../types'

interface SessionDetail extends SessionItem { messages: ChatMessage[] }
interface RunRecord {
  id: string
  session_id: string
  status: string
  input: string
  output: string
  created_at: string
}
interface ApprovalRecord extends Approval { status: string }

const sessions = ref<SessionItem[]>([])
const agents = ref<AgentConfig[]>([])
const projects = ref<Project[]>([])
const projectFilter = ref('all')
const selectedId = ref('')
const messages = ref<ChatMessage[]>([])
const loading = ref(true)
const sessionLoading = ref(false)
const loadError = ref('')
const prompt = ref('')
const running = ref(false)
const runId = ref('')
const runStatus = ref('idle')
const streamState = ref<'idle' | 'connecting' | 'open' | 'reconnecting'>('idle')
const events = ref<RunEvent[]>([])
const currentCitations = ref<Citation[]>([])
const currentArtifacts = ref<ArtifactItem[]>([])
const approval = ref<Approval | null>(null)
const decidingApproval = ref(false)
const createOpen = ref(false)
const creating = ref(false)
const assistantDraftId = ref('')
const messagesPane = ref<HTMLElement | null>(null)
const promptBox = ref<HTMLTextAreaElement | null>(null)
const createForm = reactive({ title: '新对话', agent_id: '' })
let source: EventSource | null = null

const selected = computed(() => sessions.value.find((item) => item.id === selectedId.value) ?? null)
const selectedAgent = computed(() => agents.value.find((item) => item.id === selected.value?.agent_id) ?? null)
const canSend = computed(() => Boolean(selectedId.value && prompt.value.trim() && !running.value))
const timelineEmpty = computed(() => events.value.length === 0)
const filteredAgents = computed(() => projectFilter.value === 'all' ? agents.value : agents.value.filter((item) => item.project_id === projectFilter.value))
const filteredSessions = computed(() => projectFilter.value === 'all' ? sessions.value : sessions.value.filter((item) => filteredAgents.value.some((agent) => agent.id === item.agent_id)))

watch(projectFilter, () => {
  if (running.value) return
  createForm.agent_id = filteredAgents.value[0]?.id ?? ''
  if (!filteredSessions.value.some((item) => item.id === selectedId.value)) {
    selectedId.value = filteredSessions.value[0]?.id ?? ''
    messages.value = []
    if (selectedId.value) void loadSession(selectedId.value)
  }
})

const nodeLabels: Record<string, string> = {
  load_session: '加载会话', retrieve: '知识检索', draft_plan: '生成实施方案', review_plan: '方案 Review',
  model_decision: '模型推理', tool_loop: '工具循环', resume_approval: '恢复工具审批',
  resume_plan_review: '恢复方案审批', finalize: '整理引用', persist: '持久化', pause: '等待审批',
}

function agentName(id?: string | null): string {
  return agents.value.find((item) => item.id === id)?.name ?? '未知智能体'
}

function relativeDate(value?: string): string {
  if (!value) return ''
  const diff = Date.now() - new Date(value).getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(value))
}

function bytes(value = 0): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function eventTitle(event: RunEvent): string {
  const data = event.data
  if (event.type === 'node_started') return `${nodeLabels[String(data.node)] ?? data.node ?? '节点'}开始`
  if (event.type === 'node_finished') return `${nodeLabels[String(data.node)] ?? data.node ?? '节点'}完成`
  if (event.type === 'retrieval') return `检索到 ${Array.isArray(data.items) ? data.items.length : 0} 个片段`
  if (event.type === 'model_delta') return '模型正在生成'
  if (event.type === 'tool_call') return `调用 ${data.tool ?? '工具'}`
  if (event.type === 'tool_result') return `${data.tool ?? '工具'} 返回结果`
  if (event.type === 'approval_required') return '工具等待审批'
  if (event.type === 'plan_drafted') return '实施方案已生成'
  if (event.type === 'plan_reviewed') return `方案 Review：${data.decision === 'pass' ? '通过' : '需调整'}`
  if (event.type === 'plan_review_required') return '实施方案等待人工审批'
  if (event.type === 'plan_approved') return '实施方案已批准'
  if (event.type === 'plan_rejected') return '实施方案已拒绝'
  if (event.type === 'citation') return `引用 ${data.filename ?? '知识库文档'}`
  if (event.type === 'completed') return '运行完成'
  if (event.type === 'failed') return `运行失败：${data.code ?? 'ERROR'}`
  if (event.type === 'cancelled') return '运行已取消'
  if (event.type === 'mcp_error') return 'MCP 服务异常'
  return event.type
}

function eventTone(event: RunEvent): string {
  if (['failed', 'mcp_error'].includes(event.type)) return 'error'
  if (['completed'].includes(event.type)) return 'success'
  if (['approval_required', 'plan_review_required'].includes(event.type)) return 'approval'
  if (['model_delta'].includes(event.type)) return 'stream'
  return 'normal'
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const [sessionData, agentData, projectData] = await Promise.all([
      request<SessionItem[] | { items: SessionItem[] }>('/sessions'),
      request<AgentConfig[] | { items: AgentConfig[] }>('/agents'),
      request<Project[]>('/projects'),
    ])
    sessions.value = listOf(sessionData)
    agents.value = listOf(agentData).filter((item) => item.enabled !== false && item.agent_type !== 'digital_human')
    projects.value = listOf(projectData)
    if (!sessions.value.some((item) => item.id === selectedId.value)) selectedId.value = sessions.value[0]?.id ?? ''
    if (selectedId.value) await loadSession(selectedId.value)
  } catch (error) {
    loadError.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

async function loadSession(id: string): Promise<void> {
  if (running.value && id === selectedId.value) return
  if (running.value && id !== selectedId.value) {
    notify('请等待当前运行结束，或先取消运行', 'info')
    return
  }
  selectedId.value = id
  sessionLoading.value = true
  events.value = []
  currentCitations.value = []
  currentArtifacts.value = []
  approval.value = null
  try {
    const detail = await request<SessionDetail>(`/sessions/${id}`)
    messages.value = detail.messages ?? []
    await recoverActiveRun(id)
    await scrollToBottom()
  } catch (error) {
    notify(formatApiError(error), 'error')
  } finally {
    sessionLoading.value = false
  }
}

function connectRunStream(eventsUrl: string): void {
  streamState.value = 'connecting'
  source?.close()
  source = openRunEventStream(eventsUrl, {
    onEvent: handleRunEvent,
    onOpen: () => {
      streamState.value = 'open'
      runStatus.value = runStatus.value === 'queued' ? 'running' : runStatus.value
    },
    onConnectionError: () => { if (running.value) streamState.value = 'reconnecting' },
  })
}

async function recoverActiveRun(sessionId: string): Promise<void> {
  if (running.value) return
  const runs = listOf(await request<RunRecord[] | { items: RunRecord[] }>(`/runs?session_id=${encodeURIComponent(sessionId)}`))
  const activeRun = runs.find((item) => ['queued', 'running', 'waiting_approval'].includes(item.status))
  if (!activeRun) return

  runId.value = activeRun.id
  runStatus.value = activeRun.status
  running.value = true
  assistantDraftId.value = `resume-${activeRun.id}`
  if (!messages.value.some((item) => item.id === assistantDraftId.value)) {
    messages.value.push({
      id: assistantDraftId.value,
      role: 'assistant',
      content: activeRun.output ?? '',
      created_at: activeRun.created_at,
      citations: [],
    })
  }

  const log = listOf(await request<RunEvent[] | { items: RunEvent[] }>(`/runs/${activeRun.id}/event-log`))
  const timeline = log.filter((item) => item.type !== 'model_delta').slice(-120)
  for (const event of log) {
    if (event.type === 'retrieval' && Array.isArray(event.data.items)) {
      for (const item of event.data.items) addCitation(item as unknown as Citation)
    } else if (event.type === 'citation') addCitation(event.data as unknown as Citation)
  }

  const terminal = [...log].reverse().find((item) => ['completed', 'failed', 'cancelled'].includes(item.type))
  if (terminal) {
    events.value = timeline.filter((item) => item.id !== terminal.id)
    handleRunEvent(terminal)
    return
  }
  events.value = timeline

  if (activeRun.status === 'waiting_approval') {
    const approvals = listOf(await request<ApprovalRecord[] | { items: ApprovalRecord[] }>(`/runs/${activeRun.id}/approvals`))
    const pending = approvals.find((item) => item.status === 'pending')
    if (pending) approval.value = pending
  }

  const lastId = log.reduce((highest, item) => Math.max(highest, Number(item.id) || 0), 0)
  connectRunStream(`/api/v1/runs/${activeRun.id}/events?after=${lastId}`)
  notify(activeRun.status === 'waiting_approval' ? '已恢复等待审批的运行' : '已重新连接进行中的运行', 'info')
}

function openCreate(): void {
  if (!agents.value.length) {
    navigateTo('agents')
    notify('请先创建一个可运行的智能体', 'info')
    return
  }
  Object.assign(createForm, { title: '新对话', agent_id: filteredAgents.value[0]?.id ?? '' })
  createOpen.value = true
}

async function createSession(): Promise<void> {
  if (!createForm.agent_id || !createForm.title.trim()) return
  creating.value = true
  try {
    const created = await request<SessionItem>('/sessions', { method: 'POST', ...jsonBody({ title: createForm.title.trim(), agent_id: createForm.agent_id }) })
    createOpen.value = false
    await load()
    await loadSession(created.id)
    notify('新会话已创建', 'success')
    await nextTick()
    promptBox.value?.focus()
  } catch (error) {
    notify(formatApiError(error), 'error')
  } finally {
    creating.value = false
  }
}

async function deleteSession(session: SessionItem): Promise<void> {
  if (running.value || !window.confirm(`确认删除会话“${session.title}”？`)) return
  try {
    await request<void>(`/sessions/${session.id}`, { method: 'DELETE' })
    notify('会话已删除', 'success')
    if (selectedId.value === session.id) selectedId.value = ''
    await load()
  } catch (error) { notify(formatApiError(error), 'error') }
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (messagesPane.value) messagesPane.value.scrollTop = messagesPane.value.scrollHeight
}

function updateAssistant(content: string, replace = false): void {
  const item = messages.value.find((message) => message.id === assistantDraftId.value)
  if (item) item.content = replace ? content : item.content + content
  void scrollToBottom()
}

function addCitation(value: Citation): void {
  if (!currentCitations.value.some((item) => item.document_id === value.document_id && item.chunk_index === value.chunk_index)) {
    currentCitations.value.push(value)
  }
}

function handleRunEvent(event: RunEvent): void {
  if (events.value.some((item) => item.id === event.id)) return
  if (!(event.type === 'model_delta' && events.value.at(-1)?.type === 'model_delta')) events.value.push(event)
  else events.value[events.value.length - 1] = event
  if (events.value.length > 120) events.value.splice(0, events.value.length - 120)

  const data = event.data
  if (event.type === 'model_delta') updateAssistant(String(data.content ?? ''))
  if (event.type === 'retrieval' && Array.isArray(data.items)) {
    for (const item of data.items) addCitation(item as unknown as Citation)
  }
  if (event.type === 'citation') addCitation(data as unknown as Citation)
  if (event.type === 'artifact_created') {
    const artifactId = String(data.artifact_id ?? '')
    if (artifactId && !currentArtifacts.value.some((item) => item.id === artifactId)) {
      currentArtifacts.value.push({ ...(data as unknown as ArtifactItem), id: artifactId })
    }
  }
  if (event.type === 'approval_required') {
    approval.value = {
      id: String(data.approval_id), kind: 'tool_approval', tool_name: String(data.tool),
      arguments: (data.arguments ?? {}) as Record<string, unknown>, risk: String(data.risk ?? 'write'),
    }
    runStatus.value = 'waiting_approval'
  }
  if (event.type === 'plan_review_required') {
    approval.value = {
      id: String(data.approval_id), kind: 'plan_review', tool_name: 'builtin.plan_review',
      arguments: { plan: data.plan, review: data.review }, risk: 'review',
    }
    runStatus.value = 'waiting_approval'
  }
  if (event.type === 'completed') {
    const output = String(data.output ?? '')
    if (output) updateAssistant(output, true)
    const draft = messages.value.find((message) => message.id === assistantDraftId.value)
    if (draft) draft.citations = (data.citations as Citation[] | undefined) ?? currentCitations.value
    finishRun('completed')
  }
  if (event.type === 'failed') {
    const partial = String(data.output ?? '')
    const message = String(data.message ?? '模型运行失败')
    updateAssistant(partial ? `${partial}\n\n[运行失败] ${message}` : `[运行失败] ${message}`, true)
    notify(message, 'error')
    finishRun('failed')
  }
  if (event.type === 'cancelled') {
    const partial = String(data.output ?? '')
    updateAssistant(partial || '运行已取消。', true)
    finishRun('cancelled')
  }
}

function finishRun(status: string): void {
  running.value = false
  runStatus.value = status
  approval.value = null
  streamState.value = 'idle'
  source?.close()
  source = null
  void refreshSessionsQuietly()
}

async function refreshSessionsQuietly(): Promise<void> {
  try { sessions.value = listOf(await request<SessionItem[] | { items: SessionItem[] }>('/sessions')) } catch { /* chat remains usable */ }
}

async function send(): Promise<void> {
  const text = prompt.value.trim()
  if (!canSend.value || !text) return
  prompt.value = ''
  const now = new Date().toISOString()
  messages.value.push({ id: `local-user-${Date.now()}`, role: 'user', content: text, created_at: now })
  assistantDraftId.value = `local-assistant-${Date.now()}`
  messages.value.push({ id: assistantDraftId.value, role: 'assistant', content: '', created_at: now, citations: [] })
  events.value = []
  currentCitations.value = []
  currentArtifacts.value = []
  approval.value = null
  running.value = true
  runStatus.value = 'queued'
  await scrollToBottom()
  try {
    const accepted = await request<RunResponse>(`/sessions/${selectedId.value}/runs`, { method: 'POST', ...jsonBody({ message: text }) })
    runId.value = accepted.run_id
    runStatus.value = accepted.status
    connectRunStream(accepted.events_url)
  } catch (error) {
    updateAssistant(`[无法启动运行] ${formatApiError(error)}`, true)
    running.value = false
    runStatus.value = 'failed'
    notify(formatApiError(error), 'error')
  }
}

async function cancelRun(): Promise<void> {
  if (!runId.value || !running.value) return
  try {
    await request(`/runs/${runId.value}/cancel`, { method: 'POST' })
    runStatus.value = 'cancelling'
    notify('已发送取消请求', 'info')
  } catch (error) { notify(formatApiError(error), 'error') }
}

async function decide(decision: 'approve' | 'reject'): Promise<void> {
  if (!approval.value || !runId.value) return
  const planReview = approval.value.kind === 'plan_review'
  decidingApproval.value = true
  try {
    await request(`/runs/${runId.value}/approvals/${approval.value.id}`, {
      method: 'POST', ...jsonBody({ decision, reason: decision === 'reject' ? '用户在控制台拒绝了该操作' : null }),
    })
    approval.value = null
    runStatus.value = 'running'
    notify(
      decision === 'approve' ? (planReview ? '方案已批准，开始生成代码' : '已批准，运行继续') : (planReview ? '方案已拒绝，不会生成或修改代码' : '已拒绝，模型将尝试替代方案'),
      decision === 'approve' ? 'success' : 'info',
    )
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { decidingApproval.value = false }
}

function keydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void send()
  }
}

function copyMessage(content: string): void {
  void navigator.clipboard.writeText(content)
  notify('回答已复制', 'success')
}

onMounted(load)
onActivated(() => { if (!loading.value && !running.value) void load() })
onBeforeUnmount(() => source?.close())
</script>

<template>
  <div class="page chat-page">
    <div class="chat-shell">
      <header class="chat-header">
        <div>
          <div class="eyebrow">LangGraph Runtime</div>
          <h1>对话与运行</h1>
        </div>
        <div class="chat-header-actions">
          <select v-model="projectFilter" class="select compact-select"><option value="all">全部项目</option><option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option></select>
          <span v-if="running" class="stream-pill"><i />{{ streamState === 'reconnecting' ? '正在重连事件流' : runStatus === 'waiting_approval' ? '等待审批' : '运行中' }}</span>
          <button class="button" type="button" @click="openCreate"><AppIcon name="plus" :size="16" />新对话</button>
        </div>
      </header>

      <div v-if="loading" class="chat-loading"><span class="spinner" />正在加载会话…</div>
      <EmptyState v-else-if="loadError" icon="alert" title="无法打开对话工作台" :description="loadError"><button class="button secondary" type="button" @click="load">重新连接</button></EmptyState>
      <div v-else class="chat-layout">
        <aside class="conversation-list panel">
          <div class="conversation-head"><span>最近会话</span><strong>{{ filteredSessions.length }}</strong></div>
          <div v-if="filteredSessions.length" class="conversation-scroll">
            <div
              v-for="session in filteredSessions"
              :key="session.id"
              class="conversation"
              :class="{ active: selectedId === session.id }"
              role="button"
              tabindex="0"
              @click="loadSession(session.id)"
              @keydown.enter="loadSession(session.id)"
              @keydown.space.prevent="loadSession(session.id)"
            >
              <span class="conversation-avatar"><AppIcon name="chat" :size="15" /></span>
              <span class="conversation-copy"><strong>{{ session.title }}</strong><small>{{ agentName(session.agent_id) }} · {{ relativeDate(session.updated_at) }}</small></span>
              <button class="conversation-delete" type="button" aria-label="删除会话" @click.stop="deleteSession(session)"><AppIcon name="trash" :size="13" /></button>
            </div>
          </div>
          <div v-else class="mini-empty"><AppIcon name="chat" :size="21" /><span>还没有会话</span></div>
          <button class="new-conversation" type="button" @click="openCreate"><AppIcon name="plus" :size="14" />开始新对话</button>
        </aside>

        <section class="chat-panel panel">
          <template v-if="selected">
            <header class="active-session">
              <div class="active-agent"><span><AppIcon name="agents" :size="18" /></span><div><strong>{{ selected.title }}</strong><small>{{ selectedAgent?.name ?? '智能体' }} · 配置快照随运行保存</small></div></div>
              <StatusBadge :status="running ? runStatus : 'ready'" :label="running ? undefined : '就绪'" />
            </header>
            <div ref="messagesPane" class="messages">
              <div v-if="sessionLoading" class="chat-loading"><span class="spinner" />加载消息…</div>
              <div v-else-if="messages.length === 0" class="welcome">
                <div class="welcome-mark"><span>H</span></div>
                <h2>有什么可以一起完成？</h2>
                <p>{{ selectedAgent?.description || '这个智能体已准备好使用模型、知识库与工具。' }}</p>
                <div class="suggestions">
                  <button type="button" @click="prompt = '总结知识库中的核心内容，并列出引用来源。'">总结知识库内容</button>
                  <button type="button" @click="prompt = '帮我制定一个清晰、可执行的任务计划。'">制定任务计划</button>
                </div>
              </div>
              <article v-for="message in messages" v-else :key="message.id" class="message" :class="`message-${message.role}`">
                <div class="message-avatar">{{ message.role === 'user' ? '你' : message.role === 'assistant' ? 'H' : 'T' }}</div>
                <div class="message-body">
                  <header><strong>{{ message.role === 'user' ? '你' : message.role === 'assistant' ? selectedAgent?.name || 'Hi-agent' : '工具' }}</strong><span>{{ relativeDate(message.created_at) }}</span><button v-if="message.role === 'assistant' && message.content" type="button" aria-label="复制回答" @click="copyMessage(message.content)"><AppIcon name="copy" :size="13" /></button></header>
                  <div v-if="message.content" class="message-content">{{ message.content }}</div>
                  <div v-else class="typing"><i /><i /><i /></div>
                  <div v-if="message.citations?.length" class="citation-list">
                    <span class="citation-label">引用</span>
                    <button v-for="(citation, index) in message.citations" :key="`${citation.document_id}-${citation.chunk_index}`" type="button" :title="citation.content">
                      <b>{{ index + 1 }}</b>{{ citation.filename }}<small><template v-if="citation.page">p.{{ citation.page }} · </template>#{{ citation.chunk_index }}</small>
                    </button>
                  </div>
                </div>
              </article>
              <section v-if="currentArtifacts.length" class="artifact-list">
                <a v-for="artifact in currentArtifacts" :key="artifact.id" :href="artifact.download_url || `/api/v1/artifacts/${artifact.id}/download`" class="artifact-card" download>
                  <span><AppIcon :name="artifact.kind === 'image' ? 'sparkles' : 'file'" :size="18" /></span>
                  <div><strong>{{ artifact.filename }}</strong><small>{{ artifact.kind === 'presentation' ? '演示文稿' : artifact.kind === 'image' ? '生成图片' : '生成报告' }} · {{ bytes(artifact.size_bytes) }}</small></div>
                  <AppIcon name="download" :size="16" />
                </a>
              </section>
            </div>

            <div v-if="approval" class="approval-bar">
              <span class="approval-icon"><AppIcon name="alert" :size="19" /></span>
              <div><strong>{{ approval.kind === 'plan_review' ? '实施方案需要人工 Review' : `工具请求${approval.risk === 'execute' ? '执行' : '写入'}权限` }}</strong><code>{{ approval.tool_name }}</code><p>{{ JSON.stringify(approval.arguments, null, 2) }}</p></div>
              <div class="approval-actions"><button class="button danger small" type="button" :disabled="decidingApproval" @click="decide('reject')">{{ approval.kind === 'plan_review' ? '退回方案' : '拒绝' }}</button><button class="button small" type="button" :disabled="decidingApproval" @click="decide('approve')">{{ approval.kind === 'plan_review' ? '批准实施' : '批准一次' }}</button></div>
            </div>

            <footer class="composer-wrap">
              <div class="composer" :class="{ disabled: running }">
                <textarea ref="promptBox" v-model="prompt" rows="1" maxlength="100000" :disabled="running" placeholder="输入消息，Enter 发送，Shift + Enter 换行…" @keydown="keydown" />
                <div class="composer-footer">
                  <div class="composer-tags"><span><AppIcon name="agents" :size="12" />{{ selectedAgent?.name }}</span><span v-if="selectedAgent?.knowledge_base_id"><AppIcon name="database" :size="12" />RAG</span></div>
                  <button v-if="running" class="send-button stop-button" type="button" aria-label="取消运行" @click="cancelRun"><AppIcon name="stop" :size="17" /></button>
                  <button v-else class="send-button" type="button" aria-label="发送消息" :disabled="!canSend" @click="send"><AppIcon name="send" :size="17" /></button>
                </div>
              </div>
              <p>Hi-agent 可能会出错，请核验重要信息与引用。</p>
            </footer>
          </template>
          <EmptyState v-else icon="chat" title="选择或创建一个会话" description="每个会话绑定一个智能体，运行期间会显示完整节点时间线。"><button class="button" type="button" @click="openCreate">开始新对话</button></EmptyState>
        </section>

        <aside class="timeline panel">
          <div class="timeline-head"><div><strong>运行时间线</strong><span>{{ running ? 'LIVE' : events.length ? runStatus.toUpperCase() : 'IDLE' }}</span></div><AppIcon name="activity" :size="17" /></div>
          <div v-if="timelineEmpty" class="timeline-empty"><span class="timeline-track" /><div><AppIcon name="clock" :size="20" /><strong>等待运行</strong><p>节点状态、检索、工具调用与审批会实时出现在这里。</p></div></div>
          <div v-else class="event-list">
            <article v-for="event in events" :key="event.id" class="event" :class="`event-${eventTone(event)}`">
              <span class="event-dot"><i /></span>
              <div><header><strong>{{ eventTitle(event) }}</strong><time>{{ new Date(event.created_at).toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit', second:'2-digit' }) }}</time></header><p v-if="event.type === 'tool_call'">{{ JSON.stringify(event.data.arguments) }}</p><p v-else-if="event.type === 'failed'">{{ event.data.message }}</p></div>
            </article>
          </div>
          <div v-if="currentCitations.length" class="run-sources"><strong>本次检索来源</strong><span v-for="sourceItem in currentCitations.slice(0,5)" :key="`${sourceItem.document_id}-${sourceItem.chunk_index}`"><AppIcon name="file" :size="12" /><b>{{ sourceItem.filename }}</b><small>#{{ sourceItem.chunk_index }}</small></span></div>
        </aside>
      </div>
    </div>

    <ModalDialog :open="createOpen" title="开始新对话" description="选择智能体后，会话会一直绑定该配置入口" @close="createOpen = false">
      <form class="form-grid" @submit.prevent="createSession">
        <div class="field full"><label for="session-title">会话名称</label><input id="session-title" v-model="createForm.title" class="input" maxlength="200" /></div>
        <div class="field full"><label for="session-agent">智能体</label><select id="session-agent" v-model="createForm.agent_id" class="select"><option v-for="agent in filteredAgents" :key="agent.id" :value="agent.id">{{ agent.name }} · {{ agent.description || '无说明' }}</option></select></div>
      </form>
      <template #footer><button class="button secondary" type="button" @click="createOpen = false">取消</button><button class="button" type="button" :disabled="creating || !createForm.agent_id" @click="createSession">{{ creating ? '创建中…' : '创建会话' }}</button></template>
    </ModalDialog>
  </div>
</template>

<style scoped>
.chat-page { overflow: hidden; }
.chat-shell { display: flex; width: 100%; height: 100%; flex-direction: column; padding: 25px 27px 27px; }
.chat-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 17px; }
.chat-header h1 { margin: 0; font-size: 25px; letter-spacing: -.035em; }
.chat-header .eyebrow { margin-bottom: 5px; }
.chat-header-actions { display: flex; align-items: center; gap: 9px; }
.stream-pill { display: inline-flex; align-items: center; gap: 6px; color: var(--green); font-size: 9px; }
.stream-pill i { width: 6px; height: 6px; background: #54b17e; border-radius: 50%; box-shadow: 0 0 0 4px rgba(84,177,126,.12); animation: pulse 1.3s infinite; }
.chat-layout { display: grid; min-height: 0; flex: 1; grid-template-columns: 205px minmax(380px,1fr) 245px; gap: 11px; }
.artifact-list { display: grid; gap: 8px; margin: 8px 45px 18px; }
.artifact-card { display: flex; align-items: center; gap: 10px; padding: 11px 13px; color: inherit; background: var(--green-soft); border: 1px solid rgba(35,93,70,.14); border-radius: 12px; text-decoration: none; }
.artifact-card > span { display: grid; width: 34px; height: 34px; place-items: center; color: var(--green); background: white; border-radius: 9px; }
.artifact-card > div { display: flex; min-width: 0; flex: 1; flex-direction: column; }
.artifact-card strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.artifact-card small { margin-top: 3px; color: var(--muted); font-size: 8px; }
.conversation-list, .chat-panel, .timeline { min-height: 0; overflow: hidden; }
.conversation-list { display: flex; flex-direction: column; padding: 7px; }
.conversation-head { display: flex; align-items: center; justify-content: space-between; padding: 10px 8px; color: var(--muted); font-size: 9px; }
.conversation-head strong { color: var(--green); font-family: 'DM Mono',monospace; }
.conversation-scroll { flex: 1; overflow-y: auto; }
.conversation { position: relative; display: flex; width: 100%; align-items: center; gap: 8px; padding: 9px 7px; color: var(--muted); text-align: left; background: transparent; border: 1px solid transparent; border-radius: 9px; cursor: pointer; }
.conversation:hover { background: #f8f9f5; }
.conversation:focus-visible { outline: 2px solid var(--green); outline-offset: 1px; }
.conversation.active { color: var(--ink); background: var(--green-soft); border-color: #d8eade; }
.conversation-avatar { display: grid; width: 29px; height: 29px; flex: 0 0 29px; place-items: center; color: var(--green); background: #fff; border-radius: 8px; }
.conversation-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; }
.conversation-copy strong { overflow: hidden; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.conversation-copy small { margin-top: 3px; overflow: hidden; color: var(--muted); font-size: 7px; text-overflow: ellipsis; white-space: nowrap; }
.conversation-delete { display: none; width: 24px; height: 24px; place-items: center; color: var(--muted); background: transparent; border: 0; border-radius: 6px; cursor: pointer; }
.conversation:hover .conversation-delete { display: grid; }
.conversation-delete:hover { color: var(--red); background: var(--red-soft); }
.new-conversation { display: flex; align-items: center; justify-content: center; gap: 5px; margin-top: 7px; padding: 9px; color: var(--green); font-size: 9px; font-weight: 650; background: #f7f9f5; border: 1px dashed #cbd7cc; border-radius: 9px; cursor: pointer; }
.mini-empty { display: flex; flex: 1; align-items: center; justify-content: center; flex-direction: column; gap: 8px; color: var(--faint); font-size: 9px; }
.chat-panel { display: flex; flex-direction: column; background: #fff; }
.active-session { display: flex; min-height: 59px; align-items: center; justify-content: space-between; padding: 10px 14px; border-bottom: 1px solid var(--line); }
.active-agent { display: flex; align-items: center; gap: 9px; }
.active-agent > span { display: grid; width: 34px; height: 34px; place-items: center; color: var(--green); background: var(--green-soft); border-radius: 10px; }
.active-agent div { display: flex; flex-direction: column; }
.active-agent strong { font-size: 10px; }
.active-agent small { margin-top: 3px; color: var(--muted); font-size: 7px; }
.messages { flex: 1; overflow-y: auto; padding: 15px 17px; scroll-behavior: smooth; }
.welcome { display: flex; min-height: 100%; align-items: center; justify-content: center; flex-direction: column; text-align: center; }
.welcome-mark { position: relative; display: grid; width: 58px; height: 58px; place-items: center; color: #17392e; font-size: 19px; font-weight: 800; background: var(--lime); border-radius: 18px 11px; box-shadow: 0 12px 26px rgba(81,121,61,.14); transform: rotate(-4deg); }
.welcome-mark span { transform: rotate(4deg); }
.welcome h2 { margin: 18px 0 6px; font-size: 18px; letter-spacing: -.03em; }
.welcome p { max-width: 380px; margin: 0; color: var(--muted); font-size: 9px; line-height: 1.6; }
.suggestions { display: flex; gap: 7px; margin-top: 17px; }
.suggestions button { padding: 8px 10px; color: #5c675f; font-size: 8px; background: #f7f9f5; border: 1px solid var(--line); border-radius: 8px; cursor: pointer; }
.suggestions button:hover { color: var(--green); border-color: #bcd0c0; }
.message { display: flex; gap: 10px; max-width: 92%; margin-bottom: 17px; }
.message-user { margin-left: auto; flex-direction: row-reverse; }
.message-avatar { display: grid; width: 28px; height: 28px; flex: 0 0 28px; place-items: center; color: var(--green); font-size: 9px; font-weight: 700; background: var(--green-soft); border-radius: 8px; }
.message-user .message-avatar { color: #fff; background: #315f50; }
.message-body { min-width: 0; }
.message-body > header { display: flex; align-items: center; gap: 7px; margin: 1px 0 5px; }
.message-user .message-body > header { justify-content: flex-end; }
.message-body header strong { font-size: 9px; }
.message-body header span { color: var(--faint); font-size: 7px; }
.message-body header button { display: grid; width: 20px; height: 20px; place-items: center; color: var(--faint); background: transparent; border: 0; border-radius: 5px; cursor: pointer; }
.message-content { padding: 10px 12px; color: #3f453f; font-size: 11px; line-height: 1.72; white-space: pre-wrap; overflow-wrap: anywhere; background: #f6f8f4; border: 1px solid #eceee8; border-radius: 4px 12px 12px; }
.message-user .message-content { color: #fff; background: #245b48; border-color: #245b48; border-radius: 12px 4px 12px 12px; }
.typing { display: flex; gap: 4px; padding: 12px; background: #f6f8f4; border-radius: 4px 12px 12px; }
.typing i { width: 5px; height: 5px; background: #8da095; border-radius: 50%; animation: pulse 1s infinite; }
.typing i:nth-child(2) { animation-delay: .15s; }.typing i:nth-child(3) { animation-delay: .3s; }
.citation-list { display: flex; max-width: 100%; gap: 5px; margin-top: 6px; flex-wrap: wrap; }
.citation-label { padding: 5px 2px; color: var(--faint); font-size: 7px; }
.citation-list button { display: flex; min-width: 0; align-items: center; gap: 5px; padding: 5px 7px; color: #59645d; font-size: 7px; background: #f4f7f2; border: 1px solid #e3e8e1; border-radius: 7px; cursor: pointer; }
.citation-list button b { display: grid; width: 14px; height: 14px; place-items: center; color: var(--green); background: var(--green-soft); border-radius: 4px; }
.citation-list button small { color: var(--faint); }
.approval-bar { display: flex; align-items: flex-start; gap: 10px; margin: 0 13px 8px; padding: 11px; background: var(--amber-soft); border: 1px solid #ecdcb9; border-radius: 11px; }
.approval-icon { display: grid; width: 32px; height: 32px; flex: 0 0 32px; place-items: center; color: var(--amber); background: #fff8e9; border-radius: 9px; }
.approval-bar > div:nth-child(2) { display: flex; min-width: 0; flex: 1; flex-direction: column; }
.approval-bar strong { font-size: 9px; }.approval-bar code { margin-top: 3px; font-family: 'DM Mono',monospace; font-size: 8px; }.approval-bar p { max-height: 38px; overflow: auto; margin: 4px 0 0; color: var(--muted); font-family: 'DM Mono',monospace; font-size: 7px; white-space: pre-wrap; }
.approval-actions { display: flex; align-items: center; gap: 5px; }
.composer-wrap { padding: 7px 13px 10px; border-top: 1px solid var(--line); }
.composer { padding: 9px; background: #f7f9f5; border: 1px solid var(--line-strong); border-radius: 12px; transition: .15s; }
.composer:focus-within { background: #fff; border-color: #70a98d; box-shadow: 0 0 0 3px rgba(31,115,84,.06); }
.composer.disabled { opacity: .78; }
.composer textarea { display: block; width: 100%; min-height: 35px; max-height: 120px; padding: 2px 3px; resize: none; color: var(--ink); font-size: 10px; line-height: 1.5; background: transparent; border: 0; outline: 0; }
.composer-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 4px; }
.composer-tags { display: flex; gap: 5px; }
.composer-tags span { display: flex; align-items: center; gap: 4px; padding: 4px 6px; color: var(--muted); font-size: 7px; background: #eef2ec; border-radius: 6px; }
.send-button { display: grid; width: 31px; height: 31px; place-items: center; color: #fff; background: var(--green); border: 0; border-radius: 9px; cursor: pointer; }
.send-button:disabled { cursor: not-allowed; opacity: .3; }.stop-button { background: var(--red); }
.composer-wrap > p { margin: 6px 0 0; color: var(--faint); font-size: 7px; text-align: center; }
.timeline { display: flex; flex-direction: column; }
.timeline-head { display: flex; min-height: 59px; align-items: center; justify-content: space-between; padding: 12px 14px; color: var(--green); border-bottom: 1px solid var(--line); }
.timeline-head > div { display: flex; flex-direction: column; }
.timeline-head strong { color: var(--ink); font-size: 10px; }.timeline-head span { margin-top: 3px; font-family: 'DM Mono',monospace; font-size: 6px; letter-spacing:.1em; }
.timeline-empty { position: relative; display: grid; flex: 1; place-items: center; padding: 20px; color: var(--muted); text-align: center; }
.timeline-empty > div { position: relative; z-index: 1; }.timeline-empty svg { color: var(--green); }.timeline-empty strong { display:block;margin-top:9px;font-size:10px; }.timeline-empty p { max-width: 170px;margin:5px auto;color:var(--faint);font-size:8px;line-height:1.6; }
.event-list { flex: 1; overflow-y: auto; padding: 12px; }
.event { display: grid; grid-template-columns: 18px minmax(0,1fr); gap: 7px; padding-bottom: 13px; }
.event-dot { position: relative; display: flex; justify-content:center; }
.event-dot::after { position:absolute;top:13px;bottom:-15px;width:1px;content:'';background:var(--line); }.event:last-child .event-dot::after{display:none}.event-dot i { position:relative;z-index:1;width:7px;height:7px;margin-top:4px;background:#a9afa8;border:2px solid #fff;border-radius:50%;box-shadow:0 0 0 1px #d5d9d3; }
.event > div { min-width: 0; padding: 6px 8px; background:#f8f9f6;border-radius:8px; }.event header{display:flex;align-items:center;justify-content:space-between;gap:5px}.event header strong{overflow:hidden;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.event time{color:var(--faint);font-family:'DM Mono',monospace;font-size:6px}.event p{margin:4px 0 0;overflow:hidden;color:var(--muted);font-family:'DM Mono',monospace;font-size:6px;text-overflow:ellipsis;white-space:nowrap}
.event-success .event-dot i{background:#55a877;box-shadow:0 0 0 2px #dceee3}.event-error .event-dot i{background:var(--red);box-shadow:0 0 0 2px var(--red-soft)}.event-approval .event-dot i{background:#d79c3f;box-shadow:0 0 0 2px var(--amber-soft)}.event-stream .event-dot i{background:var(--green);animation:pulse 1s infinite}.event-error > div{background:var(--red-soft)}.event-approval > div{background:var(--amber-soft)}
.run-sources { display:flex;flex-direction:column;gap:5px;padding:10px 12px;border-top:1px solid var(--line); }.run-sources>strong{margin-bottom:2px;font-size:8px}.run-sources>span{display:flex;min-width:0;align-items:center;gap:5px;color:var(--muted);font-size:7px}.run-sources b{overflow:hidden;font-weight:500;text-overflow:ellipsis;white-space:nowrap}.run-sources small{margin-left:auto;color:var(--faint)}
.chat-loading { display:flex;min-height:200px;flex:1;align-items:center;justify-content:center;gap:9px;color:var(--muted);font-size:10px}.chat-loading .spinner{width:18px;height:18px;margin:0}
@media (max-width: 1080px) { .chat-layout { grid-template-columns: 180px minmax(360px,1fr); }.timeline { display:none; } }
@media (max-width: 760px) { .chat-page { overflow: visible; }.chat-shell{height:calc(100vh - 57px);padding:14px 12px}.chat-header h1{font-size:20px}.chat-header .eyebrow{display:none}.chat-layout{grid-template-columns:1fr;}.conversation-list{display:none}.chat-panel{min-height:0}.active-agent small{display:none}.messages{padding-inline:12px}.message{max-width:97%}.approval-bar{flex-wrap:wrap}.approval-actions{width:100%;justify-content:flex-end;padding-left:42px}.chat-header-actions .stream-pill{display:none}.suggestions{flex-direction:column}.chat-header{margin-bottom:10px} }
</style>
