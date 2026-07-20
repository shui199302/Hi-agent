<script setup lang="ts">
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { formatApiError, jsonBody, listOf, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { notify } from '../notifications'
import type { ImageEndpoint, ModelEndpoint, SystemStatus } from '../types'

const models = ref<ModelEndpoint[]>([])
const imageEndpoints = ref<ImageEndpoint[]>([])
const status = ref<SystemStatus | null>(null)
const loading = ref(true)
const loadError = ref('')
const modalOpen = ref(false)
const saving = ref(false)
const editingId = ref<string | null>(null)
const lastRefresh = ref<Date | null>(null)
const imageModalOpen = ref(false)
const imageSaving = ref(false)
const editingImageId = ref<string | null>(null)
const imageForm = reactive({ name: '', base_url: 'https://api.openai.com/v1', model: 'gpt-image-1', api_key_env: 'OPENAI_API_KEY', timeout_seconds: 180, enabled: true })

const form = reactive({
  name: '', base_url: 'http://127.0.0.1:8000/v1', model: '', api_key_env: 'HI_AGENT_LLM_API_KEY',
  timeout_seconds: 120, enabled: true, mock: false,
})

const statusCards = computed(() => [
  { label: 'API 与数据库', value: status.value?.database || (status.value?.status === 'ok' ? 'ready' : 'unknown'), icon: 'server', detail: 'SQLite WAL 元数据' },
  { label: '嵌入后端', value: status.value?.embedding_backend || 'unknown', icon: 'database', detail: 'BGE / 确定性测试后端' },
  { label: '模型配置', value: status.value?.model_configured ? 'ready' : 'unconfigured', icon: 'sparkles', detail: `${models.value.filter((item) => item.enabled).length} 个启用端点` },
  { label: '活动运行', value: (status.value?.active_runs ?? 0) > 0 ? 'running' : 'ready', icon: 'activity', detail: `${status.value?.active_runs ?? 0} active · ${status.value?.interrupted_runs ?? 0} interrupted` },
])

function openCreate(): void {
  editingId.value = null
  Object.assign(form, { name: '', base_url: 'http://127.0.0.1:8000/v1', model: '', api_key_env: 'HI_AGENT_LLM_API_KEY', timeout_seconds: 120, enabled: true, mock: false })
  modalOpen.value = true
}

function openEdit(model: ModelEndpoint): void {
  editingId.value = model.id
  Object.assign(form, {
    name: model.name, base_url: model.base_url, model: model.model, api_key_env: model.api_key_env || 'HI_AGENT_LLM_API_KEY',
    timeout_seconds: model.timeout_seconds ?? 120, enabled: model.enabled, mock: Boolean(model.mock),
  })
  modalOpen.value = true
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const [modelData, imageData, statusData] = await Promise.all([
      request<ModelEndpoint[] | { items: ModelEndpoint[] }>('/models'),
      request<ImageEndpoint[]>('/image-endpoints'),
      request<SystemStatus>('/system/status'),
    ])
    models.value = listOf(modelData)
    imageEndpoints.value = imageData
    status.value = statusData
    lastRefresh.value = new Date()
  } catch (error) {
    loadError.value = formatApiError(error)
  } finally {
    loading.value = false
  }
}

function openImage(endpoint?: ImageEndpoint): void {
  editingImageId.value = endpoint?.id ?? null
  Object.assign(imageForm, endpoint ? { ...endpoint } : { name: '', base_url: 'https://api.openai.com/v1', model: 'gpt-image-1', api_key_env: 'OPENAI_API_KEY', timeout_seconds: 180, enabled: true })
  imageModalOpen.value = true
}

