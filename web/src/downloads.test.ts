import { describe, expect, it } from 'vitest'
import { buildRagMarkdown, buildSearchCsv, safeFilename } from './downloads'

describe('knowledge base downloads', () => {
  it('builds an Excel-friendly CSV and escapes quoted content', () => {
    const csv = buildSearchCsv({
      knowledgeBase: '产品知识库',
      query: '价格,版本',
      mode: 'hybrid',
      results: [{ document_id: 'doc-1', filename: '报价"表.csv', page: 2, chunk_index: 7, content: '企业版,含服务', score: 0.91, dense_score: 0.8, lexical_score: 0.7, channels: ['dense', 'lexical'] }],
    })
    expect(csv.startsWith('\uFEFF')).toBe(true)
    expect(csv).toContain('"报价""表.csv"')
    expect(csv).toContain('"dense + lexical"')
    expect(csv).toContain('"企业版,含服务"')
  })

  it('builds a Markdown RAG report with workflow and citations', () => {
    const report = buildRagMarkdown({
      knowledgeBase: { id: 'kb-1', name: '产品知识库' },
      question: '企业版是什么？',
      answer: '企业版包含支持服务。',
      generatedAt: '2026年7月16日 11:00:00',
      events: [{ id: 1, run_id: 'run-1', type: 'retrieval', data: {}, created_at: '2026-07-16T03:00:00Z' }],
      citations: [{ filename: '说明书.pdf', page: 3, chunk_index: 4, score: 0.88 }],
    })
    expect(report).toContain('# 产品知识库 · RAG 问答报告')
    expect(report).toContain('## 回答\n\n企业版包含支持服务。')
    expect(report).toContain('- retrieval')
    expect(report).toContain('**说明书.pdf**，第 3 页，块 4，相关度 88.0%')
  })

  it('sanitizes filenames', () => {
    expect(safeFilename('知识库 / 2026:报告')).toBe('知识库---2026-报告')
  })
})
