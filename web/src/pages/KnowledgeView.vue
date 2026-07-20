<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { download, formatApiError, jsonBody, listOf, openRunEventStream, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import { buildSearchCsv, safeFilename } from '../downloads'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { notify } from '../notifications'
import { hashSegments, navigateTo } from '../navigation'
import type { AgentConfig, Citation, DocumentItem, KnowledgeBase, PagedResult, Project, RunEvent, RunResponse, SearchResult } from '../types'

type DetailTab = 'overview' | 'documents' | 'retrieval' | 'rag'

const knowledgeBases = ref<KnowledgeBase[]>([])
const allKnowledgeBases = ref<KnowledgeBase[]>([])
const kbTotal = ref(0)
const selectedId = ref('')
const detailId = ref('')
const activeTab = ref<DetailTab>('overview')
const loading = ref(true)
const listLoading = ref(false)
const loadError = ref('')
const agents = ref<AgentConfig[]>([])
const projects = ref<Project[]>([])
const kbFilters = reactive({ q: '', exact: false, status: 'all', sort_by: 'updated_at', sort_order: 'desc', page: 1, limit: 10 })

const documents = ref<DocumentItem[]>([])
const documentTotal = ref(0)
const documentsLoading = ref(false)
const documentFilters = reactive({ q: '', exact: false, status: 'all', sort_by: 'created_at', sort_order: 'desc', page: 1, limit: 10 })

const createOpen = ref(false)
const editOpen = ref(false)
const creating = ref(false)
const saving = ref(false)
const createForm = reactive({ project_id: '', name: '', description: '', embedding_model: 'BAAI/bge-small-zh-v1.5', chunk_size: 800, chunk_overlap: 120, top_k: 5, ocr_mode: 'auto', ocr_language: 'ch', ocr_min_chars: 30 })
const editForm = reactive({ project_id: '', name: '', description: '' })
const indexForm = reactive({ embedding_model: '', chunk_size: 800, chunk_overlap: 120, top_k: 5, ocr_mode: 'auto', ocr_language: 'ch', ocr_min_chars: 30 })
const reindexing = ref(false)

const uploadBusy = ref(false)
const dragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const searchQuery = ref('')
const searching = ref(false)
const searchResults = ref<SearchResult[]>([])
const searched = ref(false)
const retrievalMode = ref<'dense' | 'lexical' | 'hybrid'>('hybrid')
const qaQuestion = ref('')
const qaAnswer = ref('')
const qaRunning = ref(false)
const qaEvents = ref<RunEvent[]>([])
const qaCitations = ref<Citation[]>([])
const qaRunId = ref('')
const qaCompleted = ref(false)
const reportFormat = ref<'md' | 'docx' | 'pdf'>('md')
let qaSource: EventSource | null = null

const selected = computed(() => knowledgeBases.value.find((item) => item.id === selectedId.value) ?? allKnowledgeBases.value.find((item) => item.id === selectedId.value) ?? null)
const isDetail = computed(() => Boolean(detailId.value))
const ragAgents = computed(() => agents.value.filter((agent) => agent.knowledge_base_id === selectedId.value && agent.enabled !== false && agent.model_endpoint_id))
const kbPages = computed(() => Math.max(1, Math.ceil(kbTotal.value / kbFilters.limit)))
const documentPages = computed(() => Math.max(1, Math.ceil(documentTotal.value / documentFilters.limit)))
const totalDocuments = computed(() => allKnowledgeBases.value.reduce((sum, item) => sum + (item.document_count ?? 0), 0))
const totalChunks = computed(() => allKnowledgeBases.value.reduce((sum, item) => sum + (item.chunk_count ?? 0), 0))
const failedDocuments = computed(() => allKnowledgeBases.value.reduce((sum, item) => sum + (item.failed_document_count ?? 0), 0))

function queryString(values: Record<string, string | number>): string {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => { if (String(value)) params.set(key, String(value)) })
  return params.toString()
}

function bytes(value?: number): string {
  if (!value) return '0 B'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function date(value?: string): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function statusLabel(status?: string): string {
  return ({ empty: '空库', ready: '可检索', processing: '处理中', error: '异常' } as Record<string, string>)[status ?? ''] ?? '未知'
}
function projectName(id?: string): string { return projects.value.find((item) => item.id === id)?.name ?? '未归属项目' }

function syncIndexForm(): void {
  if (!selected.value) return
  Object.assign(indexForm, { embedding_model: selected.value.embedding_model || 'BAAI/bge-small-zh-v1.5', chunk_size: selected.value.chunk_size || 800, chunk_overlap: selected.value.chunk_overlap ?? 120, top_k: selected.value.top_k || 5, ocr_mode: selected.value.ocr_mode || 'auto', ocr_language: selected.value.ocr_language || 'ch', ocr_min_chars: selected.value.ocr_min_chars ?? 30 })
}

async function loadKnowledgeBases(resetSelection = false): Promise<void> {
  listLoading.value = true
  try {
    const params: Record<string, string | number> = {
      q: kbFilters.exact ? '' : kbFilters.q.trim(),
      name_exact: kbFilters.exact ? kbFilters.q.trim() : '',
      status: kbFilters.status,
      sort_by: kbFilters.sort_by,
      sort_order: kbFilters.sort_order,
      offset: (kbFilters.page - 1) * kbFilters.limit,
      limit: kbFilters.limit,
    }
    const data = await request<PagedResult<KnowledgeBase>>(`/knowledge-bases/query?${queryString(params)}`)
    knowledgeBases.value = data.items
    kbTotal.value = data.total
    if (kbFilters.page > kbPages.value) { kbFilters.page = kbPages.value; await loadKnowledgeBases(resetSelection); return }
    if (detailId.value) selectedId.value = detailId.value
    else if (resetSelection) selectedId.value = ''
    syncIndexForm()
  } finally { listLoading.value = false }
}

async function loadPage(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const [allData, agentData, projectData] = await Promise.all([
      request<KnowledgeBase[] | { items: KnowledgeBase[] }>('/knowledge-bases'),
      request<AgentConfig[] | { items: AgentConfig[] }>('/agents'),
      request<Project[]>('/projects'),
    ])
    allKnowledgeBases.value = listOf(allData)
    agents.value = listOf(agentData)
    projects.value = listOf(projectData)
    if (!createForm.project_id) createForm.project_id = projects.value.find((item) => item.status === 'active')?.id ?? ''
    await loadKnowledgeBases()
    if (detailId.value) {
      selectedId.value = detailId.value
      if (!selected.value) throw new Error('知识库不存在或已被删除')
      syncIndexForm()
      await loadDocuments()
    }
  } catch (error) { loadError.value = formatApiError(error) }
  finally { loading.value = false }
}

