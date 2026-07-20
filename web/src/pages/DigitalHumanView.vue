<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { formatApiError, jsonBody, request } from '../api'
import AppIcon from '../components/AppIcon.vue'
import DigitalAvatar from '../components/DigitalAvatar.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { notify } from '../notifications'
import type { DigitalHumanResponse, DigitalHumanSpec } from '../types'

const examples = [
  '一个自信的短发女生，蓝色眼睛，穿绿色卫衣，戴圆框眼镜，叫小禾',
  '酷酷的银发男生，黑色夹克和耳机，科技感蓝色背景',
  '温柔的卷发中性形象，小麦色皮肤，穿紫色 T 恤，绿色眼睛',
]
const description = ref(examples[0])
const loading = ref(false)
const animated = ref(true)
const response = ref<DigitalHumanResponse | null>(null)
const preview = ref<HTMLElement | null>(null)
const fallback: DigitalHumanSpec = {
  version: 1, name: 'Hi 数字人', presentation: 'neutral', skin_tone: '#E7AC84', hair_style: 'short',
  hair_color: '#262522', eye_color: '#3D342F', outfit: 'hoodie', outfit_color: '#2E8B68',
  accent_color: '#B7E561', accessory: 'none', expression: 'smile', background: '#E7F5EC', seed: 1,
}

async function generate(): Promise<void> {
  if (description.value.trim().length < 2) return
  loading.value = true
  try {
    response.value = await request<DigitalHumanResponse>('/digital-humans/generate', {
      method: 'POST', ...jsonBody({ description: description.value.trim() }),
    })
    notify('数字人形象已生成', 'success')
  } catch (error) { notify(formatApiError(error), 'error') }
  finally { loading.value = false }
}

function useExample(value: string): void { description.value = value; void generate() }

function downloadSvg(): void {
  const svg = preview.value?.querySelector('svg')
  if (!svg) return
  const clone = svg.cloneNode(true) as SVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${response.value?.spec.name || 'digital-human'}.svg`
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(generate)
</script>

<template>
  <div class="page">
    <div class="page-inner human-page">
      <header class="page-header"><div class="page-title-group"><div class="eyebrow">Local Avatar Agent</div><h1>数字人工作台</h1><p>用自然语言生成结构化卡通形象，在浏览器中实时驱动眨眼、呼吸和轻微摆动；全程本地计算，不上传人物描述。</p></div><StatusBadge status="ready" label="内置 2D Agent" /></header>
      <div class="human-layout">
        <section class="panel human-console">
          <div class="agent-identity"><span><AppIcon name="agents" :size="22" /></span><div><strong>{{ response?.agent_name || '数字人形象设计师' }}</strong><small>本地规则引擎 · 无需模型密钥</small></div><StatusBadge status="enabled" label="BUILT-IN" /></div>
          <form @submit.prevent="generate"><label for="human-description">描述你想要的数字人</label><textarea id="human-description" v-model="description" class="textarea" maxlength="1000" placeholder="例如：一个自信的短发女生，蓝色眼睛，穿绿色卫衣，戴眼镜…" /><div class="description-meta"><span>{{ description.length }} / 1000</span><span>支持发型、肤色、眼睛、服装、配饰、气质与背景</span></div><button class="button generate-button" type="submit" :disabled="loading || description.trim().length < 2"><AppIcon name="sparkles" :size="17" />{{ loading ? '设计中…' : '生成数字人' }}</button></form>
          <div class="examples"><strong>快速示例</strong><button v-for="item in examples" :key="item" type="button" @click="useExample(item)">{{ item }}</button></div>
          <div class="safety-note"><AppIcon name="check" :size="16" /><span>生成器只输出白名单形象参数，不执行用户输入中的代码或 SVG 标记，也不会推断种族等敏感身份。</span></div>
        </section>
        <section class="preview-column">
          <div ref="preview" class="panel avatar-stage"><DigitalAvatar :spec="response?.spec || fallback" :animated="animated" /><div v-if="loading" class="avatar-loading"><span class="spinner" />正在组合形象参数…</div></div>
          <div class="preview-actions"><button class="button secondary" type="button" @click="animated = !animated"><AppIcon :name="animated ? 'stop' : 'activity'" :size="15" />{{ animated ? '暂停动态' : '播放动态' }}</button><button class="button" type="button" @click="downloadSvg"><AppIcon name="download" :size="15" />导出 SVG</button></div>
          <div v-if="response" class="panel spec-card"><div><span>发型</span><strong>{{ response.spec.hair_style }}</strong></div><div><span>服装</span><strong>{{ response.spec.outfit }}</strong></div><div><span>配饰</span><strong>{{ response.spec.accessory }}</strong></div><div><span>表情</span><strong>{{ response.spec.expression }}</strong></div></div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.human-page{max-width:1240px}.human-layout{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(360px,.8fr);gap:22px;align-items:start}.human-console{padding:22px}.agent-identity{display:flex;align-items:center;gap:11px;padding-bottom:18px;border-bottom:1px solid var(--line)}.agent-identity>span{display:grid;width:43px;height:43px;place-items:center;color:var(--green);background:var(--green-soft);border-radius:12px}.agent-identity>div{display:flex;min-width:0;flex:1;flex-direction:column}.agent-identity strong{font-size:13px}.agent-identity small{margin-top:4px;color:var(--muted);font-size:9px}.human-console form{display:flex;flex-direction:column;gap:9px;margin-top:20px}.human-console label{font-size:11px;font-weight:650}.human-console textarea{min-height:145px}.description-meta{display:flex;justify-content:space-between;gap:12px;color:var(--faint);font-size:8px}.generate-button{min-height:43px;margin-top:4px}.examples{display:flex;flex-direction:column;gap:7px;margin-top:20px}.examples>strong{font-size:10px}.examples button{padding:9px 11px;color:var(--muted);font-size:9px;line-height:1.5;text-align:left;background:#f7f8f4;border:1px solid var(--line);border-radius:8px;cursor:pointer}.examples button:hover{color:var(--green);border-color:#cfe1d5}.safety-note{display:flex;gap:8px;margin-top:18px;padding:11px;color:var(--green);font-size:9px;line-height:1.6;background:var(--green-soft);border-radius:9px}.preview-column{display:grid;gap:12px}.avatar-stage{position:relative;overflow:hidden;padding:15px;background:#fff}.avatar-loading{position:absolute;inset:0;display:grid;place-content:center;gap:10px;color:var(--muted);font-size:10px;text-align:center;background:rgba(255,255,255,.72);backdrop-filter:blur(4px)}.preview-actions{display:flex;gap:8px}.preview-actions .button{flex:1}.spec-card{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;overflow:hidden}.spec-card div{display:flex;align-items:center;flex-direction:column;gap:5px;padding:12px;background:#fbfcf8}.spec-card span{color:var(--faint);font-size:8px}.spec-card strong{font:9px 'DM Mono',monospace}@media(max-width:900px){.human-layout{grid-template-columns:1fr}.preview-column{width:min(480px,100%);margin:auto}}@media(max-width:560px){.description-meta{flex-direction:column}.spec-card{grid-template-columns:1fr 1fr}}
</style>
