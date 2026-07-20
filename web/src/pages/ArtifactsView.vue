<script setup lang="ts">
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { formatApiError, jsonBody, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import LoadingState from '../components/LoadingState.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { notify } from '../notifications'
import { navigateTo } from '../navigation'
import type { ArtifactItem, ImageEndpoint, Project } from '../types'

type GeneratorMode = 'image' | 'run-report' | 'report' | 'presentation'
interface RunItem { id: string; project_id: string; status: string; input: string; created_at: string }

const generators = [
  { id: 'image', label: '图片生成', hint: '使用图片模型生成并归档', icon: 'sparkles' },
  { id: 'run-report', label: '运行报告', hint: '将 Agent Run 导出为报告', icon: 'activity' },
  { id: 'report', label: '文档报告', hint: '生成 Markdown、Word 或 PDF', icon: 'file' },
  { id: 'presentation', label: '演示文稿', hint: '按提纲生成 PPTX', icon: 'presentation' },
] as const

const artifacts = ref<ArtifactItem[]>([])
const projects = ref<Project[]>([])
const imageEndpoints = ref<ImageEndpoint[]>([])
const runs = ref<RunItem[]>([])
const projectId = ref('')
const query = ref('')
const loading = ref(true)
const generating = ref(false)
const error = ref('')
const active = ref<GeneratorMode>('image')
const form = reactive({
  title: '项目分析报告', content: '', format: 'pdf', prompt: '', image_endpoint_id: '', run_id: '',
  presentation_outline: '项目总结\n目标与背景\n核心成果\n\n下一步计划\n优先事项\n风险与应对',
})

const activeProjects = computed(() => projects.value.filter((item) => item.status === 'active'))
const terminalRuns = computed(() => runs.value.filter((item) => (
  item.project_id === projectId.value && !['queued', 'running', 'waiting_approval'].includes(item.status)
)))
const visible = computed(() => artifacts.value.filter((item) => {
  const projectMatches = !projectId.value || item.project_id === projectId.value
  return projectMatches && item.filename.toLowerCase().includes(query.value.trim().toLowerCase())
}))

function bytes(value: number): string {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
function kindLabel(kind: string): string {
  return ({ image: '图片', report: '报告', presentation: '演示文稿' } as Record<string, string>)[kind] ?? kind
}
function openModelSettings(): void { navigateTo('settings/models') }

async function load(): Promise<void> {
  loading.value = true; error.value = ''
  try {
    const [artifactData, projectData, endpointData, runData] = await Promise.all([
      request<ArtifactItem[]>('/artifacts'), request<Project[]>('/projects'),
      request<ImageEndpoint[]>('/image-endpoints'), request<RunItem[]>('/runs'),
    ])
    artifacts.value = artifactData; projects.value = projectData; imageEndpoints.value = endpointData; runs.value = runData
    if (!projectId.value) projectId.value = activeProjects.value[0]?.id ?? ''
    if (!form.image_endpoint_id) form.image_endpoint_id = imageEndpoints.value.find((item) => item.enabled)?.id ?? ''
  } catch (reason) { error.value = formatApiError(reason) }
  finally { loading.value = false }
}

function slidesFromOutline(): Array<{ title: string; bullets: string[] }> {
  return form.presentation_outline.trim().split(/\n\s*\n/).filter(Boolean).map((block) => {
    const lines = block.split('\n').map((line) => line.trim()).filter(Boolean)
    return { title: lines[0] || '内容', bullets: lines.slice(1).length ? lines.slice(1) : ['待补充内容'] }
  })
}

async function generate(): Promise<void> {
  if (!projectId.value) { notify('请先选择项目', 'error'); return }
  generating.value = true
  try {
    let artifact: ArtifactItem
    if (active.value === 'image') {
      artifact = await request<ArtifactItem>('/artifacts/images', { method: 'POST', ...jsonBody({ project_id: projectId.value, image_endpoint_id: form.image_endpoint_id || null, prompt: form.prompt.trim() }) })
    } else if (active.value === 'run-report') {
      artifact = await request<ArtifactItem>('/artifacts/run-reports', { method: 'POST', ...jsonBody({ run_id: form.run_id, format: form.format }) })
    } else if (active.value === 'report') {
      artifact = await request<ArtifactItem>('/artifacts/reports', { method: 'POST', ...jsonBody({ project_id: projectId.value, title: form.title.trim(), content: form.content.trim(), format: form.format }) })
    } else {
      artifact = await request<ArtifactItem>('/artifacts/presentations', { method: 'POST', ...jsonBody({ project_id: projectId.value, title: form.title.trim(), slides: slidesFromOutline() }) })
    }
    artifacts.value = [artifact, ...artifacts.value.filter((item) => item.id !== artifact.id)]
    notify(`${kindLabel(artifact.kind)}已生成，可在下方下载`, 'success')
  } catch (reason) { notify(formatApiError(reason), 'error') }
  finally { generating.value = false }
}

onMounted(load)
onActivated(() => { if (!loading.value) void load() })
</script>

<template>
  <div class="page">
    <div class="page-inner content-page">
      <header class="page-header"><div class="page-title-group"><div class="eyebrow">Content Factory</div><h1>内容生成</h1><p>集中生成图片、智能体运行报告、专业文档和演示文稿，结果按用户与项目安全归档。</p></div><button class="button secondary" type="button" @click="load"><AppIcon name="refresh" :size="16" />刷新</button></header>
      <LoadingState v-if="loading" :rows="5" />
      <EmptyState v-else-if="error" icon="alert" title="无法加载内容生成工作台" :description="error"><button class="button secondary" type="button" @click="load">重新连接</button></EmptyState>
      <template v-else>
        <section class="generator-grid">
          <button v-for="item in generators" :key="item.id" type="button" :class="{ active: active === item.id }" @click="active = item.id"><span><AppIcon :name="item.icon" :size="20" /></span><div><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></div><AppIcon name="chevron" :size="14" /></button>
        </section>

        <section class="panel generator-panel">
          <div class="generator-heading"><div><span>GENERATOR</span><h2>{{ generators.find((item) => item.id === active)?.label }}</h2></div><label>归属项目<select v-model="projectId" class="select"><option v-for="project in activeProjects" :key="project.id" :value="project.id">{{ project.name }}</option></select></label></div>

          <form v-if="active === 'image'" class="generator-form" @submit.prevent="generate">
            <div class="field full"><label for="image-prompt">图片描述</label><textarea id="image-prompt" v-model="form.prompt" class="textarea large" maxlength="8000" placeholder="描述主题、构图、风格、光线、色彩和画幅，例如：雨夜未来城市中的原创机甲战士，电影感灯光…" /></div>
            <div class="field"><label for="image-endpoint">图片模型端点</label><select id="image-endpoint" v-model="form.image_endpoint_id" class="select"><option value="">自动选择已启用端点</option><option v-for="endpoint in imageEndpoints" :key="endpoint.id" :value="endpoint.id" :disabled="!endpoint.enabled">{{ endpoint.name }} · {{ endpoint.model }}{{ endpoint.enabled ? '' : '（已停用）' }}</option></select></div>
            <div v-if="!imageEndpoints.some((item) => item.enabled)" class="endpoint-warning"><AppIcon name="alert" :size="16" /><span>尚未配置可用的图片端点。</span><button type="button" @click="openModelSettings">前往设置</button></div>
            <button class="button submit-generator" type="submit" :disabled="generating || form.prompt.trim().length < 2 || !imageEndpoints.some((item) => item.enabled)"><AppIcon name="sparkles" :size="17" />{{ generating ? '生成中…' : '生成图片' }}</button>
          </form>

          <form v-else-if="active === 'run-report'" class="generator-form" @submit.prevent="generate">
            <div class="field full"><label for="report-run">选择已结束的智能体 Run</label><select id="report-run" v-model="form.run_id" class="select"><option value="">请选择 Run</option><option v-for="run in terminalRuns" :key="run.id" :value="run.id">{{ run.id.slice(0, 8) }} · {{ run.status }} · {{ run.input.slice(0, 60) }}</option></select><span class="field-hint">报告包含配置快照、输入输出、状态、错误和 Trace 事件统计。</span></div>
            <div class="field"><label for="run-format">报告格式</label><select id="run-format" v-model="form.format" class="select"><option value="pdf">PDF</option><option value="docx">Word DOCX</option><option value="md">Markdown</option></select></div>
            <button class="button submit-generator" type="submit" :disabled="generating || !form.run_id"><AppIcon name="file" :size="17" />{{ generating ? '生成中…' : '生成运行报告' }}</button>
          </form>

          <form v-else-if="active === 'report'" class="generator-form" @submit.prevent="generate">
            <div class="field"><label for="document-title">报告标题</label><input id="document-title" v-model="form.title" class="input" maxlength="200" /></div><div class="field"><label for="document-format">格式</label><select id="document-format" v-model="form.format" class="select"><option value="pdf">PDF</option><option value="docx">Word DOCX</option><option value="md">Markdown</option></select></div>
            <div class="field full"><label for="document-content">报告内容</label><textarea id="document-content" v-model="form.content" class="textarea large" maxlength="500000" placeholder="输入需要整理为报告的正文，可包含 Markdown 标题与列表…" /></div>
            <button class="button submit-generator" type="submit" :disabled="generating || !form.title.trim() || !form.content.trim()"><AppIcon name="file" :size="17" />{{ generating ? '生成中…' : '生成文档报告' }}</button>
          </form>

          <form v-else class="generator-form" @submit.prevent="generate">
            <div class="field full"><label for="presentation-title">演示文稿标题</label><input id="presentation-title" v-model="form.title" class="input" maxlength="200" /></div><div class="field full"><label for="presentation-outline">页面提纲</label><textarea id="presentation-outline" v-model="form.presentation_outline" class="textarea large" /><span class="field-hint">空行分隔幻灯片；每段第一行作为标题，其余行作为要点，最多 30 页。</span></div>
            <button class="button submit-generator" type="submit" :disabled="generating || !form.title.trim() || !form.presentation_outline.trim()"><AppIcon name="presentation" :size="17" />{{ generating ? '生成中…' : '生成 PPTX' }}</button>
          </form>
        </section>

        <section class="archive-section">
          <div class="section-heading"><div><h2>生成记录</h2><p>统一查看和下载图片、报告及演示文稿</p></div><div class="archive-filter"><input v-model="query" class="input" placeholder="按文件名搜索…" /><StatusBadge status="ready" :label="`${visible.length} FILES`" /></div></div>
          <EmptyState v-if="visible.length === 0" icon="file" title="暂无生成内容" description="使用上方生成器创建第一份内容，结果会自动出现在这里。" />
          <div v-else class="artifact-grid"><article v-for="artifact in visible" :key="artifact.id" class="panel artifact"><span class="artifact-icon"><AppIcon :name="artifact.kind === 'image' ? 'sparkles' : artifact.kind === 'presentation' ? 'presentation' : 'file'" :size="22" /></span><div><header><strong>{{ artifact.filename }}</strong><StatusBadge :status="artifact.status" :label="kindLabel(artifact.kind)" /></header><p>{{ projects.find((item) => item.id === artifact.project_id)?.name || '项目' }} · {{ bytes(artifact.size_bytes) }}</p><small>{{ artifact.created_at ? new Date(artifact.created_at).toLocaleString('zh-CN') : '' }}</small></div><a class="button secondary small" :href="`/api/v1/artifacts/${artifact.id}/download`" download><AppIcon name="download" :size="14" />下载</a></article></div>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.content-page{max-width:1240px}.generator-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}.generator-grid>button{display:flex;align-items:center;gap:10px;padding:13px;color:var(--muted);text-align:left;background:var(--panel);border:1px solid var(--line);border-radius:12px;cursor:pointer;box-shadow:var(--shadow-sm)}.generator-grid>button>span{display:grid;width:38px;height:38px;flex:0 0 38px;place-items:center;color:var(--green);background:var(--green-soft);border-radius:10px}.generator-grid>button>div{display:flex;min-width:0;flex:1;flex-direction:column}.generator-grid strong{color:var(--ink);font-size:11px}.generator-grid small{margin-top:4px;font-size:8px}.generator-grid>button.active{color:var(--green);background:var(--green-soft);border-color:#cfe3d6}.generator-panel{padding:21px}.generator-heading{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;padding-bottom:17px;border-bottom:1px solid var(--line)}.generator-heading span{color:var(--green);font:8px 'DM Mono',monospace;letter-spacing:.12em}.generator-heading h2{margin:4px 0 0;font-size:16px}.generator-heading>label{display:flex;min-width:220px;align-items:center;gap:9px;color:var(--muted);font-size:9px}.generator-form{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-top:19px}.generator-form .large{min-height:135px}.submit-generator{grid-column:1/-1;min-height:42px}.endpoint-warning{display:flex;align-items:center;gap:7px;padding:10px;color:var(--amber);font-size:9px;background:var(--amber-soft);border-radius:9px}.endpoint-warning button{margin-left:auto;color:var(--amber);font-weight:650;background:transparent;border:0;cursor:pointer}.archive-section{margin-top:25px}.archive-filter{display:flex;align-items:center;gap:9px}.archive-filter .input{width:230px}.artifact-grid{display:grid;gap:10px}.artifact{display:flex;align-items:center;gap:13px;padding:14px}.artifact-icon{display:grid;width:44px;height:44px;flex:0 0 44px;place-items:center;color:var(--green);background:var(--green-soft);border-radius:12px}.artifact>div{min-width:0;flex:1}.artifact header{display:flex;align-items:center;gap:8px}.artifact strong{overflow:hidden;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.artifact p,.artifact small{display:block;margin:4px 0 0;color:var(--muted);font-size:8px}@media(max-width:1000px){.generator-grid{grid-template-columns:1fr 1fr}}@media(max-width:680px){.generator-grid,.generator-form{grid-template-columns:1fr}.generator-heading{align-items:flex-start;flex-direction:column}.generator-heading>label{width:100%;flex-direction:column;align-items:flex-start}.archive-filter{width:100%}.archive-filter .input{width:100%}.artifact{flex-wrap:wrap}.artifact>a{margin-left:57px}}
</style>
