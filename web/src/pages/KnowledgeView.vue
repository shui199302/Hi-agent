<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { formatApiError, jsonBody, listOf, openRunEventStream, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { notify } from '../notifications'
import type { AgentConfig, Citation, DocumentItem, KnowledgeBase, RunEvent, RunResponse, SearchResult } from '../types'

const knowledgeBases = ref<KnowledgeBase[]>([])
const documents = ref<DocumentItem[]>([])
const selectedId = ref('')
const loading = ref(true)
const documentsLoading = ref(false)
const loadError = ref('')
const createOpen = ref(false)
const creating = ref(false)
const uploadBusy = ref(false)
const dragging = ref(false)
const searchQuery = ref('')
const searching = ref(false)
const searchResults = ref<SearchResult[]>([])
const searched = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const createForm = reactive({ name: '', description: '', embedding_model: 'BAAI/bge-small-zh-v1.5', chunk_size: 800, chunk_overlap: 120, top_k: 5 })
const indexForm = reactive({ embedding_model: '', chunk_size: 800, chunk_overlap: 120, top_k: 5 })
const reindexing = ref(false)
const retrievalMode = ref<'dense' | 'lexical' | 'hybrid'>('hybrid')
const agents = ref<AgentConfig[]>([])
const qaQuestion = ref('')
const qaAnswer = ref('')
const qaRunning = ref(false)
const qaEvents = ref<RunEvent[]>([])
const qaCitations = ref<Citation[]>([])
let qaSource: EventSource | null = null

const selected = computed(() => knowledgeBases.value.find((item) => item.id === selectedId.value) ?? null)
const ragAgents = computed(() => agents.value.filter((agent) => agent.knowledge_base_id === selectedId.value && agent.enabled !== false && agent.model_endpoint_id))

function syncIndexForm(): void {
  if (!selected.value) return
  Object.assign(indexForm, { embedding_model: selected.value.embedding_model || 'BAAI/bge-small-zh-v1.5', chunk_size: selected.value.chunk_size || 800, chunk_overlap: selected.value.chunk_overlap ?? 120, top_k: selected.value.top_k || 5 })
}

function bytes(value?: number): string {
  if (!value) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function date(value?: string): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

async function loadKnowledgeBases(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const [data, agentData] = await Promise.all([request<KnowledgeBase[] | { items: KnowledgeBase[] }>('/knowledge-bases'), request<AgentConfig[] | { items: AgentConfig[] }>('/agents')])
    knowledgeBases.value = listOf(data)
    agents.value = listOf(agentData)
    if (!knowledgeBases.value.some((item) => item.id === selectedId.value)) {
      selectedId.value = knowledgeBases.value[0]?.id ?? ''
    }
    if (selectedId.value) await loadDocuments()
    syncIndexForm()
  } catch (error) {
    loadError.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

async function loadDocuments(): Promise<void> {
  if (!selectedId.value) {
    documents.value = []
    return
  }
  documentsLoading.value = true
  try {
    const data = await request<DocumentItem[] | { items: DocumentItem[] }>(`/knowledge-bases/${selectedId.value}/documents`)
    documents.value = listOf(data)
  } catch (error) {
    notify(formatApiError(error), 'error')
    documents.value = []
  } finally {
    documentsLoading.value = false
  }
}

async function chooseKnowledgeBase(id: string): Promise<void> {
  selectedId.value = id
  searchResults.value = []
  searched.value = false
  qaAnswer.value = ''
  qaEvents.value = []
  await loadDocuments()
  syncIndexForm()
}

async function createKnowledgeBase(): Promise<void> {
  if (!createForm.name.trim()) {
    notify('请填写知识库名称', 'error')
    return
  }
  creating.value = true
  try {
    const created = await request<KnowledgeBase>('/knowledge-bases', {
      method: 'POST',
      ...jsonBody({ ...createForm, name: createForm.name.trim(), description: createForm.description.trim() }),
    })
    createOpen.value = false
    Object.assign(createForm, { name: '', description: '', embedding_model: 'BAAI/bge-small-zh-v1.5', chunk_size: 800, chunk_overlap: 120, top_k: 5 })
    notify('知识库已创建', 'success')
    await loadKnowledgeBases()
    selectedId.value = created.id
    await loadDocuments()
  } catch (error) {
    notify(formatApiError(error), 'error')
  } finally {
    creating.value = false
  }
}

async function deleteKnowledgeBase(): Promise<void> {
  if (!selected.value || !window.confirm(`确认删除知识库“${selected.value.name}”及其全部文档和向量？此操作无法撤销。`)) return
  try {
    await request<void>(`/knowledge-bases/${selected.value.id}`, { method: 'DELETE' })
    notify('知识库已删除', 'success')
    selectedId.value = ''
    await loadKnowledgeBases()
  } catch (error) {
    notify(formatApiError(error), 'error')
  }
}

async function upload(files: FileList | File[]): Promise<void> {
  if (!selectedId.value || files.length === 0) return
  const allowed = new Set(['pdf', 'docx', 'md', 'markdown', 'txt'])
  const list = Array.from(files)
  const invalid = list.find((file) => !allowed.has(file.name.split('.').pop()?.toLowerCase() ?? '') || file.size > 50 * 1024 * 1024)
  if (invalid) {
    notify(`“${invalid.name}”格式不支持或超过 50 MB`, 'error')
    return
  }
  uploadBusy.value = true
  let completed = 0
  for (const file of list) {
    const body = new FormData()
    body.append('file', file, file.name)
    try {
      await request<DocumentItem>(`/knowledge-bases/${selectedId.value}/documents`, { method: 'POST', body })
      completed += 1
    } catch (error) {
      notify(`${file.name}：${formatApiError(error)}`, 'error')
    }
  }
  if (completed) notify(`${completed} 个文档已上传并进入索引`, 'success')
  uploadBusy.value = false
  if (fileInput.value) fileInput.value.value = ''
  await loadDocuments()
  await refreshKbCounts()
}

async function refreshKbCounts(): Promise<void> {
  try {
    const data = await request<KnowledgeBase[] | { items: KnowledgeBase[] }>('/knowledge-bases')
    knowledgeBases.value = listOf(data)
  } catch { /* document list remains usable */ }
}

function dropped(event: DragEvent): void {
  dragging.value = false
  if (event.dataTransfer?.files) void upload(event.dataTransfer.files)
}

async function deleteDocument(document: DocumentItem): Promise<void> {
  if (!window.confirm(`删除“${document.filename}”及其全部向量？`)) return
  try {
    await request<void>(`/documents/${document.id}`, { method: 'DELETE' })
    notify('文档与向量已删除', 'success')
    await loadDocuments()
    await refreshKbCounts()
  } catch (error) {
    notify(formatApiError(error), 'error')
  }
}

async function search(): Promise<void> {
  if (!selectedId.value || !searchQuery.value.trim()) return
  searching.value = true
  searched.value = true
  try {
    const data = await request<{ items: SearchResult[] } | SearchResult[]>(`/knowledge-bases/${selectedId.value}/search`, {
      method: 'POST',
      ...jsonBody({ query: searchQuery.value.trim(), top_k: selected.value?.top_k || 5, mode: retrievalMode.value }),
    })
    searchResults.value = listOf(data)
  } catch (error) {
    notify(formatApiError(error), 'error')
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

async function rebuildIndex(): Promise<void> {
  if (!selected.value || !window.confirm('确认按新配置重建全部文档索引？重建期间该知识库暂不可检索。')) return
  reindexing.value = true
  try {
    await request(`/knowledge-bases/${selected.value.id}/reindex`, { method: 'POST', ...jsonBody(indexForm) })
    notify('索引已按新配置重建', 'success')
    await loadKnowledgeBases()
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { reindexing.value = false }
}

async function askRag(): Promise<void> {
  const agent = ragAgents.value[0]
  if (!agent || !qaQuestion.value.trim() || qaRunning.value) return
  qaAnswer.value = ''
  qaEvents.value = []
  qaCitations.value = []
  qaRunning.value = true
  try {
    const session = await request<{ id: string }>('/sessions', { method: 'POST', ...jsonBody({ title: `RAG 实验：${qaQuestion.value.trim().slice(0, 30)}`, agent_id: agent.id }) })
    const accepted = await request<RunResponse>(`/sessions/${session.id}/runs`, { method: 'POST', ...jsonBody({ message: qaQuestion.value.trim() }) })
    qaSource?.close()
    qaSource = openRunEventStream(accepted.events_url, { onEvent: (event) => {
      qaEvents.value.push(event)
      if (event.type === 'model_delta') qaAnswer.value += String(event.data.content ?? '')
      if (event.type === 'retrieval' && Array.isArray(event.data.items)) qaCitations.value = event.data.items as unknown as Citation[]
      if (event.type === 'completed') { qaAnswer.value = String(event.data.output ?? qaAnswer.value); qaRunning.value = false; qaSource?.close() }
      if (event.type === 'failed' || event.type === 'cancelled') { qaAnswer.value += `\n\n[${event.type === 'failed' ? '运行失败' : '已取消'}] ${String(event.data.message ?? '')}`; qaRunning.value = false; qaSource?.close() }
    } })
  } catch (error) { qaRunning.value = false; notify(formatApiError(error), 'error') }
}

onMounted(loadKnowledgeBases)
onActivated(() => { if (!loading.value) void loadKnowledgeBases() })
onBeforeUnmount(() => qaSource?.close())
</script>

<template>
  <div class="page">
    <div class="page-inner">
      <header class="page-header">
        <div class="page-title-group">
          <div class="eyebrow">Retrieval · BGE + Qdrant</div>
          <h1>知识库</h1>
          <p>把 PDF、DOCX、Markdown 与文本变成可检索的上下文。检索结果会保留文件、页码和块编号引用。</p>
        </div>
        <div class="page-actions">
          <button class="button" type="button" @click="createOpen = true"><AppIcon name="plus" :size="16" />新建知识库</button>
        </div>
      </header>

      <LoadingState v-if="loading" :rows="4" />
      <EmptyState v-else-if="loadError" icon="alert" title="无法加载知识库" :description="loadError">
        <button class="button secondary" type="button" @click="loadKnowledgeBases">重新连接</button>
      </EmptyState>
      <EmptyState v-else-if="knowledgeBases.length === 0" icon="database" title="从一个知识库开始" description="文档与向量只保存在本机，支持按内容哈希自动去重。">
        <button class="button" type="button" @click="createOpen = true"><AppIcon name="plus" :size="16" />创建知识库</button>
      </EmptyState>
      <div v-else class="knowledge-layout">
        <aside class="kb-list panel">
          <div class="kb-list-head">
            <span>知识库</span>
            <strong>{{ knowledgeBases.length }}</strong>
          </div>
          <button
            v-for="kb in knowledgeBases"
            :key="kb.id"
            class="kb-item"
            :class="{ active: selectedId === kb.id }"
            type="button"
            @click="chooseKnowledgeBase(kb.id)"
          >
            <span class="kb-item-icon"><AppIcon name="database" :size="17" /></span>
            <span class="kb-item-copy"><strong>{{ kb.name }}</strong><small>{{ kb.document_count ?? 0 }} 文档 · {{ kb.chunk_count ?? 0 }} 分块</small></span>
            <AppIcon name="chevron" :size="14" />
          </button>
        </aside>

        <div v-if="selected" class="kb-content">
          <section class="panel panel-padded kb-overview">
            <div>
              <span class="overview-mark"><AppIcon name="database" :size="22" /></span>
              <div>
                <h2>{{ selected.name }}</h2>
                <p>{{ selected.description || '未填写说明' }}</p>
              </div>
            </div>
            <div class="overview-actions">
              <button class="button danger small" type="button" @click="deleteKnowledgeBase"><AppIcon name="trash" :size="14" />删除</button>
            </div>
          </section>

          <section class="panel upload-section">
            <div
              class="drop-zone"
              :class="{ dragging, busy: uploadBusy }"
              @dragenter.prevent="dragging = true"
              @dragover.prevent
              @dragleave.prevent="dragging = false"
              @drop.prevent="dropped"
            >
              <span v-if="uploadBusy" class="spinner" />
              <span v-else class="upload-icon"><AppIcon name="upload" :size="21" /></span>
              <div>
                <strong>{{ uploadBusy ? '正在解析并索引文档…' : '拖入文档，或点击选择文件' }}</strong>
                <span>PDF · DOCX · Markdown · TXT，单文件不超过 50 MB</span>
              </div>
              <button v-if="!uploadBusy" class="button secondary small" type="button" @click="fileInput?.click()">选择文件</button>
              <input ref="fileInput" type="file" hidden multiple accept=".pdf,.docx,.md,.markdown,.txt" @change="($event.target as HTMLInputElement).files && upload(($event.target as HTMLInputElement).files!)" />
            </div>
          </section>

          <section class="panel panel-padded index-config">
            <div class="section-heading"><div><h2>向量索引配置</h2><p>修改配置会重建全部文档；默认使用 Dense + BM25 + RRF 混合召回</p></div><StatusBadge status="ready" label="HYBRID" /></div>
            <div class="config-grid">
              <div class="field wide"><label>嵌入模型</label><input v-model="indexForm.embedding_model" class="input" /></div>
              <div class="field"><label>分块 Token</label><input v-model.number="indexForm.chunk_size" class="input" type="number" min="100" max="4000" /></div>
              <div class="field"><label>重叠 Token</label><input v-model.number="indexForm.chunk_overlap" class="input" type="number" min="0" max="1000" /></div>
              <div class="field"><label>Top K</label><input v-model.number="indexForm.top_k" class="input" type="number" min="1" max="50" /></div>
              <button class="button secondary" :disabled="reindexing" type="button" @click="rebuildIndex">{{ reindexing ? '正在重建…' : '保存并重建' }}</button>
            </div>
          </section>

          <section class="panel">
            <div class="section-bar">
              <div><h2>文档</h2><p>删除文档时会同步清理它的向量</p></div>
              <StatusBadge status="indexed" :label="`${documents.length} 个文件`" />
            </div>
            <LoadingState v-if="documentsLoading" :rows="2" />
            <EmptyState v-else-if="documents.length === 0" icon="file" title="这里还没有文档" description="上传后会自动分块、嵌入并写入 Qdrant。" />
            <div v-else class="table-wrap">
              <table class="data-table document-table">
                <thead><tr><th>文件</th><th>大小</th><th>分块</th><th>状态</th><th>添加时间</th><th /></tr></thead>
                <tbody>
                  <tr v-for="document in documents" :key="document.id">
                    <td><span class="file-cell"><i><AppIcon name="file" :size="16" /></i><span><strong>{{ document.filename }}</strong><small>{{ document.media_type || document.filename.split('.').pop()?.toUpperCase() }}</small></span></span></td>
                    <td>{{ bytes(document.size_bytes ?? document.size) }}</td>
                    <td>{{ document.chunk_count ?? '—' }}</td>
                    <td><StatusBadge :status="document.status || 'indexed'" /></td>
                    <td>{{ date(document.created_at) }}</td>
                    <td><button class="icon-button delete-document" type="button" aria-label="删除文档" @click="deleteDocument(document)"><AppIcon name="trash" :size="15" /></button></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="panel panel-padded search-panel">
            <div class="section-heading"><div><h2>检索试验台</h2><p>检查各检索通道、融合分数和召回片段，不调用大语言模型</p></div><select v-model="retrievalMode" class="input mode-select"><option value="hybrid">混合检索</option><option value="dense">语义向量</option><option value="lexical">BM25 关键词</option></select></div>
            <form class="search-box" @submit.prevent="search">
              <AppIcon name="search" :size="18" />
              <input v-model="searchQuery" placeholder="输入一个问题，检查知识库召回…" />
              <button class="button small" type="submit" :disabled="searching || !searchQuery.trim()">{{ searching ? '检索中…' : '检索' }}</button>
            </form>
            <div v-if="searching" class="search-loading"><span class="spinner" /> 正在计算查询向量…</div>
            <EmptyState v-else-if="searched && searchResults.length === 0" icon="search" title="没有找到相关片段" description="可以换一种问法，或确认文档索引已完成。" />
            <div v-else-if="searchResults.length" class="result-list">
              <article v-for="(result, index) in searchResults" :key="`${result.document_id}-${result.chunk_index}`" class="result-card">
                <span class="result-rank">{{ String(index + 1).padStart(2, '0') }}</span>
                <div>
                  <header><strong>{{ result.filename }}</strong><span>块 {{ result.chunk_index }}<template v-if="result.page"> · 第 {{ result.page }} 页</template> · {{ result.channels?.join(' + ') || retrievalMode }}</span><em>{{ (result.score * 100).toFixed(1) }}%</em></header>
                  <p>{{ result.content }}</p>
                </div>
              </article>
            </div>
          </section>

          <section class="panel panel-padded rag-lab">
            <div class="section-heading"><div><h2>RAG 问答实验台</h2><p>运行检索、上下文组装、模型生成与引用持久化的完整链路</p></div><StatusBadge :status="qaRunning ? 'running' : 'ready'" :label="qaRunning ? '运行中' : '可观测'" /></div>
            <div class="rag-flow"><span>问题分析</span><i>→</i><span>Dense / BM25</span><i>→</i><span>RRF 融合</span><i>→</i><span>上下文注入</span><i>→</i><span>LLM 生成</span><i>→</i><span>引用核验</span></div>
            <form class="search-box" @submit.prevent="askRag"><AppIcon name="chat" :size="18" /><input v-model="qaQuestion" placeholder="输入需要依据知识库回答的问题…" /><button class="button small" :disabled="qaRunning || !qaQuestion.trim() || !ragAgents.length" type="submit">{{ qaRunning ? '生成中…' : '开始 RAG 问答' }}</button></form>
            <p v-if="!ragAgents.length" class="lab-warning">请先配置一个绑定此知识库且已设置模型端点的智能体。</p>
            <div v-if="qaEvents.length" class="qa-timeline"><span v-for="event in qaEvents.filter((item) => item.type !== 'model_delta')" :key="String(event.id)">{{ event.type }}</span></div>
            <article v-if="qaAnswer" class="qa-answer"><h3>模型回答</h3><p>{{ qaAnswer }}</p><footer v-if="qaCitations.length"><span v-for="citation in qaCitations" :key="`${citation.document_id}-${citation.chunk_index}`">{{ citation.filename }} · 块 {{ citation.chunk_index }}<template v-if="citation.page"> · 第 {{ citation.page }} 页</template></span></footer></article>
          </section>
        </div>
      </div>
    </div>

    <ModalDialog :open="createOpen" title="新建知识库" description="文档与向量将存储在本机 data 目录" @close="createOpen = false">
      <form class="form-grid" @submit.prevent="createKnowledgeBase">
        <div class="field full"><label for="kb-name">名称</label><input id="kb-name" v-model="createForm.name" class="input" maxlength="80" placeholder="例如：产品资料" /></div>
        <div class="field full"><label for="kb-description">说明</label><textarea id="kb-description" v-model="createForm.description" class="textarea" maxlength="300" placeholder="这个知识库包含哪些内容？" /></div>
        <div class="field full"><label>嵌入模型</label><input v-model="createForm.embedding_model" class="input" /></div>
        <div class="field"><label>分块 Token</label><input v-model.number="createForm.chunk_size" class="input" type="number" min="100" max="4000" /></div>
        <div class="field"><label>重叠 Token</label><input v-model.number="createForm.chunk_overlap" class="input" type="number" min="0" max="1000" /></div>
        <div class="field"><label>Top K</label><input v-model.number="createForm.top_k" class="input" type="number" min="1" max="50" /></div>
      </form>
      <template #footer>
        <button class="button secondary" type="button" @click="createOpen = false">取消</button>
        <button class="button" type="button" :disabled="creating" @click="createKnowledgeBase">{{ creating ? '创建中…' : '创建知识库' }}</button>
      </template>
    </ModalDialog>
  </div>
</template>

<style scoped>
.knowledge-layout { display: grid; grid-template-columns: 225px minmax(0, 1fr); gap: 15px; align-items: start; }
.kb-list { position: sticky; top: 20px; overflow: hidden; padding: 8px; }
.kb-list-head { display: flex; align-items: center; justify-content: space-between; padding: 9px 8px 11px; color: var(--muted); font-size: 10px; }
.kb-list-head strong { display: grid; min-width: 21px; height: 21px; place-items: center; color: var(--green); font-family: 'DM Mono', monospace; font-size: 9px; background: var(--green-soft); border-radius: 7px; }
.kb-item { display: flex; width: 100%; align-items: center; gap: 9px; padding: 9px; color: var(--muted); text-align: left; background: transparent; border: 1px solid transparent; border-radius: 10px; cursor: pointer; }
.kb-item:hover { background: #f7f8f4; }
.kb-item.active { color: var(--ink); background: var(--green-soft); border-color: #d8eade; }
.kb-item-icon { display: grid; width: 31px; height: 31px; flex: 0 0 31px; place-items: center; color: var(--green); background: #fff; border-radius: 8px; }
.kb-item-copy { display: flex; min-width: 0; flex: 1; flex-direction: column; }
.kb-item-copy strong { overflow: hidden; font-size: 10px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.kb-item-copy small { margin-top: 3px; color: var(--muted); font-size: 8px; }
.kb-content { display: grid; min-width: 0; gap: 14px; }
.kb-overview { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.kb-overview > div:first-child { display: flex; min-width: 0; align-items: center; gap: 13px; }
.overview-mark { display: grid; width: 45px; height: 45px; flex: 0 0 45px; place-items: center; color: var(--green); background: var(--green-soft); border-radius: 12px; }
.kb-overview h2 { margin: 0; font-size: 16px; }
.kb-overview p { margin: 4px 0 0; color: var(--muted); font-size: 10px; }
.upload-section { padding: 8px; }
.drop-zone { display: flex; min-height: 88px; align-items: center; gap: 13px; padding: 15px; background: #f8faf5; border: 1px dashed #bdcbbd; border-radius: 10px; transition: .15s; }
.drop-zone.dragging { background: var(--green-soft); border-color: var(--green); transform: scale(.995); }
.drop-zone.busy { cursor: wait; }
.upload-icon { display: grid; width: 39px; height: 39px; flex: 0 0 39px; place-items: center; color: var(--green); background: #fff; border: 1px solid #e1e8df; border-radius: 10px; }
.drop-zone > div { display: flex; min-width: 0; flex: 1; flex-direction: column; }
.drop-zone strong { font-size: 11px; }
.drop-zone span { margin-top: 4px; color: var(--muted); font-size: 9px; }
.section-bar { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px 12px; border-bottom: 1px solid var(--line); }
.section-bar h2 { margin: 0; font-size: 13px; }
.section-bar p { margin: 4px 0 0; color: var(--muted); font-size: 9px; }
.config-grid { display: grid; grid-template-columns: 2fr repeat(3,1fr) auto; gap: 9px; align-items: end; }
.mode-select { width: 130px; }
.rag-flow { display: flex; align-items: center; justify-content: center; gap: 7px; margin: 12px 0; padding: 12px; overflow: auto; color: var(--green); background: var(--green-soft); border-radius: 10px; white-space: nowrap; }
.rag-flow span { padding: 5px 8px; font-size: 8px; background: #fff; border-radius: 7px; }
.rag-flow i { color: var(--faint); font-style: normal; }
.lab-warning { color: var(--orange); font-size: 9px; }
.qa-timeline { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 10px; }
.qa-timeline span { padding: 4px 7px; color: var(--muted); font: 8px 'DM Mono',monospace; background: #f4f6f2; border-radius: 6px; }
.qa-answer { margin-top: 12px; padding: 14px; border: 1px solid var(--line); border-radius: 10px; }
.qa-answer h3 { margin: 0 0 8px; font-size: 11px; }
.qa-answer p { margin: 0; font-size: 10px; line-height: 1.75; white-space: pre-wrap; }
.qa-answer footer { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 11px; }
.qa-answer footer span { padding: 4px 7px; color: var(--green); font-size: 8px; background: var(--green-soft); border-radius: 6px; }
.file-cell { display: flex; min-width: 190px; align-items: center; gap: 9px; }
.file-cell i { display: grid; width: 30px; height: 30px; flex: 0 0 30px; place-items: center; color: var(--green); background: var(--green-soft); border-radius: 8px; }
.file-cell > span { display: flex; min-width: 0; max-width: 210px; flex-direction: column; }
.file-cell strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.file-cell small { margin-top: 2px; color: var(--faint); font-family: 'DM Mono', monospace; font-size: 7px; }
.delete-document:hover { color: var(--red); background: var(--red-soft); }
.search-box { display: flex; align-items: center; gap: 9px; padding: 7px 7px 7px 11px; color: var(--muted); background: #f8f9f5; border: 1px solid var(--line-strong); border-radius: 11px; }
.search-box:focus-within { background: #fff; border-color: #70a98d; box-shadow: 0 0 0 3px rgba(31,115,84,.07); }
.search-box input { min-width: 0; flex: 1; padding: 4px; background: transparent; border: 0; outline: none; }
.search-loading { display: flex; min-height: 100px; align-items: center; justify-content: center; gap: 10px; color: var(--muted); font-size: 10px; }
.search-loading .spinner { width: 17px; height: 17px; margin: 0; }
.result-list { display: grid; gap: 8px; margin-top: 13px; }
.result-card { display: grid; grid-template-columns: 31px minmax(0,1fr); gap: 10px; padding: 12px; background: #fafbf8; border: 1px solid var(--line); border-radius: 10px; }
.result-rank { display: grid; width: 29px; height: 29px; place-items: center; color: var(--green); font-family: 'DM Mono', monospace; font-size: 8px; background: var(--green-soft); border-radius: 8px; }
.result-card header { display: flex; min-width: 0; align-items: center; gap: 8px; }
.result-card header strong { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.result-card header span { color: var(--faint); font-size: 8px; white-space: nowrap; }
.result-card header em { margin-left: auto; color: var(--green); font-family: 'DM Mono', monospace; font-size: 8px; font-style: normal; }
.result-card p { margin: 7px 0 0; color: #565c55; font-size: 10px; line-height: 1.65; white-space: pre-wrap; }
@media (max-width: 920px) { .knowledge-layout { grid-template-columns: 1fr; } .kb-list { position: static; display: flex; overflow-x: auto; gap: 6px; } .kb-list-head { display: none; } .kb-item { min-width: 190px; width: auto; } }
@media (max-width: 900px) { .config-grid { grid-template-columns: 1fr 1fr; } .config-grid .wide { grid-column: 1/-1; } }
@media (max-width: 600px) { .drop-zone { align-items: flex-start; flex-wrap: wrap; } .drop-zone .button { margin-left: 52px; } .kb-overview { align-items: flex-start; } .document-table th:nth-child(2), .document-table td:nth-child(2), .document-table th:nth-child(5), .document-table td:nth-child(5) { display:none; } }
</style>