async function applyKbFilters(): Promise<void> {
  kbFilters.page = 1
  await loadKnowledgeBases(true)
}

async function clearKbFilters(): Promise<void> {
  Object.assign(kbFilters, { q: '', exact: false, status: 'all', sort_by: 'updated_at', sort_order: 'desc', page: 1 })
  await loadKnowledgeBases(true)
}

async function changeKbPage(page: number): Promise<void> {
  kbFilters.page = Math.min(kbPages.value, Math.max(1, page))
  await loadKnowledgeBases(true)
}

async function loadDocuments(): Promise<void> {
  if (!selectedId.value) { documents.value = []; documentTotal.value = 0; return }
  documentsLoading.value = true
  try {
    const params: Record<string, string | number> = {
      q: documentFilters.exact ? '' : documentFilters.q.trim(),
      filename_exact: documentFilters.exact ? documentFilters.q.trim() : '',
      status: documentFilters.status,
      sort_by: documentFilters.sort_by,
      sort_order: documentFilters.sort_order,
      offset: (documentFilters.page - 1) * documentFilters.limit,
      limit: documentFilters.limit,
    }
    const data = await request<PagedResult<DocumentItem>>(`/knowledge-bases/${selectedId.value}/documents/query?${queryString(params)}`)
    documents.value = data.items
    documentTotal.value = data.total
  } catch (error) { notify(formatApiError(error), 'error'); documents.value = []; documentTotal.value = 0 }
  finally { documentsLoading.value = false }
}

async function openKnowledgeBase(id: string): Promise<void> {
  detailId.value = id
  selectedId.value = id
  activeTab.value = 'overview'
  Object.assign(documentFilters, { q: '', exact: false, status: 'all', sort_by: 'created_at', sort_order: 'desc', page: 1 })
  searchResults.value = []; searched.value = false; qaAnswer.value = ''; qaEvents.value = []; qaCitations.value = []; qaRunId.value = ''; qaCompleted.value = false
  syncIndexForm()
  await loadDocuments()
  navigateTo(`knowledge/${encodeURIComponent(id)}`)
}

function backToKnowledgeList(): void {
  detailId.value = ''
  selectedId.value = ''
  activeTab.value = 'overview'
  navigateTo('knowledge')
}

function syncKnowledgeRoute(): void {
  const path = hashSegments()
  const id = path[0] === 'knowledge' && path[1] ? decodeURIComponent(path[1]) : ''
  if (id === detailId.value) return
  detailId.value = id
  selectedId.value = id
  activeTab.value = 'overview'
  if (id && !loading.value) void loadPage()
}

async function applyDocumentFilters(): Promise<void> { documentFilters.page = 1; await loadDocuments() }
async function changeDocumentPage(page: number): Promise<void> { documentFilters.page = Math.min(documentPages.value, Math.max(1, page)); await loadDocuments() }

async function refreshData(): Promise<void> {
  const data = await request<KnowledgeBase[] | { items: KnowledgeBase[] }>('/knowledge-bases')
  allKnowledgeBases.value = listOf(data)
  await loadKnowledgeBases()
  if (selectedId.value) await loadDocuments()
}

