<script setup lang="ts">
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { formatApiError, listOf, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import StatusBadge from '../components/StatusBadge.vue'
import type { AgentConfig, ModelEndpoint, Project } from '../types'

interface RecentRun {
  id: string; project_id: string; project_name: string; session_id: string; session_title: string
  agent_id: string; agent_name: string; model_endpoint_id?: string | null; model_endpoint_name?: string | null
  model_id?: string | null; provider?: string; knowledge_base_name?: string | null; status: string
  duration_seconds?: number | null; tool_calls: number; tool_results: number; retrieval_hits: number
  citation_count: number; error_code?: string | null; error_message?: string | null; input_preview: string
  input_chars: number; output_chars: number; created_at: string; started_at?: string | null; finished_at?: string | null
}
interface Summary {
  total_runs: number; offset: number; limit: number; status_counts: Record<string, number>
  average_duration_seconds: number; total_tool_calls: number; total_retrieval_hits: number
  models_used: number; recent_runs: RecentRun[]
}

const data = ref<Summary | null>(null)
const projects = ref<Project[]>([])
const agents = ref<AgentConfig[]>([])
const models = ref<ModelEndpoint[]>([])
const loading = ref(true)
const error = ref('')
const filters = reactive({ q: '', status: 'all', project_id: '', agent_id: '', model: '', error_only: false, created_from: '', created_to: '', offset: 0, limit: 20 })
const successRate = computed(() => {
  const terminal = (data.value?.status_counts.completed || 0) + (data.value?.status_counts.failed || 0) + (data.value?.status_counts.cancelled || 0)
  return terminal ? Math.round((data.value?.status_counts.completed || 0) / terminal * 100) : 0
})
const pages = computed(() => Math.max(1, Math.ceil((data.value?.total_runs || 0) / filters.limit)))
const page = computed(() => Math.floor(filters.offset / filters.limit) + 1)

function params(): string {
  const value = new URLSearchParams()
  Object.entries(filters).forEach(([key, item]) => {
    if (item !== '' && item !== false && item !== 'all') value.set(key, String(item))
  })
  return value.toString()
}
async function load(): Promise<void> {
  loading.value = true; error.value = ''
  try {
    const [summary, projectData, agentData, modelData] = await Promise.all([
      request<Summary>(`/observability/summary?${params()}`),
      request<Project[]>('/projects'), request<AgentConfig[]>('/agents'), request<ModelEndpoint[]>('/models'),
    ])
    data.value = summary; projects.value = listOf(projectData); agents.value = listOf(agentData); models.value = listOf(modelData)
  } catch (reason) { error.value = formatApiError(reason) }
  finally { loading.value = false }
}
function applyFilters(): void { filters.offset = 0; void load() }
function clearFilters(): void { Object.assign(filters, { q: '', status: 'all', project_id: '', agent_id: '', model: '', error_only: false, created_from: '', created_to: '', offset: 0 }); void load() }
function changePage(next: number): void { filters.offset = (Math.min(pages.value, Math.max(1, next)) - 1) * filters.limit; void load() }
function date(value?: string | null): string { return value ? new Date(value).toLocaleString('zh-CN') : '—' }

onMounted(load)
onActivated(() => { if (!loading.value) void load() })
</script>

<template>
  <div class="page">
    <div class="page-inner">
      <header class="page-header"><div class="page-title-group"><div class="eyebrow">Agent Operations</div><h1>运行监测</h1><p>按项目、智能体、模型、状态和时间查询 Run Trace，核对模型调用、RAG、工具、引用与失败信息。</p></div><button class="button secondary" type="button" @click="load"><AppIcon name="refresh" :size="16" />刷新</button></header>
      <section class="panel ops-filter"><form @submit.prevent="applyFilters"><div class="filter-search"><AppIcon name="search" :size="16" /><input v-model="filters.q" placeholder="Run ID、输入内容或智能体名称…" /></div><select v-model="filters.project_id" class="select"><option value="">全部项目</option><option v-for="item in projects" :key="item.id" :value="item.id">{{ item.name }}</option></select><select v-model="filters.agent_id" class="select"><option value="">全部智能体</option><option v-for="item in agents" :key="item.id" :value="item.id">{{ item.name }}</option></select><select v-model="filters.model" class="select"><option value="">全部模型</option><option v-for="item in models" :key="item.id" :value="item.id">{{ item.name }} · {{ item.model }}</option></select><select v-model="filters.status" class="select"><option value="all">全部状态</option><option value="completed">已完成</option><option value="failed">失败</option><option value="running">运行中</option><option value="waiting_approval">等待审批</option><option value="cancelled">已取消</option><option value="interrupted">已中断</option></select><input v-model="filters.created_from" class="input" type="datetime-local" aria-label="开始时间" /><input v-model="filters.created_to" class="input" type="datetime-local" aria-label="结束时间" /><label class="error-check"><input v-model="filters.error_only" type="checkbox" />仅看异常</label><button class="button" type="submit">查询</button><button class="button secondary" type="button" @click="clearFilters">重置</button></form></section>
      <LoadingState v-if="loading" :rows="4" />
      <EmptyState v-else-if="error" icon="alert" title="无法加载运行指标" :description="error" />
      <template v-else-if="data">
        <section class="metric-grid"><article><span>匹配运行</span><strong>{{ data.total_runs }}</strong></article><article><span>完成率</span><strong>{{ successRate }}%</strong></article><article><span>平均耗时</span><strong>{{ data.average_duration_seconds.toFixed(2) }}s</strong></article><article><span>涉及模型</span><strong>{{ data.models_used }}</strong></article><article><span>当前页工具调用</span><strong>{{ data.total_tool_calls }}</strong></article><article><span>当前页 RAG 召回</span><strong>{{ data.total_retrieval_hits }}</strong></article></section>
        <section class="panel"><div class="section-bar"><div><h2>Run Trace 查询结果</h2><p>模型字段来自不可变 Run 配置快照，不暴露 API Key 或 MCP 环境变量</p></div><StatusBadge status="ready" label="TENANT ISOLATED" /></div><EmptyState v-if="!data.recent_runs.length" icon="search" title="没有匹配的 Run" description="调整筛选条件后重新查询。" /><div v-else class="table-wrap"><table class="data-table ops-table"><thead><tr><th>Run / 输入</th><th>项目 / Agent</th><th>模型</th><th>状态</th><th>创建 / 耗时</th><th>工具</th><th>RAG / 引用</th><th>错误</th></tr></thead><tbody><tr v-for="run in data.recent_runs" :key="run.id"><td><code>{{ run.id.slice(0,8) }}</code><small :title="run.input_preview">{{ run.input_preview || '无输入' }}</small></td><td><strong>{{ run.project_name }}</strong><small>{{ run.agent_name }} · {{ run.session_title }}</small></td><td><strong>{{ run.model_endpoint_name || '未绑定端点' }}</strong><small>{{ run.model_id || '—' }}<template v-if="run.provider"> · {{ run.provider }}</template></small></td><td><StatusBadge :status="run.status" /></td><td><strong>{{ date(run.created_at) }}</strong><small>{{ run.duration_seconds == null ? '未结束' : `${run.duration_seconds.toFixed(2)}s` }} · 输出 {{ run.output_chars }} 字</small></td><td>{{ run.tool_calls }} / {{ run.tool_results }}</td><td>{{ run.retrieval_hits }} / {{ run.citation_count }}<small>{{ run.knowledge_base_name || '未使用知识库' }}</small></td><td><code>{{ run.error_code || '—' }}</code><small :title="run.error_message || ''">{{ run.error_message || '无错误' }}</small></td></tr></tbody></table></div><footer v-if="data.total_runs" class="pager"><span>共 {{ data.total_runs }} 条</span><div><button :disabled="page <= 1" @click="changePage(page - 1)">上一页</button><b>{{ page }} / {{ pages }}</b><button :disabled="page >= pages" @click="changePage(page + 1)">下一页</button></div></footer></section>
        <section class="capability-grid"><article><AppIcon name="activity" /><div><strong>配置快照</strong><p>模型、Agent、项目和知识库均从 Run 快照安全展开。</p></div></article><article><AppIcon name="search" /><div><strong>组合查询</strong><p>支持状态、项目、智能体、模型、异常和时间范围筛选。</p></div></article><article><AppIcon name="check" /><div><strong>质量证据</strong><p>显示工具结果、RAG 召回、引用、错误和输出规模。</p></div></article></section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.ops-filter{margin-bottom:14px;padding:14px}.ops-filter form{display:grid;grid-template-columns:2fr repeat(4,minmax(130px,1fr));gap:8px}.ops-filter .filter-search{min-width:220px}.error-check{display:flex;align-items:center;gap:6px;padding:0 10px;font-size:9px;white-space:nowrap}.metric-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:14px}.metric-grid article{display:flex;flex-direction:column;gap:7px;padding:15px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius)}.metric-grid span{color:var(--muted);font-size:9px}.metric-grid strong{color:var(--green);font:20px 'DM Mono',monospace}.section-bar{display:flex;align-items:center;justify-content:space-between;padding:16px 18px;border-bottom:1px solid var(--line)}.section-bar h2{margin:0;font-size:13px}.section-bar p{margin:4px 0 0;color:var(--muted);font-size:9px}.ops-table{min-width:1250px}.ops-table td{vertical-align:top}.ops-table td strong,.ops-table td small{display:block;max-width:240px}.ops-table td small{margin-top:4px;overflow:hidden;color:var(--muted);font-size:8px;text-overflow:ellipsis;white-space:nowrap}.capability-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}.capability-grid article{display:flex;gap:10px;padding:14px;color:var(--green);background:var(--green-soft);border-radius:10px}.capability-grid strong{color:var(--ink);font-size:10px}.capability-grid p{margin:4px 0 0;color:var(--muted);font-size:9px;line-height:1.5}code{font:9px 'DM Mono',monospace}@media(max-width:1100px){.ops-filter form{grid-template-columns:repeat(3,1fr)}.metric-grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:700px){.ops-filter form,.metric-grid,.capability-grid{grid-template-columns:1fr}}
</style>
