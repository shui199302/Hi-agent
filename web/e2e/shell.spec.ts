import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/system/status')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'ok', version: '0.1.0', database: 'ready', embedding_backend: 'deterministic',
          model_configured: false, active_runs: 0, interrupted_runs: 0, skills: 7, data_dir: '/tmp/data',
        }),
      })
      return
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' })
  })
})

test('renders the Chinese console shell and navigates between major areas', async ({ page }) => {
  await page.goto('/')

  await expect(page).toHaveTitle(/Hi-agent/)
  await expect(page.getByText('LOCAL AI STUDIO')).toBeVisible()
  await expect(page.getByRole('heading', { name: '对话与运行' })).toBeVisible()

  await page.getByRole('button', { name: /知识库/ }).first().click()
  await expect(page).toHaveURL(/#\/knowledge$/)
  await expect(page.getByRole('heading', { name: '知识库' })).toBeVisible()

  await page.getByRole('button', { name: /模型与系统/ }).first().click()
  await expect(page).toHaveURL(/#\/models$/)
  await expect(page.getByRole('heading', { name: '模型与系统' })).toBeVisible()
})

test('recovers a terminal event that races with the active-run lookup', async ({ page }) => {
  const now = new Date().toISOString()
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(body),
    })
    if (url.pathname.endsWith('/sessions')) {
      await json([{ id: 'session-1', title: '恢复测试', agent_id: 'agent-1', created_at: now, updated_at: now }])
    } else if (url.pathname.endsWith('/agents')) {
      await json([{ id: 'agent-1', name: '测试助手', enabled: true, created_at: now, updated_at: now }])
    } else if (url.pathname.endsWith('/sessions/session-1')) {
      await json({ id: 'session-1', title: '恢复测试', agent_id: 'agent-1', messages: [], created_at: now, updated_at: now })
    } else if (url.pathname.endsWith('/runs') && url.searchParams.get('session_id') === 'session-1') {
      await json([{
        id: 'run-1', session_id: 'session-1', status: 'running', input: '测试', output: '最终恢复内容',
        config_snapshot: {}, cancel_requested: false, created_at: now, started_at: now,
      }])
    } else if (url.pathname.endsWith('/runs/run-1/event-log')) {
      await json([{
        id: 9, run_id: 'run-1', type: 'completed',
        data: { output: '最终恢复内容', citations: [] }, created_at: now,
      }])
    } else {
      await json([])
    }
  })

  await page.goto('/')
  await expect(page.getByText('最终恢复内容')).toBeVisible()
  await expect(page.locator('.stream-pill')).toHaveCount(0)
})