async function createKnowledgeBase(): Promise<void> {
  if (!createForm.name.trim()) { notify('请填写知识库名称', 'error'); return }
  creating.value = true
  try {
    const created = await request<KnowledgeBase>('/knowledge-bases', { method: 'POST', ...jsonBody({ ...createForm, name: createForm.name.trim(), description: createForm.description.trim() }) })
    createOpen.value = false
    Object.assign(createForm, { project_id: projects.value.find((item) => item.status === 'active')?.id ?? '', name: '', description: '', embedding_model: 'BAAI/bge-small-zh-v1.5', chunk_size: 800, chunk_overlap: 120, top_k: 5, ocr_mode: 'auto', ocr_language: 'ch', ocr_min_chars: 30 })
    notify('知识库已创建', 'success')
    await refreshData(); await openKnowledgeBase(created.id)
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { creating.value = false }
}

function openEdit(): void {
  if (!selected.value) return
  Object.assign(editForm, { project_id: selected.value.project_id, name: selected.value.name, description: selected.value.description ?? '' })
  editOpen.value = true
}

async function updateKnowledgeBase(): Promise<void> {
  if (!selected.value || !editForm.name.trim()) { notify('请填写知识库名称', 'error'); return }
  saving.value = true
  try {
    await request<KnowledgeBase>(`/knowledge-bases/${selected.value.id}`, { method: 'PATCH', ...jsonBody({ project_id: editForm.project_id, name: editForm.name.trim(), description: editForm.description.trim() }) })
    editOpen.value = false
    notify('知识库信息已更新', 'success')
    await refreshData()
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { saving.value = false }
}

async function deleteKnowledgeBase(): Promise<void> {
  if (!selected.value || !window.confirm(`确认删除知识库“${selected.value.name}”及其全部文档和向量？此操作无法撤销。`)) return
  try { await request<void>(`/knowledge-bases/${selected.value.id}`, { method: 'DELETE' }); notify('知识库已删除', 'success'); backToKnowledgeList(); await refreshData() }
  catch (error) { notify(formatApiError(error), 'error') }
}

async function upload(files: FileList | File[]): Promise<void> {
  if (!selectedId.value || files.length === 0) return
  const allowed = new Set(['pdf', 'docx', 'md', 'markdown', 'txt'])
  const items = Array.from(files)
  const invalid = items.find((file) => !allowed.has(file.name.split('.').pop()?.toLowerCase() ?? '') || file.size > 50 * 1024 * 1024)
  if (invalid) { notify(`“${invalid.name}”格式不支持或超过 50 MB`, 'error'); return }
  uploadBusy.value = true
  let completed = 0
  for (const file of items) {
    const body = new FormData(); body.append('file', file, file.name)
    try { await request<DocumentItem>(`/knowledge-bases/${selectedId.value}/documents`, { method: 'POST', body }); completed += 1 }
    catch (error) { notify(`${file.name}：${formatApiError(error)}`, 'error') }
  }
  if (completed) notify(`${completed} 个文档已上传并完成索引`, 'success')
  uploadBusy.value = false
  if (fileInput.value) fileInput.value.value = ''
  await refreshData()
}

function dropped(event: DragEvent): void { dragging.value = false; if (event.dataTransfer?.files) void upload(event.dataTransfer.files) }

async function deleteDocument(document: DocumentItem): Promise<void> {
  if (!window.confirm(`删除“${document.filename}”及其全部向量？`)) return
  try { await request<void>(`/documents/${document.id}`, { method: 'DELETE' }); notify('文档与向量已删除', 'success'); await refreshData() }
  catch (error) { notify(formatApiError(error), 'error') }
}

async function search(): Promise<void> {
  if (!selectedId.value || !searchQuery.value.trim()) return
  searching.value = true; searched.value = true
  try {
    const data = await request<{ items: SearchResult[] } | SearchResult[]>(`/knowledge-bases/${selectedId.value}/search`, { method: 'POST', ...jsonBody({ query: searchQuery.value.trim(), top_k: selected.value?.top_k || 5, mode: retrievalMode.value }) })
    searchResults.value = listOf(data)
  } catch (error) { notify(formatApiError(error), 'error'); searchResults.value = [] }
  finally { searching.value = false }
}

function downloadText(filename: string, content: string, type: string): void {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function downloadSearchCsv(): void {
  if (!selected.value || !searchResults.value.length) return
  const csv = buildSearchCsv({ knowledgeBase: selected.value.name, query: searchQuery.value, mode: retrievalMode.value, results: searchResults.value })
  downloadText(`${safeFilename(selected.value.name)}-检索结果.csv`, csv, 'text/csv;charset=utf-8')
  notify('检索结果 CSV 已下载', 'success')
}

async function downloadRagReport(): Promise<void> {
  if (!qaRunId.value || !qaAnswer.value || !qaCompleted.value) return
  try {
    const result = await download('/rag/reports', { method: 'POST', ...jsonBody({ run_id: qaRunId.value, format: reportFormat.value }) })
    const url = URL.createObjectURL(result.blob); const link = document.createElement('a')
    link.href = url; link.download = result.filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url)
    notify(`RAG ${reportFormat.value.toUpperCase()} 报告已下载`, 'success')
  } catch (error) { notify(formatApiError(error), 'error') }
}

async function rebuildIndex(): Promise<void> {
  if (!selected.value || !window.confirm('确认按新配置重建全部文档索引？重建期间该知识库暂不可检索。')) return
  reindexing.value = true
  try { await request(`/knowledge-bases/${selected.value.id}/reindex`, { method: 'POST', ...jsonBody(indexForm) }); notify('索引已按新配置重建', 'success'); await refreshData() }
  catch (error) { notify(formatApiError(error), 'error') }
  finally { reindexing.value = false }
}

async function askRag(): Promise<void> {
  const agent = ragAgents.value[0]
  if (!agent || !qaQuestion.value.trim() || qaRunning.value) return
  qaAnswer.value = ''; qaEvents.value = []; qaCitations.value = []; qaRunId.value = ''; qaCompleted.value = false; qaRunning.value = true
  try {
    const session = await request<{ id: string }>('/sessions', { method: 'POST', ...jsonBody({ title: `RAG 实验：${qaQuestion.value.trim().slice(0, 30)}`, agent_id: agent.id }) })
    const accepted = await request<RunResponse>(`/sessions/${session.id}/runs`, { method: 'POST', ...jsonBody({ message: qaQuestion.value.trim() }) })
    qaRunId.value = accepted.run_id
    qaSource?.close()
    qaSource = openRunEventStream(accepted.events_url, { onEvent: (event) => {
      qaEvents.value.push(event)
      if (event.type === 'model_delta') qaAnswer.value += String(event.data.content ?? '')
      if (event.type === 'retrieval' && Array.isArray(event.data.items)) qaCitations.value = event.data.items as unknown as Citation[]
      if (event.type === 'completed') { qaAnswer.value = String(event.data.output ?? qaAnswer.value); qaCompleted.value = true; qaRunning.value = false; qaSource?.close() }
      if (event.type === 'failed' || event.type === 'cancelled') { qaCompleted.value = false; qaAnswer.value += `\n\n[${event.type === 'failed' ? '运行失败' : '已取消'}] ${String(event.data.message ?? '')}`; qaRunning.value = false; qaSource?.close() }
    } })
  } catch (error) { qaRunning.value = false; notify(formatApiError(error), 'error') }
}

onMounted(() => {
  syncKnowledgeRoute()
  window.addEventListener('hashchange', syncKnowledgeRoute)
  void loadPage()
})
onActivated(() => { syncKnowledgeRoute(); if (!loading.value) void loadPage() })
onBeforeUnmount(() => { qaSource?.close(); window.removeEventListener('hashchange', syncKnowledgeRoute) })
</script>

<template>
  <div class="page">
    <div class="page-inner">
      <header class="page-header">
        <div class="page-title-group">
          <button v-if="isDetail" class="back-link" type="button" @click="backToKnowledgeList">‹ 返回知识库列表</button>
          <div class="eyebrow">Knowledge workspace · Hybrid RAG</div>
          <h1>{{ isDetail ? (selected?.name || '知识库详情') : '知识库列表' }}</h1>
          <p>{{ isDetail ? '管理知识库内容、文档索引、检索验证与 RAG 问答。' : '查询和浏览全部知识库，点击名称进入内容管理。' }}</p>
        </div>
        <div class="page-actions"><button class="button secondary" type="button" @click="loadPage"><AppIcon name="refresh" :size="15" />刷新</button><button v-if="!isDetail" class="button" type="button" @click="createOpen = true"><AppIcon name="plus" :size="16" />新建知识库</button></div>
      </header>

      <LoadingState v-if="loading" :rows="4" />
      <EmptyState v-else-if="loadError" icon="alert" title="无法加载知识库" :description="loadError"><button class="button secondary" type="button" @click="loadPage">重新连接</button></EmptyState>
      <template v-else>
        <section v-if="!isDetail" class="metric-grid">
          <article><span>知识库</span><strong>{{ allKnowledgeBases.length }}</strong><small>本地可管理空间</small></article>
          <article><span>文档</span><strong>{{ totalDocuments }}</strong><small>已上传文件总数</small></article>
          <article><span>索引分块</span><strong>{{ totalChunks }}</strong><small>Dense + BM25</small></article>
          <article :class="{ warning: failedDocuments }"><span>异常文档</span><strong>{{ failedDocuments }}</strong><small>{{ failedDocuments ? '需要检查解析错误' : '处理链路正常' }}</small></article>
        </section>

        <section v-if="!isDetail" class="panel kb-toolbar">
          <form class="filter-search" @submit.prevent="applyKbFilters"><AppIcon name="search" :size="17" /><input v-model="kbFilters.q" placeholder="按名称或说明查询知识库…" /><label class="exact-check"><input v-model="kbFilters.exact" type="checkbox" />精确名称</label><button class="button small" type="submit">查询</button></form>
          <select v-model="kbFilters.status" class="input compact" aria-label="知识库状态" @change="applyKbFilters"><option value="all">全部状态</option><option value="ready">可检索</option><option value="empty">空库</option><option value="processing">处理中</option><option value="error">异常</option></select>
          <select v-model="kbFilters.sort_by" class="input compact" aria-label="排序字段" @change="applyKbFilters"><option value="updated_at">最近更新</option><option value="created_at">创建时间</option><option value="name">名称</option><option value="document_count">文档数量</option></select>
          <button class="button ghost small" type="button" @click="clearKbFilters">重置</button>
        </section>

        <section v-if="!isDetail" class="panel kb-table-panel">
          <div class="section-bar"><div><h2>知识库</h2><p>共 {{ kbTotal }} 个结果；名称可点击进入详情</p></div><StatusBadge status="ready" :label="`${kbTotal} 个知识库`" /></div>
          <div v-if="listLoading" class="mini-loading"><span class="spinner" />查询中…</div>
          <EmptyState v-else-if="!knowledgeBases.length" icon="search" title="没有匹配的知识库" description="可调整查询词或筛选条件。"><button class="button secondary small" @click="clearKbFilters">清除条件</button></EmptyState>
          <div v-else class="table-wrap"><table class="data-table knowledge-table"><thead><tr><th>知识库名称</th><th>所属项目</th><th>状态</th><th>文档</th><th>分块</th><th>绑定智能体</th><th>容量</th><th>更新时间</th><th /></tr></thead><tbody><tr v-for="kb in knowledgeBases" :key="kb.id"><td><button class="kb-name-link" type="button" @click="openKnowledgeBase(kb.id)"><span class="kb-link-icon"><AppIcon name="database" :size="16" /></span><span><strong>{{ kb.name }}</strong><small>{{ kb.description || '未填写说明' }}</small></span></button></td><td>{{ projectName(kb.project_id) }}</td><td><StatusBadge :status="kb.status || 'empty'" :label="statusLabel(kb.status)" /></td><td>{{ kb.document_count ?? 0 }}</td><td>{{ kb.chunk_count ?? 0 }}</td><td>{{ kb.bound_agent_count ?? 0 }}</td><td>{{ bytes(kb.total_size_bytes) }}</td><td>{{ date(kb.updated_at) }}</td><td><button class="button ghost small" type="button" @click="openKnowledgeBase(kb.id)">进入管理 <AppIcon name="chevron" :size="13" /></button></td></tr></tbody></table></div>
          <footer v-if="kbTotal" class="pager"><span>共 {{ kbTotal }} 个知识库</span><div><button :disabled="kbFilters.page <= 1" @click="changeKbPage(kbFilters.page - 1)">上一页</button><b>{{ kbFilters.page }} / {{ kbPages }}</b><button :disabled="kbFilters.page >= kbPages" @click="changeKbPage(kbFilters.page + 1)">下一页</button></div></footer>
        </section>

        <main v-else-if="selected" class="kb-content">
          <section class="panel panel-padded kb-overview">
            <div><span class="overview-mark"><AppIcon name="database" :size="22" /></span><div><div class="title-line"><h2>{{ selected.name }}</h2><StatusBadge :status="selected.status || 'empty'" :label="statusLabel(selected.status)" /></div><p>{{ selected.description || '未填写说明' }}</p><small>更新于 {{ date(selected.updated_at) }} · ID {{ selected.id }}</small></div></div>
            <div class="overview-actions"><button class="button secondary small" type="button" @click="openEdit"><AppIcon name="edit" :size="14" />编辑</button><button class="button danger small" type="button" @click="deleteKnowledgeBase"><AppIcon name="trash" :size="14" />删除</button></div>
          </section>

          <nav class="detail-tabs panel" aria-label="知识库功能">
            <button v-for="tab in ([['overview','概览'],['documents','文档'],['retrieval','索引与检索'],['rag','RAG 问答']] as const)" :key="tab[0]" :class="{ active: activeTab === tab[0] }" @click="activeTab = tab[0]">{{ tab[1] }}<span v-if="tab[0] === 'documents'">{{ selected.document_count ?? 0 }}</span></button>
          </nav>

          <template v-if="activeTab === 'overview'">
            <section class="summary-grid">
              <article class="panel"><span>文档处理</span><strong>{{ selected.ready_document_count ?? 0 }} / {{ selected.document_count ?? 0 }}</strong><small>可检索 / 全部</small></article>
              <article class="panel"><span>索引分块</span><strong>{{ selected.chunk_count ?? 0 }}</strong><small>平均 {{ selected.document_count ? Math.round((selected.chunk_count ?? 0) / selected.document_count) : 0 }} 块/文档</small></article>
              <article class="panel"><span>存储容量</span><strong>{{ bytes(selected.total_size_bytes) }}</strong><small>原始文档大小</small></article>
              <article class="panel"><span>绑定智能体</span><strong>{{ selected.bound_agent_count ?? 0 }}</strong><small>使用此知识库</small></article>
            </section>
            <section class="panel upload-section"><div class="drop-zone" :class="{ dragging, busy: uploadBusy }" @dragenter.prevent="dragging = true" @dragover.prevent @dragleave.prevent="dragging = false" @drop.prevent="dropped"><span v-if="uploadBusy" class="spinner" /><span v-else class="upload-icon"><AppIcon name="upload" :size="21" /></span><div><strong>{{ uploadBusy ? '正在解析并索引文档…' : '上传资料到知识库' }}</strong><span>支持 PDF、DOCX、Markdown、TXT；按 SHA-256 去重；单文件不超过 50 MB</span></div><button v-if="!uploadBusy" class="button secondary small" type="button" @click="fileInput?.click()">选择文件</button><input ref="fileInput" type="file" hidden multiple accept=".pdf,.docx,.md,.markdown,.txt" @change="($event.target as HTMLInputElement).files && upload(($event.target as HTMLInputElement).files!)" /></div></section>
            <section class="panel panel-padded flow-card"><div class="section-heading"><div><h2>处理流程</h2><p>从原始文档到可验证引用的完整状态</p></div><StatusBadge :status="selected.status || 'empty'" :label="statusLabel(selected.status)" /></div><div class="rag-flow"><span>上传与去重</span><i>→</i><span>解析清洗</span><i>→</i><span>Token 分块</span><i>→</i><span>向量嵌入</span><i>→</i><span>Qdrant / BM25</span><i>→</i><span>可引用检索</span></div></section>
          </template>

          <section v-else-if="activeTab === 'documents'" class="panel">
            <div class="section-bar"><div><h2>文档管理</h2><p>按文件名查询、精确查找、筛选处理状态并查看索引结果</p></div><StatusBadge status="indexed" :label="`${documentTotal} 个文件`" /></div>
            <div class="document-toolbar"><form class="filter-search" @submit.prevent="applyDocumentFilters"><AppIcon name="search" :size="16" /><input v-model="documentFilters.q" placeholder="查询文件名…" /><label class="exact-check"><input v-model="documentFilters.exact" type="checkbox" />精确文件名</label><button class="button small">查询</button></form><select v-model="documentFilters.status" class="input compact" @change="applyDocumentFilters"><option value="all">全部状态</option><option value="ready">可检索</option><option value="indexed">已索引</option><option value="processing">处理中</option><option value="failed">异常</option></select><select v-model="documentFilters.sort_by" class="input compact" @change="applyDocumentFilters"><option value="created_at">最近添加</option><option value="filename">文件名</option><option value="size_bytes">文件大小</option><option value="chunk_count">分块数量</option></select></div>
            <LoadingState v-if="documentsLoading" :rows="2" />
            <EmptyState v-else-if="documents.length === 0" icon="file" title="没有匹配的文档" description="上传新文档，或调整文件名和状态条件。" />
            <div v-else class="table-wrap"><table class="data-table document-table"><thead><tr><th>文件</th><th>提取方式</th><th>大小</th><th>分块</th><th>状态</th><th>添加时间</th><th /></tr></thead><tbody><tr v-for="document in documents" :key="document.id"><td><span class="file-cell"><i><AppIcon name="file" :size="16" /></i><span><strong>{{ document.filename }}</strong><small>{{ document.error || document.media_type || document.filename.split('.').pop()?.toUpperCase() }}</small></span></span></td><td><StatusBadge :status="document.extraction_method || 'text'" :label="document.extraction_method === 'hybrid' ? '文本 + OCR' : document.extraction_method === 'ocr' ? 'PaddleOCR' : '文字层'" /><small v-if="document.ocr_pages?.length">{{ document.ocr_pages.length }} 页 OCR</small></td><td>{{ bytes(document.size_bytes ?? document.size) }}</td><td>{{ document.chunk_count ?? '—' }}</td><td><StatusBadge :status="document.status || 'indexed'" /></td><td>{{ date(document.created_at) }}</td><td><button class="icon-button delete-document" type="button" aria-label="删除文档" @click="deleteDocument(document)"><AppIcon name="trash" :size="15" /></button></td></tr></tbody></table></div>
            <footer v-if="documentTotal" class="pager"><span>共 {{ documentTotal }} 个文档</span><div><button :disabled="documentFilters.page <= 1" @click="changeDocumentPage(documentFilters.page - 1)">上一页</button><b>{{ documentFilters.page }} / {{ documentPages }}</b><button :disabled="documentFilters.page >= documentPages" @click="changeDocumentPage(documentFilters.page + 1)">下一页</button></div></footer>
          </section>

          <template v-else-if="activeTab === 'retrieval'">
            <section class="panel panel-padded index-config"><div class="section-heading"><div><h2>向量索引与 OCR 配置</h2><p>PDF 优先读取文字层，仅对扫描页调用 PaddleOCR；保存后重建全部文档</p></div><StatusBadge status="ready" label="HYBRID + OCR" /></div><div class="config-grid"><div class="field wide"><label>嵌入模型</label><input v-model="indexForm.embedding_model" class="input" /></div><div class="field"><label>分块 Token</label><input v-model.number="indexForm.chunk_size" class="input" type="number" min="100" max="4000" /></div><div class="field"><label>重叠 Token</label><input v-model.number="indexForm.chunk_overlap" class="input" type="number" min="0" max="1000" /></div><div class="field"><label>Top K</label><input v-model.number="indexForm.top_k" class="input" type="number" min="1" max="50" /></div><div class="field"><label>PDF OCR 策略</label><select v-model="indexForm.ocr_mode" class="select"><option value="off">关闭 OCR</option><option value="auto">自动回退（推荐）</option><option value="force">所有页面强制 OCR</option></select></div><div class="field"><label>OCR 语言</label><select v-model="indexForm.ocr_language" class="select"><option value="ch">中文 + 英文</option><option value="en">英文</option></select></div><div class="field"><label>文字层阈值</label><input v-model.number="indexForm.ocr_min_chars" class="input" type="number" min="0" max="1000" /><span class="field-hint">少于该字符数时启用 OCR</span></div><button class="button secondary" :disabled="reindexing" type="button" @click="rebuildIndex">{{ reindexing ? '正在重建…' : '保存并重建' }}</button></div></section>
            <section class="panel panel-padded search-panel"><div class="section-heading"><div><h2>检索试验台</h2><p>检查召回通道、融合分数与原始片段，不调用大语言模型</p></div><div class="heading-actions"><select v-model="retrievalMode" class="input mode-select"><option value="hybrid">混合检索</option><option value="dense">语义向量</option><option value="lexical">BM25 关键词</option></select><button class="button secondary small" type="button" :disabled="!searchResults.length" @click="downloadSearchCsv"><AppIcon name="download" :size="14" />下载查询结果</button></div></div><form class="search-box" @submit.prevent="search"><AppIcon name="search" :size="18" /><input v-model="searchQuery" placeholder="输入问题，检查知识库召回…" /><button class="button small" type="submit" :disabled="searching || !searchQuery.trim()">{{ searching ? '检索中…' : '检索' }}</button></form><div v-if="searching" class="search-loading"><span class="spinner" /> 正在计算查询向量…</div><EmptyState v-else-if="searched && searchResults.length === 0" icon="search" title="没有找到相关片段" description="可以换一种问法，或确认文档索引已完成。" /><div v-else-if="searchResults.length" class="result-list"><article v-for="(result, index) in searchResults" :key="`${result.document_id}-${result.chunk_index}`" class="result-card"><span class="result-rank">{{ String(index + 1).padStart(2, '0') }}</span><div><header><strong>{{ result.filename }}</strong><span>块 {{ result.chunk_index }}<template v-if="result.page"> · 第 {{ result.page }} 页</template> · {{ result.channels?.join(' + ') || retrievalMode }}</span><em>{{ (result.score * 100).toFixed(1) }}%</em></header><p>{{ result.content }}</p></div></article></div></section>
          </template>

          <section v-else class="panel panel-padded rag-lab"><div class="section-heading"><div><h2>RAG 问答实验台</h2><p>运行检索、上下文组装、模型生成与引用持久化的完整链路</p></div><div class="heading-actions"><StatusBadge :status="qaRunning ? 'running' : (qaCompleted ? 'ready' : 'unknown')" :label="qaRunning ? '运行中' : (qaCompleted ? '已完成' : '可观测')" /><select v-model="reportFormat" class="select compact-select" aria-label="报告格式"><option value="md">Markdown</option><option value="docx">Word DOCX</option><option value="pdf">PDF</option></select><button class="button secondary small" type="button" :disabled="!qaCompleted || !qaAnswer || !qaRunId" @click="downloadRagReport"><AppIcon name="download" :size="14" />下载报告</button></div></div><div class="rag-flow"><span>问题分析</span><i>→</i><span>Dense / BM25</span><i>→</i><span>RRF 融合</span><i>→</i><span>上下文注入</span><i>→</i><span>LLM 生成</span><i>→</i><span>引用核验</span></div><form class="search-box" @submit.prevent="askRag"><AppIcon name="chat" :size="18" /><input v-model="qaQuestion" placeholder="输入需要依据知识库回答的问题…" /><button class="button small" :disabled="qaRunning || !qaQuestion.trim() || !ragAgents.length" type="submit">{{ qaRunning ? '生成中…' : '开始 RAG 问答' }}</button></form><p v-if="!ragAgents.length" class="lab-warning">请先配置一个绑定此知识库且已设置模型端点的智能体。</p><div v-if="qaEvents.length" class="qa-timeline"><span v-for="event in qaEvents.filter((item) => item.type !== 'model_delta')" :key="String(event.id)">{{ event.type }}</span></div><article v-if="qaAnswer" class="qa-answer"><h3>模型回答</h3><p>{{ qaAnswer }}</p><footer v-if="qaCitations.length"><span v-for="citation in qaCitations" :key="`${citation.document_id}-${citation.chunk_index}`">{{ citation.filename }} · 块 {{ citation.chunk_index }}<template v-if="citation.page"> · 第 {{ citation.page }} 页</template></span></footer></article></section>
        </main>
        <EmptyState v-else-if="isDetail" class="panel" icon="alert" title="知识库不存在" description="该知识库可能已被删除。"><button class="button secondary" @click="backToKnowledgeList">返回列表</button></EmptyState>
      </template>
    </div>

    <ModalDialog :open="createOpen" title="新建知识库" description="文档、OCR 结果与向量将存储在本机 data 目录" @close="createOpen = false"><form class="form-grid" @submit.prevent="createKnowledgeBase"><div class="field full"><label>所属项目</label><select v-model="createForm.project_id" class="select"><option v-for="project in projects.filter((item) => item.status === 'active')" :key="project.id" :value="project.id">{{ project.name }}</option></select></div><div class="field full"><label for="kb-name">名称</label><input id="kb-name" v-model="createForm.name" class="input" maxlength="120" placeholder="例如：产品资料" /></div><div class="field full"><label for="kb-description">说明</label><textarea id="kb-description" v-model="createForm.description" class="textarea" maxlength="4000" placeholder="这个知识库包含哪些内容？" /></div><div class="field full"><label>嵌入模型</label><input v-model="createForm.embedding_model" class="input" /></div><div class="field"><label>分块 Token</label><input v-model.number="createForm.chunk_size" class="input" type="number" min="100" max="4000" /></div><div class="field"><label>重叠 Token</label><input v-model.number="createForm.chunk_overlap" class="input" type="number" min="0" max="1000" /></div><div class="field"><label>Top K</label><input v-model.number="createForm.top_k" class="input" type="number" min="1" max="50" /></div><div class="field"><label>PDF OCR</label><select v-model="createForm.ocr_mode" class="select"><option value="off">关闭</option><option value="auto">扫描页自动识别</option><option value="force">强制识别所有页</option></select></div><div class="field"><label>OCR 语言</label><select v-model="createForm.ocr_language" class="select"><option value="ch">中文 + 英文</option><option value="en">英文</option></select></div></form><template #footer><button class="button secondary" type="button" @click="createOpen = false">取消</button><button class="button" type="button" :disabled="creating" @click="createKnowledgeBase">{{ creating ? '创建中…' : '创建知识库' }}</button></template></ModalDialog>
    <ModalDialog :open="editOpen" title="编辑知识库" description="修改名称、说明和项目不会触发重新索引" @close="editOpen = false"><form class="form-grid" @submit.prevent="updateKnowledgeBase"><div class="field full"><label>所属项目</label><select v-model="editForm.project_id" class="select"><option v-for="project in projects.filter((item) => item.status === 'active')" :key="project.id" :value="project.id">{{ project.name }}</option></select></div><div class="field full"><label for="edit-kb-name">名称</label><input id="edit-kb-name" v-model="editForm.name" class="input" maxlength="120" /></div><div class="field full"><label for="edit-kb-description">说明</label><textarea id="edit-kb-description" v-model="editForm.description" class="textarea" maxlength="4000" rows="5" /></div></form><template #footer><button class="button secondary" type="button" @click="editOpen = false">取消</button><button class="button" type="button" :disabled="saving" @click="updateKnowledgeBase">{{ saving ? '保存中…' : '保存修改' }}</button></template></ModalDialog>
  </div>
</template>

<style scoped>
.metric-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:14px; }
.metric-grid article { display:flex; flex-direction:column; gap:5px; padding:15px 17px; background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); }
.metric-grid span,.summary-grid span { color:var(--muted); font-size:9px; }.metric-grid strong { color:var(--green); font:21px 'DM Mono',monospace; }.metric-grid small,.summary-grid small { color:var(--faint); font-size:8px; }.metric-grid .warning strong { color:var(--orange); }
.kb-toolbar,.document-toolbar { display:flex; align-items:center; gap:8px; padding:10px; margin-bottom:14px; }
.filter-search { display:flex; min-width:260px; flex:1; align-items:center; gap:8px; padding:5px 5px 5px 10px; color:var(--muted); background:#f8f9f5; border:1px solid var(--line-strong); border-radius:10px; }
.filter-search:focus-within { background:#fff; border-color:#70a98d; box-shadow:0 0 0 3px rgba(31,115,84,.07); }.filter-search > input:not([type=checkbox]) { min-width:90px; flex:1; padding:5px; background:transparent; border:0; outline:0; }.exact-check { display:flex; align-items:center; gap:4px; color:var(--muted); font-size:9px; white-space:nowrap; }.compact { width:auto; min-width:112px; }
.back-link { align-self:flex-start; margin:0 0 8px; padding:0; color:var(--green); font-size:10px; background:transparent; border:0; cursor:pointer; }.back-link:hover { text-decoration:underline; }
.kb-table-panel { overflow:hidden; }.knowledge-table th,.knowledge-table td { white-space:nowrap; }.knowledge-table td:first-child { width:38%; white-space:normal; }.kb-name-link { display:flex; width:100%; min-width:250px; align-items:center; gap:10px; padding:2px; color:#1769aa; text-align:left; background:transparent; border:0; cursor:pointer; }.kb-name-link:hover strong { text-decoration:underline; }.kb-name-link > span:last-child { display:flex; min-width:0; flex-direction:column; }.kb-name-link strong { overflow:hidden; color:#1769aa; font-size:11px; text-overflow:ellipsis; white-space:nowrap; }.kb-name-link small { display:block; max-width:440px; margin-top:3px; overflow:hidden; color:var(--muted); font-size:8px; text-overflow:ellipsis; white-space:nowrap; }.kb-link-icon { display:grid; width:32px; height:32px; flex:0 0 32px; place-items:center; color:#1769aa; background:#edf6fc; border-radius:8px; }
.heading-actions { display:flex; align-items:center; gap:8px; }
.knowledge-layout { display:grid; grid-template-columns:285px minmax(0,1fr); gap:15px; align-items:start; }.kb-list { position:sticky; top:20px; overflow:hidden; padding:8px; }.kb-list-head { display:flex; align-items:center; justify-content:space-between; padding:9px 8px 11px; color:var(--muted); font-size:10px; }.kb-list-head strong { display:grid; min-width:21px; height:21px; place-items:center; color:var(--green); font:9px 'DM Mono',monospace; background:var(--green-soft); border-radius:7px; }
.kb-item { display:flex; width:100%; align-items:center; gap:8px; padding:9px; color:var(--muted); text-align:left; background:transparent; border:1px solid transparent; border-radius:10px; cursor:pointer; }.kb-item:hover { background:#f7f8f4; }.kb-item.active { color:var(--ink); background:var(--green-soft); border-color:#d8eade; }.kb-item-icon { display:grid; width:31px; height:31px; flex:0 0 31px; place-items:center; color:var(--green); background:#fff; border-radius:8px; }.kb-item-copy { display:flex; min-width:0; flex:1; flex-direction:column; }.kb-item-copy strong { overflow:hidden; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }.kb-item-copy small { margin-top:3px; color:var(--muted); font-size:8px; }.kb-item :deep(.status-badge) { font-size:7px; }
.mini-loading { display:flex; align-items:center; justify-content:center; gap:8px; min-height:90px; color:var(--muted); font-size:9px; }.mini-loading .spinner { width:16px; height:16px; margin:0; }.kb-content { display:grid; min-width:0; gap:14px; }
.kb-overview { display:flex; align-items:center; justify-content:space-between; gap:20px; }.kb-overview > div:first-child { display:flex; min-width:0; align-items:center; gap:13px; }.overview-mark { display:grid; width:45px; height:45px; flex:0 0 45px; place-items:center; color:var(--green); background:var(--green-soft); border-radius:12px; }.title-line { display:flex; align-items:center; gap:8px; }.kb-overview h2 { margin:0; font-size:16px; }.kb-overview p { margin:4px 0; color:var(--muted); font-size:10px; }.kb-overview small { color:var(--faint); font:7px 'DM Mono',monospace; }.overview-actions { display:flex; gap:7px; }
.detail-tabs { display:flex; gap:3px; padding:5px; }.detail-tabs button { position:relative; display:flex; flex:1; align-items:center; justify-content:center; gap:6px; min-height:36px; color:var(--muted); font-size:10px; background:transparent; border:0; border-radius:8px; cursor:pointer; }.detail-tabs button:hover { background:#f7f8f4; }.detail-tabs button.active { color:var(--green); font-weight:650; background:var(--green-soft); }.detail-tabs span { display:grid; min-width:18px; height:18px; place-items:center; font:7px 'DM Mono',monospace; background:#fff; border-radius:6px; }
.summary-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }.summary-grid article { display:flex; flex-direction:column; gap:5px; padding:15px; }.summary-grid strong { color:var(--ink); font:16px 'DM Mono',monospace; }
.upload-section { padding:8px; }.drop-zone { display:flex; min-height:88px; align-items:center; gap:13px; padding:15px; background:#f8faf5; border:1px dashed #bdcbbd; border-radius:10px; transition:.15s; }.drop-zone.dragging { background:var(--green-soft); border-color:var(--green); transform:scale(.995); }.drop-zone.busy { cursor:wait; }.upload-icon { display:grid; width:39px; height:39px; flex:0 0 39px; place-items:center; color:var(--green); background:#fff; border:1px solid #e1e8df; border-radius:10px; }.drop-zone > div { display:flex; min-width:0; flex:1; flex-direction:column; }.drop-zone strong { font-size:11px; }.drop-zone span { margin-top:4px; color:var(--muted); font-size:9px; }
.section-bar { display:flex; align-items:center; justify-content:space-between; padding:16px 18px 12px; border-bottom:1px solid var(--line); }.section-bar h2 { margin:0; font-size:13px; }.section-bar p { margin:4px 0 0; color:var(--muted); font-size:9px; }.document-toolbar { margin:0; border-bottom:1px solid var(--line); border-radius:0; }.config-grid { display:grid; grid-template-columns:2fr repeat(3,1fr) auto; gap:9px; align-items:end; }.mode-select { width:130px; }
.rag-flow { display:flex; align-items:center; justify-content:center; gap:7px; margin:12px 0; padding:12px; overflow:auto; color:var(--green); background:var(--green-soft); border-radius:10px; white-space:nowrap; }.rag-flow span { padding:5px 8px; font-size:8px; background:#fff; border-radius:7px; }.rag-flow i { color:var(--faint); font-style:normal; }.lab-warning { color:var(--orange); font-size:9px; }.qa-timeline { display:flex; flex-wrap:wrap; gap:5px; margin-top:10px; }.qa-timeline span { padding:4px 7px; color:var(--muted); font:8px 'DM Mono',monospace; background:#f4f6f2; border-radius:6px; }.qa-answer { margin-top:12px; padding:14px; border:1px solid var(--line); border-radius:10px; }.qa-answer h3 { margin:0 0 8px; font-size:11px; }.qa-answer p { margin:0; font-size:10px; line-height:1.75; white-space:pre-wrap; }.qa-answer footer { display:flex; flex-wrap:wrap; gap:6px; margin-top:11px; }.qa-answer footer span { padding:4px 7px; color:var(--green); font-size:8px; background:var(--green-soft); border-radius:6px; }
.file-cell { display:flex; min-width:190px; align-items:center; gap:9px; }.file-cell i { display:grid; width:30px; height:30px; flex:0 0 30px; place-items:center; color:var(--green); background:var(--green-soft); border-radius:8px; }.file-cell > span { display:flex; min-width:0; max-width:290px; flex-direction:column; }.file-cell strong { overflow:hidden; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }.file-cell small { overflow:hidden; margin-top:2px; color:var(--faint); font:7px 'DM Mono',monospace; text-overflow:ellipsis; white-space:nowrap; }.delete-document:hover { color:var(--red); background:var(--red-soft); }
.search-box { display:flex; align-items:center; gap:9px; padding:7px 7px 7px 11px; color:var(--muted); background:#f8f9f5; border:1px solid var(--line-strong); border-radius:11px; }.search-box:focus-within { background:#fff; border-color:#70a98d; box-shadow:0 0 0 3px rgba(31,115,84,.07); }.search-box input { min-width:0; flex:1; padding:4px; background:transparent; border:0; outline:none; }.search-loading { display:flex; min-height:100px; align-items:center; justify-content:center; gap:10px; color:var(--muted); font-size:10px; }.search-loading .spinner { width:17px; height:17px; margin:0; }.result-list { display:grid; gap:8px; margin-top:13px; }.result-card { display:grid; grid-template-columns:31px minmax(0,1fr); gap:10px; padding:12px; background:#fafbf8; border:1px solid var(--line); border-radius:10px; }.result-rank { display:grid; width:29px; height:29px; place-items:center; color:var(--green); font:8px 'DM Mono',monospace; background:var(--green-soft); border-radius:8px; }.result-card header { display:flex; min-width:0; align-items:center; gap:8px; }.result-card header strong { overflow:hidden; font-size:10px; text-overflow:ellipsis; white-space:nowrap; }.result-card header span { color:var(--faint); font-size:8px; white-space:nowrap; }.result-card header em { margin-left:auto; color:var(--green); font:8px 'DM Mono',monospace; font-style:normal; }.result-card p { margin:7px 0 0; color:#565c55; font-size:10px; line-height:1.65; white-space:pre-wrap; }
.pager { display:flex; align-items:center; justify-content:space-between; padding:11px 16px; color:var(--muted); font-size:9px; border-top:1px solid var(--line); }.pager div,.compact-pager { display:flex; align-items:center; gap:7px; }.pager button { min-height:27px; padding:4px 9px; color:var(--ink); font-size:9px; background:#fff; border:1px solid var(--line-strong); border-radius:7px; cursor:pointer; }.pager button:disabled { cursor:not-allowed; opacity:.4; }.pager b { font:8px 'DM Mono',monospace; }.compact-pager { justify-content:center; margin-top:6px; padding:8px 3px 3px; }.compact-pager span { min-width:45px; text-align:center; }
@media (max-width:1050px) { .metric-grid,.summary-grid { grid-template-columns:1fr 1fr; }.kb-toolbar,.document-toolbar { flex-wrap:wrap; }.filter-search { flex-basis:100%; }.knowledge-table th:nth-child(5),.knowledge-table td:nth-child(5),.knowledge-table th:nth-child(6),.knowledge-table td:nth-child(6) { display:none; } }
@media (max-width:920px) { .knowledge-layout { grid-template-columns:1fr; }.kb-list { position:static; }.kb-item { display:inline-flex; width:calc(50% - 3px); }.kb-item:nth-of-type(even) { margin-left:6px; } }
@media (max-width:760px) { .config-grid { grid-template-columns:1fr 1fr; }.config-grid .wide { grid-column:1/-1; }.config-grid .button { grid-column:1/-1; }.detail-tabs { overflow-x:auto; }.detail-tabs button { min-width:100px; }.kb-overview { align-items:flex-start; }.overview-actions { flex-direction:column; } }
@media (max-width:600px) { .metric-grid,.summary-grid { grid-template-columns:1fr 1fr; }.kb-item { width:100%; }.kb-item:nth-of-type(even) { margin-left:0; }.exact-check { display:none; }.heading-actions { align-items:flex-end; flex-direction:column; }.drop-zone { align-items:flex-start; flex-wrap:wrap; }.drop-zone .button { margin-left:52px; }.document-table th:nth-child(2),.document-table td:nth-child(2),.document-table th:nth-child(5),.document-table td:nth-child(5),.knowledge-table th:nth-child(3),.knowledge-table td:nth-child(3),.knowledge-table th:nth-child(4),.knowledge-table td:nth-child(4),.knowledge-table th:nth-child(7),.knowledge-table td:nth-child(7) { display:none; } }
</style>
