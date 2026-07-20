<script setup lang="ts">
import type { DigitalHumanSpec } from '../types'

defineProps<{ spec: DigitalHumanSpec; animated?: boolean }>()
</script>

<template>
  <svg class="digital-avatar" :class="{ animated }" viewBox="0 0 400 480" role="img" :aria-label="`${spec.name} 的动态卡通数字人形象`" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <filter id="avatar-shadow" x="-30%" y="-30%" width="160%" height="170%"><feDropShadow dx="0" dy="12" stdDeviation="14" flood-color="#18382c" flood-opacity=".16" /></filter>
      <linearGradient id="avatar-shirt" x1="0" y1="0" x2="1" y2="1"><stop :stop-color="spec.outfit_color" /><stop offset="1" :stop-color="spec.outfit_color" stop-opacity=".72" /></linearGradient>
    </defs>
    <rect width="400" height="480" rx="36" :fill="spec.background" />
    <circle class="ambient ambient-a" cx="58" cy="77" r="18" :fill="spec.accent_color" opacity=".55" />
    <circle class="ambient ambient-b" cx="342" cy="132" r="9" :fill="spec.outfit_color" opacity=".3" />
    <path d="M38 380c58-51 110-42 151-3 42 39 98 45 173-11v114H38Z" fill="#fff" opacity=".34" />

    <g class="avatar-figure" filter="url(#avatar-shadow)">
      <path v-if="spec.hair_style === 'long'" d="M117 121c5-69 160-83 174 4l9 151c-24 28-174 28-199 0Z" :fill="spec.hair_color" />
      <g v-else-if="spec.hair_style === 'curly'" :fill="spec.hair_color">
        <circle cx="132" cy="126" r="39" /><circle cx="174" cy="102" r="42" /><circle cx="220" cy="102" r="42" /><circle cx="266" cy="128" r="40" /><circle cx="121" cy="181" r="31" /><circle cx="279" cy="181" r="31" />
      </g>
      <circle v-if="spec.hair_style === 'bun'" cx="241" cy="75" r="42" :fill="spec.hair_color" />

      <path d="M103 470c7-106 43-146 97-146s90 40 97 146Z" fill="url(#avatar-shirt)" />
      <path v-if="spec.outfit === 'hoodie'" d="M139 354c27-36 95-36 122 0l-20 33c-23-17-59-17-82 0Z" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="12" />
      <path v-if="spec.outfit === 'suit'" d="m145 343 55 57 55-57 27 127H118Z" fill="#1F2933" opacity=".88" />
      <path v-if="spec.outfit === 'suit'" d="m180 351 20 49 20-49-20-20Z" fill="#F5F3ED" />
      <path v-if="spec.outfit === 'jacket'" d="M200 329v141M122 395h156" fill="none" stroke="#fff" stroke-opacity=".48" stroke-width="5" />
      <path v-if="spec.outfit === 'dress'" d="M139 350c24 19 98 19 122 0l32 120H107Z" :fill="spec.outfit_color" />
      <rect x="181" y="292" width="38" height="52" rx="18" :fill="spec.skin_tone" />

      <circle cx="114" cy="213" r="25" :fill="spec.skin_tone" /><circle cx="286" cy="213" r="25" :fill="spec.skin_tone" />
      <ellipse cx="200" cy="202" rx="91" ry="112" :fill="spec.skin_tone" />

      <path v-if="spec.hair_style === 'short'" d="M112 183c-4-92 46-119 100-111 46 7 78 35 75 102-32-5-54-24-68-50-22 35-58 55-107 59Z" :fill="spec.hair_color" />
      <path v-if="spec.hair_style === 'long'" d="M111 180c-5-89 43-116 99-109 49 6 81 41 77 111-34-15-54-39-66-64-24 34-60 55-110 62Z" :fill="spec.hair_color" />
      <path v-if="spec.hair_style === 'bun'" d="M111 179c-3-83 42-111 99-107 49 4 80 38 77 107-35-8-59-31-70-61-25 36-59 54-106 61Z" :fill="spec.hair_color" />
      <path v-if="spec.hair_style === 'curly'" d="M111 176c5-77 45-103 91-103 50 0 79 31 87 99-34-10-58-30-71-57-23 34-59 54-107 61Z" :fill="spec.hair_color" />

      <g :stroke="spec.hair_color" stroke-width="7" stroke-linecap="round" fill="none">
        <path :d="spec.expression === 'confident' ? 'M145 179l35-7' : 'M145 176q17-8 35 0'" />
        <path :d="spec.expression === 'confident' ? 'm220 172 35 7' : 'M220 176q17-8 35 0'" />
      </g>
      <g class="eyes">
        <ellipse class="eye" cx="163" cy="205" rx="12" ry="15" :fill="spec.eye_color" />
        <ellipse class="eye eye-right" cx="237" cy="205" rx="12" ry="15" :fill="spec.eye_color" />
        <circle cx="159" cy="200" r="3" fill="#fff" /><circle cx="233" cy="200" r="3" fill="#fff" />
      </g>
      <path d="M194 220q5 13 15 2" fill="none" stroke="#B06F5A" stroke-width="4" stroke-linecap="round" opacity=".65" />
      <path v-if="spec.expression === 'smile'" d="M164 251q36 34 72 0" fill="#fff" stroke="#9D514F" stroke-width="5" stroke-linejoin="round" />
      <path v-else-if="spec.expression === 'cool'" d="M169 258h62" fill="none" stroke="#8F4B49" stroke-width="6" stroke-linecap="round" />
      <path v-else d="M171 253q29 18 58 0" fill="none" stroke="#9D514F" stroke-width="6" stroke-linecap="round" />

      <g v-if="spec.accessory === 'glasses'" fill="none" stroke="#263238" stroke-width="5"><rect x="132" y="184" width="59" height="42" rx="17" /><rect x="209" y="184" width="59" height="42" rx="17" /><path d="M191 199h18" /></g>
      <g v-if="spec.accessory === 'headphones'" fill="none" stroke="#27343A" stroke-width="12"><path d="M112 211v-25c0-113 176-113 176 0v25" /><rect x="98" y="197" width="28" height="62" rx="14" :fill="spec.accent_color" /><rect x="274" y="197" width="28" height="62" rx="14" :fill="spec.accent_color" /></g>
      <g v-if="spec.accessory === 'earrings'" :fill="spec.accent_color"><circle cx="113" cy="239" r="8" /><circle cx="287" cy="239" r="8" /></g>
    </g>
    <text x="200" y="444" text-anchor="middle" fill="#fff" font-size="17" font-weight="700" font-family="sans-serif" opacity=".92">{{ spec.name }}</text>
  </svg>
</template>

<style scoped>
.digital-avatar{display:block;width:100%;height:auto;overflow:visible}.animated .avatar-figure{animation:avatar-float 4s ease-in-out infinite;transform-origin:200px 290px}.animated .eye{animation:avatar-blink 5s infinite;transform-box:fill-box;transform-origin:center}.animated .eye-right{animation-delay:.04s}.animated .ambient-a{animation:ambient-drift 6s ease-in-out infinite}.animated .ambient-b{animation:ambient-drift 5s ease-in-out infinite reverse}@keyframes avatar-float{0%,100%{transform:translateY(0) rotate(0)}50%{transform:translateY(-5px) rotate(.4deg)}}@keyframes avatar-blink{0%,44%,48%,100%{transform:scaleY(1)}46%{transform:scaleY(.08)}}@keyframes ambient-drift{0%,100%{transform:translate(0)}50%{transform:translate(8px,-7px)}}@media(prefers-reduced-motion:reduce){.animated .avatar-figure,.animated .eye,.animated .ambient{animation:none}}
</style>
