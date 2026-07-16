import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, API_BASE, listOf, request } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('API client', () => {
  it('normalizes array and item-envelope lists', () => {
    expect(listOf([1, 2])).toEqual([1, 2])
    expect(listOf({ items: ['a'] })).toEqual(['a'])
    expect(listOf(undefined)).toEqual([])
  })

  it('uses the same-origin v1 prefix and returns JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(request('/system/status')).resolves.toEqual({ status: 'ok' })
    expect(fetchMock).toHaveBeenCalledWith(`${API_BASE}/system/status`, expect.objectContaining({ headers: expect.any(Headers) }))
  })

  it('surfaces structured backend errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      error: { code: 'MODEL_UNAVAILABLE', message: '模型服务不可达' },
    }), { status: 503, headers: { 'Content-Type': 'application/json' } })))

    const promise = request('/models')
    await expect(promise).rejects.toBeInstanceOf(ApiError)
    await expect(promise).rejects.toMatchObject({ status: 503, code: 'MODEL_UNAVAILABLE', message: '模型服务不可达' })
  })

  it('maps network failures to a stable code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('connection refused')))
    await expect(request('/sessions')).rejects.toMatchObject({ code: 'NETWORK_ERROR', status: 0 })
  })

  it('sends the double-submit CSRF token for mutations', async () => {
    document.cookie = 'hi_agent_csrf=test-csrf-token; path=/'
    const fetchMock = vi.fn().mockResolvedValue(new Response(undefined, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await request('/auth/logout', { method: 'POST' })
    const options = fetchMock.mock.calls[0][1] as RequestInit
    expect(options.credentials).toBe('same-origin')
    expect((options.headers as Headers).get('X-CSRF-Token')).toBe('test-csrf-token')
  })
})
