import type { RunEvent } from './types'

export const API_BASE = '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly details?: unknown

  constructor(message: string, status: number, code?: string, details?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

function errorMessage(payload: unknown, fallback: string): { message: string; code?: string } {
  if (!payload || typeof payload !== 'object') return { message: fallback }
  const record = payload as Record<string, unknown>
  if (record.error && typeof record.error === 'object') {
    const nested = record.error as Record<string, unknown>
    return {
      message: String(nested.message ?? nested.detail ?? fallback),
      code: String(nested.code ?? record.code ?? '') || undefined,
    }
  }
  const detail = record.detail
  if (typeof detail === 'string') return { message: detail, code: String(record.code ?? '') || undefined }
  if (detail && typeof detail === 'object') {
    const nested = detail as Record<string, unknown>
    return {
      message: String(nested.message ?? nested.detail ?? fallback),
      code: String(nested.code ?? record.code ?? '') || undefined,
    }
  }
  return {
    message: String(record.message ?? record.error ?? fallback),
    code: String(record.code ?? '') || undefined,
  }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  headers.set('Accept', 'application/json')
  const method = (init.method ?? 'GET').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = document.cookie
      .split('; ')
      .find((item) => item.startsWith('hi_agent_csrf='))
      ?.split('=')[1]
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }

  let response: Response
  try {
    response = await fetch(path.startsWith('http') ? path : `${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: 'same-origin',
    })
  } catch (error) {
    throw new ApiError(
      error instanceof Error ? `无法连接 Hi-agent 服务：${error.message}` : '无法连接 Hi-agent 服务',
      0,
      'NETWORK_ERROR',
    )
  }

  const isJson = response.headers.get('content-type')?.includes('application/json')
  const payload = response.status === 204 ? undefined : isJson ? await response.json() : await response.text()
  if (!response.ok) {
    const parsed = errorMessage(payload, `请求失败（HTTP ${response.status}）`)
    throw new ApiError(parsed.message, response.status, parsed.code, payload)
  }
  return payload as T
}

export async function download(path: string, init: RequestInit = {}): Promise<{ blob: Blob; filename: string }> {
  const headers = new Headers(init.headers)
  headers.set('Accept', '*/*')
  if (init.body && !(init.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const csrf = document.cookie.split('; ').find((item) => item.startsWith('hi_agent_csrf='))?.split('=')[1]
  if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const payload = response.headers.get('content-type')?.includes('application/json') ? await response.json() : await response.text()
    const parsed = errorMessage(payload, `下载失败（HTTP ${response.status}）`)
    throw new ApiError(parsed.message, response.status, parsed.code, payload)
  }
  const disposition = response.headers.get('content-disposition') ?? ''
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] ?? 'download'
  return { blob: await response.blob(), filename }
}

export function jsonBody(value: unknown): Pick<RequestInit, 'body'> {
  return { body: JSON.stringify(value) }
}

export function listOf<T>(payload: T[] | { items?: T[] } | null | undefined): T[] {
  if (Array.isArray(payload)) return payload
  return payload?.items ?? []
}

export function formatApiError(error: unknown): string {
  return error instanceof Error ? error.message : '发生未知错误，请稍后重试'
}

export interface EventStreamHandlers {
  onEvent: (event: RunEvent) => void
  onConnectionError?: () => void
  onOpen?: () => void
}

export function openRunEventStream(eventsUrl: string, handlers: EventStreamHandlers): EventSource {
  const url = eventsUrl.startsWith('http') ? eventsUrl : eventsUrl.startsWith('/') ? eventsUrl : `${API_BASE}/${eventsUrl}`
  const source = new EventSource(url)
  const eventTypes = [
    'node_started',
    'node_finished',
    'retrieval',
    'model_delta',
    'tool_call',
    'tool_result',
    'mcp_error',
    'approval_required',
    'citation',
    'completed',
    'failed',
    'cancelled',
  ]
  const receive = (message: MessageEvent<string>) => {
    try {
      handlers.onEvent(JSON.parse(message.data) as RunEvent)
    } catch {
      // A malformed frame is ignored; the following valid event can still complete the run.
    }
  }
  eventTypes.forEach((name) => source.addEventListener(name, receive as EventListener))
  source.onmessage = receive
  source.onopen = () => handlers.onOpen?.()
  source.onerror = () => handlers.onConnectionError?.()
  return source
}
