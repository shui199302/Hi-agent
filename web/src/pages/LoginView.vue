<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { formatApiError, jsonBody, request } from '../api'
import type { AuthConfig, AuthResult, UserProfile } from '../types'

const emit = defineEmits<{ authenticated: [user: UserProfile] }>()

const intent = ref<'login' | 'register'>('login')
const method = ref<'phone' | 'wechat'>('phone')
const phone = ref('')
const username = ref('')
const code = ref('')
const config = ref<AuthConfig | null>(null)
const loading = ref(false)
const error = ref('')
const debugCode = ref('')
const wechat = ref<{ challenge_id: string; ticket: string } | null>(null)
const nickname = ref('Hi-agent 微信用户')

const title = computed(() => intent.value === 'login' ? '欢迎回来' : '创建本地账号')

async function loadConfig(): Promise<void> {
  try {
    config.value = await request<AuthConfig>('/auth/config')
  } catch (reason) {
    error.value = formatApiError(reason)
  }
}

async function sendCode(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await request<{ debug_code?: string }>('/auth/phone/code', {
      method: 'POST',
      ...jsonBody({ phone: phone.value, purpose: intent.value }),
    })
    debugCode.value = result.debug_code ?? ''
    if (debugCode.value) code.value = debugCode.value
  } catch (reason) {
    error.value = formatApiError(reason)
  } finally {
    loading.value = false
  }
}

async function submitPhone(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const path = intent.value === 'register' ? '/auth/phone/register' : '/auth/phone/login'
    const payload = intent.value === 'register'
      ? { phone: phone.value, code: code.value, username: username.value }
      : { phone: phone.value, code: code.value }
    const result = await request<AuthResult>(path, { method: 'POST', ...jsonBody(payload) })
    emit('authenticated', result.user)
  } catch (reason) {
    error.value = formatApiError(reason)
  } finally {
    loading.value = false
  }
}

async function createWechat(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    wechat.value = await request<{ challenge_id: string; ticket: string }>('/auth/wechat/challenges', {
      method: 'POST',
      ...jsonBody({ purpose: intent.value }),
    })
  } catch (reason) {
    error.value = formatApiError(reason)
  } finally {
    loading.value = false
  }
}

async function simulateWechat(): Promise<void> {
  if (!wechat.value) return
  loading.value = true
  error.value = ''
  try {
    await request(`/auth/wechat/challenges/${wechat.value.challenge_id}/mock-authorize`, {
      method: 'POST',
      ...jsonBody({ ticket: wechat.value.ticket, nickname: nickname.value, mock_account: 'default' }),
    })
    const result = await request<AuthResult>(`/auth/wechat/challenges/${wechat.value.challenge_id}/complete`, {
      method: 'POST',
      ...jsonBody({ ticket: wechat.value.ticket }),
    })
    emit('authenticated', result.user)
  } catch (reason) {
    error.value = formatApiError(reason)
  } finally {
    loading.value = false
  }
}

function switchIntent(value: 'login' | 'register'): void {
  intent.value = value
  error.value = ''
  debugCode.value = ''
  code.value = ''
  wechat.value = null
}

onMounted(loadConfig)
</script>

<template>
  <main class="auth-page">
    <section class="auth-hero">
      <div class="auth-brand"><span>H</span><strong>Hi-agent</strong></div>
      <p class="auth-kicker">企业级智能体运行平台</p>
      <h1>让知识、模型与工具<br />在可信边界内协同。</h1>
      <p class="auth-lead">用户数据默认隔离，认证凭据仅保留在本机。登录后进入您的专属智能体工作空间。</p>
      <div class="auth-points">
        <span>独立 Agent 与会话</span><span>私有知识库与文档</span><span>可审计的运行记录</span>
      </div>
    </section>

    <section class="auth-panel-wrap">
      <div class="auth-panel">
        <div class="auth-intents">
          <button :class="{ active: intent === 'login' }" type="button" @click="switchIntent('login')">登录</button>
          <button :class="{ active: intent === 'register' }" type="button" @click="switchIntent('register')">注册</button>
        </div>
        <header><p>{{ intent === 'login' ? '继续使用您的工作空间' : '建立您的专属工作空间' }}</p><h2>{{ title }}</h2></header>

        <div v-if="config?.mode === 'development'" class="auth-dev-notice">
          <strong>开发模拟认证</strong>
          <span>{{ config.provider_notice }}</span>
        </div>

        <div class="auth-methods">
          <button :class="{ active: method === 'phone' }" type="button" @click="method = 'phone'">手机号</button>
          <button :class="{ active: method === 'wechat' }" type="button" @click="method = 'wechat'">微信扫码</button>
        </div>

        <form v-if="method === 'phone'" class="auth-form" @submit.prevent="submitPhone">
          <label v-if="intent === 'register'">用户名<input v-model.trim="username" class="input" minlength="2" maxlength="80" required placeholder="请输入 2–80 个字符" /></label>
          <label>手机号<input v-model.trim="phone" class="input" inputmode="tel" required placeholder="请输入中国大陆手机号" /></label>
          <label>验证码
            <span class="auth-code-row"><input v-model.trim="code" class="input" inputmode="numeric" maxlength="6" required placeholder="6 位验证码" /><button class="button secondary" type="button" :disabled="loading || !phone" @click="sendCode">获取验证码</button></span>
          </label>
          <p v-if="debugCode" class="mock-code">模拟验证码：<strong>{{ debugCode }}</strong>（已自动填入）</p>
          <button class="button auth-submit" type="submit" :disabled="loading">{{ loading ? '正在处理…' : intent === 'login' ? '验证码登录' : '注册并进入' }}</button>
        </form>

        <div v-else class="wechat-login">
          <label v-if="intent === 'register'">微信昵称（模拟）<input v-model.trim="nickname" class="input" maxlength="80" /></label>
          <button v-if="!wechat" class="button auth-submit" type="button" :disabled="loading" @click="createWechat">生成微信登录二维码</button>
          <template v-else>
            <div class="mock-qr" aria-label="模拟微信二维码"><span v-for="n in 49" :key="n" :class="{ dark: (n * 7 + n % 5) % 3 !== 0 }" /></div>
            <p>请使用微信扫描二维码</p>
            <small>当前没有微信开放平台资质，请点击下方按钮模拟扫码授权。</small>
            <button class="button auth-submit wechat-button" type="button" :disabled="loading" @click="simulateWechat">模拟微信扫码并授权</button>
          </template>
        </div>

        <p v-if="error" class="auth-error">{{ error }}</p>
        <p class="auth-policy">登录即表示您同意在本机保存必要的账号、会话与审计信息。</p>
      </div>
    </section>
  </main>
</template>
