import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/auth/me')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'user-1', username: '测试管理员', role: 'admin', status: 'active', created_at: new Date().toISOString(),
        }),
      })
      return
    }
    if (url.pathname.endsWith('/knowledge-bases/query')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, offset: 0, limit: 20 }),
      })
      return
    }
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
    if (url.pathname.endsWith('/digital-humans/generate')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          agent_id: 'digital-agent', agent_name: '数字人形象设计师', description: '测试数字人',
          spec: {
            version: 1, name: '小禾', presentation: 'feminine', skin_tone: '#E7AC84', hair_style: 'short',
            hair_color: '#262522', eye_color: '#4F79A7', outfit: 'hoodie', outfit_color: '#2E8B68',
            accent_color: '#B7E561', accessory: 'glasses', expression: 'smile', background: '#E7F5EC', seed: 1,
          },
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
  const menuLabels = await page.locator('.primary-nav .nav-copy strong').allTextContents()
  expect(menuLabels.indexOf('内容生成')).toBe(menuLabels.indexOf('运行监测') - 1)

  await page.getByRole('button', { name: /知识库/ }).first().click()
  await expect(page).toHaveURL(/#\/knowledge$/)
  await expect(page.getByRole('heading', { name: '知识库列表', exact: true })).toBeVisible()

  await page.getByRole('button', { name: /^设置/ }).first().click()
  await expect(page).toHaveURL(/#\/settings$/)
  const settings = page.getByRole('navigation', { name: '设置分类' })
  await settings.getByRole('button', { name: /^MCP/ }).click()
  await expect(page).toHaveURL(/#\/settings\/mcp$/)
  await expect(page.getByRole('heading', { name: 'MCP 服务', exact: true })).toBeVisible()
  await settings.getByRole('button', { name: /^Skills/ }).click()
  await expect(page).toHaveURL(/#\/settings\/skills$/)
  await expect(page.getByRole('heading', { name: 'Skills', exact: true })).toBeVisible()
  await settings.getByRole('button', { name: /模型与系统/ }).click()
  await expect(page).toHaveURL(/#\/settings\/models$/)
  await expect(page.getByRole('heading', { name: '模型与系统', exact: true })).toBeVisible()
  await settings.getByRole('button', { name: /提示词模板/ }).click()
  await expect(page).toHaveURL(/#\/settings\/prompts$/)
  await expect(page.getByRole('heading', { name: '提示词模板', exact: true })).toBeVisible()

  await settings.getByRole('button', { name: /数字人工作台/ }).click()
  await expect(page).toHaveURL(/#\/settings\/digital-human$/)
  await expect(page.getByRole('heading', { name: '数字人工作台', exact: true })).toBeVisible()
  await expect(page.getByRole('img', { name: /小禾/ })).toBeVisible()
  await expect(page.locator('.digital-avatar')).toHaveClass(/animated/)
  await expect(page.locator('.digital-avatar .eye')).toHaveCount(2)
  await page.getByRole('button', { name: '暂停动态' }).click()
  await expect(page.locator('.digital-avatar')).not.toHaveClass(/animated/)

  await page.getByRole('button', { name: /内容生成/ }).first().click()
  await expect(page).toHaveURL(/#\/artifacts$/)
  await expect(page.getByRole('heading', { name: '内容生成', exact: true })).toBeVisible()

  await page.getByRole('button', { name: /运行监测/ }).first().click()
  await expect(page).toHaveURL(/#\/operations$/)
  await expect(page.getByRole('heading', { name: '运行监测', exact: true })).toBeVisible()
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
