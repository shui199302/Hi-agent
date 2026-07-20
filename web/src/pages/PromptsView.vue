<script setup lang="ts">
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { formatApiError, jsonBody, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { notify } from '../notifications'
import type { PromptTemplate } from '../types'

const templates = ref<PromptTemplate[]>([])
const loading = ref(true)
const saving = ref(false)
const query = ref('')
const category = ref('all')
const modalOpen = ref(false)
const editing = ref<PromptTemplate | null>(null)
const form = reactive({ name: '', description: '', category: 'custom', content: '', tags: '' })
const categories: Record<string, string> = { all: '全部类型', general: '通用', rag: '知识库 RAG', research: '研究', analysis: '分析', writing: '写作', coding: '编程', custom: '自定义' }
const filtered = computed(() => templates.value.filter((item) => {
  const text = query.value.trim().toLowerCase()
  return (category.value === 'all' || item.category === category.value)
    && (!text || `${item.name} ${item.description} ${item.tags.join(' ')}`.toLowerCase().includes(text))
}))

async function load(): Promise<void> {
  loading.value = true
  try { templates.value = await request<PromptTemplate[]>('/prompt-templates') }
  catch (error) { notify(formatApiError(error), 'error') }
  finally { loading.value = false }
}
function openCreate(): void {
  editing.value = null
  Object.assign(form, { name: '', description: '', category: 'custom', content: '', tags: '' })
  modalOpen.value = true
}
function openEdit(item: PromptTemplate): void {
  if (item.builtin) return
  editing.value = item
  Object.assign(form, { name: item.name, description: item.description, category: item.category, content: item.content, tags: item.tags.join(', ') })
  modalOpen.value = true
}
async function save(): Promise<void> {
  if (!form.name.trim() || form.content.trim().length < 10) { notify('请填写模板名称和至少 10 个字符的提示词', 'error'); return }
  saving.value = true
  const payload = { name: form.name.trim(), description: form.description.trim(), category: form.category, content: form.content.trim(), variables: [], tags: form.tags.split(/[,，]/).map((item) => item.trim()).filter(Boolean), enabled: true }
  try {
    await request(editing.value ? `/prompt-templates/${editing.value.id}` : '/prompt-templates', { method: editing.value ? 'PATCH' : 'POST', ...jsonBody(payload) })
    modalOpen.value = false
    notify(editing.value ? '提示词模板已更新' : '提示词模板已创建', 'success')
    await load()
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { saving.value = false }
}
async function duplicate(item: PromptTemplate): Promise<void> {
  try {
    await request('/prompt-templates', { method: 'POST', ...jsonBody({ name: `${item.name} 副本`, description: item.description, category: item.category, content: item.content, variables: item.variables, tags: item.tags, enabled: true }) })
    notify('模板副本已创建，可继续编辑', 'success'); await load()
  } catch (error) { notify(formatApiError(error), 'error') }
}
async function remove(item: PromptTemplate): Promise<void> {
  if (item.builtin || !window.confirm(`确认删除提示词模板“${item.name}”？`)) return
  try { await request(`/prompt-templates/${item.id}`, { method: 'DELETE' }); notify('模板已删除', 'success'); await load() }
  catch (error) { notify(formatApiError(error), 'error') }
}
async function copy(item: PromptTemplate): Promise<void> {
  await navigator.clipboard.writeText(item.content)
  notify('提示词已复制', 'success')
}
onMounted(load)
onActivated(() => { if (!loading.value) void load() })
</script>

<template>
  <div class="page">
    <div class="page-inner">
      <header class="page-header"><div class="page-title-group"><div class="eyebrow">Prompt Engineering</div><h1>提示词模板</h1><p>沉淀可复用的系统提示词基线；应用到智能体后会随 Agent Revision 和 Run 快照固化。</p></div><div class="page-actions"><button class="button secondary" @click="load"><AppIcon name="refresh" :size="15" />刷新</button><button class="button" @click="openCreate"><AppIcon name="plus" :size="15" />新建模板</button></div></header>
      <section class="prompt-toolbar"><div class="filter-search"><AppIcon name="search" :size="16" /><input v-model="query" placeholder="搜索名称、说明或标签…" /></div><select v-model="category" class="select"><option v-for="(label, key) in categories" :key="key" :value="key">{{ label }}</option></select></section>
      <LoadingState v-if="loading" :rows="4" />
      <EmptyState v-else-if="!filtered.length" icon="sparkles" title="没有匹配的提示词模板" description="调整筛选条件或新建模板。" />
      <div v-else class="prompt-grid"><article v-for="item in filtered" :key="item.id" class="panel prompt-card"><header><span>{{ categories[item.category] }}</span><StatusBadge :status="item.builtin ? 'ready' : 'enabled'" :label="item.builtin ? '内置基线' : '自定义'" /></header><h2>{{ item.name }}</h2><p>{{ item.description || '暂无说明' }}</p><pre>{{ item.content }}</pre><div class="tag-list"><span v-for="tag in item.tags" :key="tag">{{ tag }}</span></div><footer><button class="button ghost small" @click="copy(item)">复制</button><button class="button ghost small" @click="duplicate(item)">创建副本</button><button v-if="!item.builtin" class="button ghost small" @click="openEdit(item)">编辑</button><button v-if="!item.builtin" class="button danger small" @click="remove(item)">删除</button></footer></article></div>
    </div>
    <ModalDialog :open="modalOpen" :title="editing ? '编辑提示词模板' : '新建提示词模板'" description="模板修改不会影响已经保存的 Agent Revision 或历史 Run" wide @close="modalOpen=false"><div class="form-grid"><div class="field"><label>模板名称</label><input v-model="form.name" class="input" maxlength="120" /></div><div class="field"><label>分类</label><select v-model="form.category" class="select"><option v-for="(label, key) in categories" v-show="key !== 'all'" :key="key" :value="key">{{ label }}</option></select></div><div class="field full"><label>说明</label><input v-model="form.description" class="input" maxlength="4000" /></div><div class="field full"><label>标签（逗号分隔）</label><input v-model="form.tags" class="input" placeholder="例如：客服, 中文, 严谨" /></div><div class="field full"><label>系统提示词</label><textarea v-model="form.content" class="textarea prompt-editor" /></div></div><template #footer><button class="button secondary" @click="modalOpen=false">取消</button><button class="button" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存模板' }}</button></template></ModalDialog>
  </div>
</template>

<style scoped>
.prompt-toolbar{display:flex;gap:12px;margin-bottom:16px}.prompt-toolbar .filter-search{flex:1}.prompt-toolbar .select{width:190px}.prompt-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.prompt-card{display:flex;min-width:0;flex-direction:column;padding:17px}.prompt-card header,.prompt-card footer{display:flex;align-items:center;gap:8px}.prompt-card header{justify-content:space-between;color:var(--green);font-size:9px}.prompt-card h2{margin:13px 0 5px;font-size:15px}.prompt-card>p{margin:0 0 12px;color:var(--muted);font-size:9px}.prompt-card pre{display:-webkit-box;max-height:126px;overflow:hidden;margin:0;padding:12px;white-space:pre-wrap;background:#f7f9f5;border-radius:9px;-webkit-box-orient:vertical;-webkit-line-clamp:6;font:9px/1.65 'DM Mono',monospace}.prompt-card footer{justify-content:flex-end;margin-top:auto;padding-top:13px}.tag-list{display:flex;flex-wrap:wrap;gap:5px;margin-top:10px}.tag-list span{padding:3px 7px;color:var(--green);background:var(--green-soft);border-radius:999px;font-size:8px}.prompt-editor{min-height:300px;font-family:'DM Mono',monospace;line-height:1.65}@media(max-width:800px){.prompt-grid{grid-template-columns:1fr}}@media(max-width:600px){.prompt-toolbar{flex-direction:column}.prompt-toolbar .select{width:100%}}
</style>