async function saveImage(): Promise<void> {
  imageSaving.value = true
  try {
    await request(editingImageId.value ? `/image-endpoints/${editingImageId.value}` : '/image-endpoints', { method: editingImageId.value ? 'PATCH' : 'POST', ...jsonBody(imageForm) })
    notify('图像端点已保存', 'success'); imageModalOpen.value = false; await load()
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { imageSaving.value = false }
}

async function toggleImage(endpoint: ImageEndpoint): Promise<void> {
  try { await request(`/image-endpoints/${endpoint.id}`, { method: 'PATCH', ...jsonBody({ enabled: !endpoint.enabled }) }); await load() }
  catch (error) { notify(formatApiError(error), 'error') }
}

async function removeImage(endpoint: ImageEndpoint): Promise<void> {
  if (!window.confirm(`确认删除图像端点“${endpoint.name}”？`)) return
  try { await request(`/image-endpoints/${endpoint.id}`, { method: 'DELETE' }); await load() }
  catch (error) { notify(formatApiError(error), 'error') }
}

async function save(): Promise<void> {
  if (!form.name.trim() || !form.base_url.trim() || !form.model.trim() || !form.api_key_env.trim()) {
    notify('请完整填写端点信息', 'error')
    return
  }
  saving.value = true
  try {
    await request<ModelEndpoint>(editingId.value ? `/models/${editingId.value}` : '/models', {
      method: editingId.value ? 'PATCH' : 'POST',
      ...jsonBody({ ...form, name: form.name.trim(), base_url: form.base_url.trim(), model: form.model.trim(), api_key_env: form.api_key_env.trim() }),
    })
    notify(editingId.value ? '模型端点已更新' : '模型端点已添加', 'success')
    modalOpen.value = false
    await load()
  } catch (error) {
    notify(formatApiError(error), 'error')
  } finally {
    saving.value = false
  }
}

async function toggle(model: ModelEndpoint): Promise<void> {
  try {
    await request<ModelEndpoint>(`/models/${model.id}`, { method: 'PATCH', ...jsonBody({ enabled: !model.enabled }) })
    notify(model.enabled ? '模型端点已停用' : '模型端点已启用', 'success')
    await load()
  } catch (error) { notify(formatApiError(error), 'error') }
}

async function remove(model: ModelEndpoint): Promise<void> {
  if (!window.confirm(`确认删除模型端点“${model.name}”？`)) return
  try {
    await request<void>(`/models/${model.id}`, { method: 'DELETE' })
    notify('模型端点已删除', 'success')
    await load()
  } catch (error) { notify(formatApiError(error), 'error') }
}

function copy(value: string): void {
  void navigator.clipboard.writeText(value)
  notify('已复制到剪贴板', 'success')
}

onMounted(load)
onActivated(() => { if (!loading.value) void load() })
</script>

<template>
  <div class="page">
    <div class="page-inner">
      <header class="page-header">
        <div class="page-title-group">
          <div class="eyebrow">OpenAI-compatible Runtime</div>
          <h1>模型与系统</h1>
          <p>连接本地 vLLM 或任意 OpenAI-compatible 端点。密钥仅以环境变量名称保存，不会写入数据库。</p>
        </div>
        <div class="page-actions">
          <button class="button secondary" type="button" @click="load"><AppIcon name="refresh" :size="16" />刷新状态</button>
          <button class="button" type="button" @click="openCreate"><AppIcon name="plus" :size="16" />添加端点</button>
        </div>
      </header>

      <LoadingState v-if="loading" :rows="4" />
      <EmptyState v-else-if="loadError" icon="alert" title="无法获取系统状态" :description="loadError"><button class="button secondary" type="button" @click="load">重新连接</button></EmptyState>
      <template v-else>
        <section>
          <div class="section-heading"><div><h2>系统状态</h2><p>最后刷新 {{ lastRefresh?.toLocaleTimeString('zh-CN') }}</p></div><StatusBadge :status="status?.status === 'ok' ? 'healthy' : 'error'" /></div>
          <div class="grid status-grid">
            <article v-for="item in statusCards" :key="item.label" class="status-card panel">
              <span><AppIcon :name="item.icon" :size="19" /></span>
              <div><small>{{ item.label }}</small><strong>{{ item.detail }}</strong></div>
              <StatusBadge :status="String(item.value)" />
            </article>
          </div>
        </section>

        <section class="model-section">
          <div class="section-heading"><div><h2>模型端点</h2><p>连接失败时会返回结构化错误，不会静默切换服务</p></div><span class="model-total">{{ models.length }} ENDPOINTS</span></div>
          <EmptyState v-if="models.length === 0" icon="server" title="尚未配置模型" description="添加 vLLM 或其他 OpenAI-compatible /v1 端点后即可开始对话。"><button class="button" type="button" @click="openCreate">添加第一个端点</button></EmptyState>
          <div v-else class="endpoint-list">
            <article v-for="model in models" :key="model.id" class="endpoint panel">
              <div class="endpoint-brand"><span>{{ model.mock ? 'F' : 'LLM' }}</span></div>
              <div class="endpoint-copy">
                <header><h3>{{ model.name }}</h3><StatusBadge :status="model.enabled ? 'enabled' : 'disabled'" /></header>
                <strong>{{ model.model }}</strong>
                <button type="button" title="复制地址" @click="copy(model.base_url)"><code>{{ model.base_url }}</code><AppIcon name="copy" :size="12" /></button>
                <div class="endpoint-facts"><span>KEY <b>{{ model.api_key_env }}</b></span><span>TIMEOUT <b>{{ model.timeout_seconds ?? 120 }}s</b></span><span v-if="model.mock">FAKE MODEL</span></div>
              </div>
              <div class="endpoint-actions">
                <button class="switch" :class="{ on: model.enabled }" type="button" :aria-pressed="model.enabled" @click="toggle(model)" />
                <button class="icon-button" type="button" aria-label="编辑端点" @click="openEdit(model)"><AppIcon name="edit" :size="16" /></button>
                <button class="icon-button remove" type="button" aria-label="删除端点" @click="remove(model)"><AppIcon name="trash" :size="16" /></button>
              </div>
            </article>
          </div>
        </section>

        <section class="model-section">
          <div class="section-heading"><div><h2>图像生成端点</h2><p>独立调用 OpenAI-compatible Images API；密钥仍只保存环境变量名</p></div><button class="button secondary small" type="button" @click="openImage()"><AppIcon name="plus" :size="14" />添加图像端点</button></div>
          <EmptyState v-if="imageEndpoints.length === 0" icon="sparkles" title="尚未配置图像模型" description="配置后，智能体可在审批通过后生成图片并提供下载。" />
          <div v-else class="endpoint-list"><article v-for="endpoint in imageEndpoints" :key="endpoint.id" class="endpoint panel"><div class="endpoint-brand"><span>IMG</span></div><div class="endpoint-copy"><header><h3>{{ endpoint.name }}</h3><StatusBadge :status="endpoint.enabled ? 'enabled' : 'disabled'" /></header><strong>{{ endpoint.model }}</strong><button type="button" @click="copy(endpoint.base_url)"><code>{{ endpoint.base_url }}</code><AppIcon name="copy" :size="12" /></button><div class="endpoint-facts"><span>KEY <b>{{ endpoint.api_key_env }}</b></span><span>TIMEOUT <b>{{ endpoint.timeout_seconds }}s</b></span></div></div><div class="endpoint-actions"><button class="switch" :class="{ on: endpoint.enabled }" type="button" @click="toggleImage(endpoint)" /><button class="icon-button" type="button" @click="openImage(endpoint)"><AppIcon name="edit" :size="16" /></button><button class="icon-button remove" type="button" @click="removeImage(endpoint)"><AppIcon name="trash" :size="16" /></button></div></article></div>
        </section>

        <section class="vllm-note panel">
          <div class="vllm-logo"><AppIcon name="server" :size="22" /></div>
          <div><span>LINUX · NVIDIA</span><h2>vLLM 部署已独立配置</h2><p>Mac 作为客户端连接远端 <code>/v1</code>。请在 GPU 主机使用 <code>deploy/vllm-compose.yml</code> 启动 v0.23.0。</p></div>
          <StatusBadge status="ready" label="配置就绪" />
        </section>
      </template>
    </div>

    <ModalDialog :open="modalOpen" :title="editingId ? '编辑模型端点' : '添加模型端点'" description="兼容 OpenAI Chat Completions API" @close="modalOpen = false">
      <form class="form-grid" @submit.prevent="save">
        <div class="field"><label for="model-name">显示名称</label><input id="model-name" v-model="form.name" class="input" placeholder="例如：本地 Qwen" /></div>
        <div class="field"><label for="model-id">模型 ID</label><input id="model-id" v-model="form.model" class="input mono" placeholder="Qwen/Qwen3-8B" /></div>
        <div class="field full"><label for="model-url">Base URL</label><input id="model-url" v-model="form.base_url" class="input mono" type="url" placeholder="http://127.0.0.1:8000/v1" /></div>
        <div class="field"><label for="model-key">API Key 环境变量</label><input id="model-key" v-model="form.api_key_env" class="input mono" pattern="[A-Z][A-Z0-9_]+" /><span class="field-hint">只保存变量名，不读取或返回密钥值。</span></div>
        <div class="field"><label for="model-timeout">超时（秒）</label><input id="model-timeout" v-model.number="form.timeout_seconds" class="input" type="number" min="1" max="600" /></div>
        <div class="field"><div class="switch-row"><span class="switch-copy"><strong>启用端点</strong><span>允许智能体选择此模型</span></span><button class="switch" :class="{ on: form.enabled }" type="button" @click="form.enabled = !form.enabled" /></div></div>
        <div class="field"><div class="switch-row"><span class="switch-copy"><strong>Fake Model</strong><span>仅用于离线测试</span></span><button class="switch" :class="{ on: form.mock }" type="button" @click="form.mock = !form.mock" /></div></div>
      </form>
      <template #footer><button class="button secondary" type="button" @click="modalOpen = false">取消</button><button class="button" type="button" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存端点' }}</button></template>
    </ModalDialog>
    <ModalDialog :open="imageModalOpen" :title="editingImageId ? '编辑图像端点' : '添加图像端点'" description="兼容 POST /images/generations，并要求返回 b64_json" @close="imageModalOpen = false">
      <form class="form-grid" @submit.prevent="saveImage"><div class="field"><label>显示名称</label><input v-model="imageForm.name" class="input" /></div><div class="field"><label>模型 ID</label><input v-model="imageForm.model" class="input mono" /></div><div class="field full"><label>Base URL</label><input v-model="imageForm.base_url" class="input mono" type="url" /></div><div class="field"><label>API Key 环境变量</label><input v-model="imageForm.api_key_env" class="input mono" pattern="[A-Z][A-Z0-9_]+" /></div><div class="field"><label>超时（秒）</label><input v-model.number="imageForm.timeout_seconds" class="input" type="number" min="1" max="600" /></div><div class="field full"><div class="switch-row"><span class="switch-copy"><strong>启用图像端点</strong><span>同一用户首个启用端点会供智能体使用</span></span><button class="switch" :class="{ on: imageForm.enabled }" type="button" @click="imageForm.enabled = !imageForm.enabled" /></div></div></form>
      <template #footer><button class="button secondary" type="button" @click="imageModalOpen = false">取消</button><button class="button" type="button" :disabled="imageSaving" @click="saveImage">{{ imageSaving ? '保存中…' : '保存端点' }}</button></template>
    </ModalDialog>
  </div>
</template>

<style scoped>
.status-grid { grid-template-columns: repeat(4,minmax(0,1fr)); }
.status-card { display: flex; min-width: 0; align-items: center; gap: 10px; padding: 13px; }
.status-card > span:first-child { display: grid; width: 35px; height: 35px; flex: 0 0 35px; place-items: center; color: var(--green); background: var(--green-soft); border-radius: 10px; }
.status-card > div { display: flex; min-width: 0; flex: 1; flex-direction: column; }
.status-card small { color: var(--muted); font-size: 8px; }
.status-card strong { margin-top: 3px; overflow: hidden; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.status-card .status-badge { width: 8px; min-width: 8px; height: 8px; min-height: 8px; overflow: hidden; padding: 0; border: 0; }
.status-card .status-badge :deep(i) { width: 8px; height: 8px; }
.model-section { margin-top: 28px; }
.model-total { color: var(--faint); font-family: 'DM Mono',monospace; font-size: 8px; }
.endpoint-list { display: grid; gap: 9px; }
.endpoint { display: flex; align-items: center; gap: 14px; padding: 15px; }
.endpoint-brand { display: grid; width: 46px; height: 46px; flex: 0 0 46px; place-items: center; color: #194c39; background: linear-gradient(145deg,#cae9d5,#eaf2d6); border-radius: 13px; }
.endpoint-brand span { font-family: 'DM Mono',monospace; font-size: 9px; font-weight: 500; }
.endpoint-copy { min-width: 0; flex: 1; }
.endpoint-copy header { display: flex; align-items: center; gap: 8px; }
.endpoint-copy h3 { margin: 0; font-size: 13px; }
.endpoint-copy > strong { display: block; margin-top: 4px; font-family: 'DM Mono',monospace; font-size: 9px; }
.endpoint-copy > button { display: flex; max-width: 100%; align-items: center; gap: 5px; margin-top: 4px; padding: 0; color: var(--muted); background: none; border: 0; cursor: pointer; }
.endpoint-copy code { overflow: hidden; font-family: 'DM Mono',monospace; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.endpoint-facts { display: flex; gap: 12px; margin-top: 8px; color: var(--faint); font-family: 'DM Mono',monospace; font-size: 6px; }
.endpoint-facts b { color: var(--muted); font-weight: 500; }
.endpoint-actions { display: flex; align-items: center; gap: 5px; }
.endpoint-actions .remove:hover { color: var(--red); background: var(--red-soft); }
.vllm-note { display: flex; align-items: center; gap: 14px; margin-top: 22px; padding: 17px; background: linear-gradient(110deg,#173b30,#234a3d); border: 0; color: #f2f6f1; }
.vllm-logo { display: grid; width: 46px; height: 46px; flex: 0 0 46px; place-items: center; color: var(--lime); background: rgba(255,255,255,.08); border-radius: 13px; }
.vllm-note > div:nth-child(2) { min-width: 0; flex: 1; }
.vllm-note span { color: rgba(255,255,255,.45); font-family: 'DM Mono',monospace; font-size: 7px; letter-spacing: .1em; }
.vllm-note h2 { margin: 5px 0 3px; font-size: 13px; }
.vllm-note p { margin: 0; color: rgba(255,255,255,.55); font-size: 9px; }
.vllm-note code { font-family: 'DM Mono',monospace; color: var(--lime); }
@media (max-width: 980px) { .status-grid { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 580px) { .status-grid { grid-template-columns: 1fr; } .endpoint { align-items: flex-start; flex-wrap: wrap; } .endpoint-copy { min-width: calc(100% - 62px); } .endpoint-actions { width: 100%; justify-content: flex-end; padding-left: 60px; } .vllm-note { align-items: flex-start; } .vllm-note > .status-badge { display:none; } }
</style>
