<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { formatApiError, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import StatusBadge from '../components/StatusBadge.vue'

interface RecentRun { id: string; agent_id: string; status: string; duration_seconds?: number | null; tool_calls: number; retrieval_hits: number; error_code?: string | null; created_at: string }
interface Summary { total_runs: number; status_counts: Record<string, number>; average_duration_seconds: number; recent_runs: RecentRun[] }

const data = ref<Summary | null>(null)
const loading = ref(true)
const error = ref('')
const successRate = computed(() => {
  const terminal = (data.value?.status_counts.completed || 0) + (data.value?.status_counts.failed || 0) + (data.value?.status_counts.cancelled || 0)
  return terminal ? Math.round((data.value?.status_counts.completed || 0) / terminal * 100) : 0
})

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try { data.value = await request<Summary>('/observability/summary') }
  catch (reason) { error.value = formatApiError(reason) }
  finally { loading.value = false }
}

onMounted(load)
onActivated(load)
</script>

<template>
  <div class="page">
    <div class="page-inner">
      <header class="page-header"><div class="page-title-group"><div class="eyebrow">Agent Operations</div><h1>运行与质量</h1><p>聚合运行状态、延迟、工具与 RAG 召回指标，为评测、Prompt 版本和 Guardrails 提供可观测基础。</p></div><button class="button secondary" type="button" @click="load"><AppIcon name="refresh" :size="16" />刷新</button></header>
      <LoadingState v-if="loading" :rows="4" />
      <EmptyState v-else-if="error" icon="alert" title="无法加载运行指标" :description="error" />
      <template v-else-if="data">
        <section class="metric-grid"><article><span>最近运行</span><strong>{{ data.total_runs }}</strong></article><article><span>完成率</span><strong>{{ successRate }}%</strong></article><article><span>平均耗时</span><strong>{{ data.average_duration_seconds.toFixed(2) }}s</strong></article><article><span>失败</span><strong>{{ data.status_counts.failed || 0 }}</strong></article></section>
        <section class="panel">
          <div class="section-bar"><div><h2>最近运行 Trace</h2><p>每次运行保留配置快照；可按 Run ID 追踪模型、检索和工具事件</p></div><StatusBadge status="ready" label="LOCAL" /></div>
          <div class="table-wrap"><table class="data-table"><thead><tr><th>Run</th><th>状态</th><th>耗时</th><th>工具</th><th>RAG 片段</th><th>错误</th></tr></thead><tbody><tr v-for="run in data.recent_runs" :key="run.id"><td><code>{{ run.id.slice(0,8) }}</code></td><td><StatusBadge :status="run.status" /></td><td>{{ run.duration_seconds == null ? '—' : `${run.duration_seconds.toFixed(2)}s` }}</td><td>{{ run.tool_calls }}</td><td>{{ run.retrieval_hits }}</td><td>{{ run.error_code || '—' }}</td></tr></tbody></table></div>
        </section>
        <section class="capability-grid"><article><AppIcon name="activity" /><div><strong>Trace 与指标</strong><p>状态、耗时、工具调用和召回数量已接入。</p></div></article><article><AppIcon name="agents" /><div><strong>Agent 配置版本</strong><p>创建、修改和恢复都会保存不可变版本。</p></div></article><article><AppIcon name="check" /><div><strong>评测与 Guardrails</strong><p>后续评测数据集将直接关联 Run Trace 与版本。</p></div></article></section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.metric-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:14px; }
.metric-grid article { display:flex; flex-direction:column; gap:7px; padding:17px; background:var(--panel); border:1px solid var(--line); border-radius:var(--radius); }
.metric-grid span { color:var(--muted); font-size:9px; }.metric-grid strong { color:var(--green); font:22px 'DM Mono',monospace; }
.section-bar { display:flex; align-items:center; justify-content:space-between; padding:16px 18px; border-bottom:1px solid var(--line); }.section-bar h2 { margin:0;font-size:13px }.section-bar p { margin:4px 0 0;color:var(--muted);font-size:9px }
.capability-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:14px; }.capability-grid article { display:flex;gap:10px;padding:14px;color:var(--green);background:var(--green-soft);border-radius:10px }.capability-grid strong { color:var(--ink);font-size:10px }.capability-grid p { margin:4px 0 0;color:var(--muted);font-size:9px;line-height:1.5 }
code { font:9px 'DM Mono',monospace } @media(max-width:700px){.metric-grid,.capability-grid{grid-template-columns:1fr 1fr}}
</style>
