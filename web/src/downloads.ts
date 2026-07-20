import type { Citation, RunEvent, SearchResult } from './types'

export function safeFilename(value: string): string {
  return value.replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, '-').slice(0, 80) || 'knowledge-base'
}

function csvCell(value: unknown): string {
  return `"${String(value ?? '').replaceAll('"', '""')}"`
}

export function buildSearchCsv(input: {
  knowledgeBase: string
  query: string
  mode: string
  results: SearchResult[]
}): string {
  const header = ['序号', '知识库', '查询', '检索模式', '文件名', '页码', '块编号', '召回通道', '融合分数', '向量分数', '关键词分数', '内容']
  const rows = input.results.map((item, index) => [index + 1, input.knowledgeBase, input.query, input.mode, item.filename, item.page ?? '', item.chunk_index, item.channels?.join(' + ') ?? '', item.score, item.dense_score ?? '', item.lexical_score ?? '', item.content])
  return `\uFEFF${[header, ...rows].map((row) => row.map(csvCell).join(',')).join('\r\n')}`
}

export function buildRagMarkdown(input: {
  knowledgeBase: { id: string; name: string }
  question: string
  answer: string
  events: RunEvent[]
  citations: Citation[]
  generatedAt: string
}): string {
  const workflow = input.events.filter((event) => event.type !== 'model_delta').map((event) => `- ${event.type}`).join('\n') || '- 无执行事件记录'
  const citations = input.citations.map((item, index) => `${index + 1}. **${item.filename}**${item.page ? `，第 ${item.page} 页` : ''}，块 ${item.chunk_index}${item.score == null ? '' : `，相关度 ${(item.score * 100).toFixed(1)}%`}`).join('\n') || '无引用记录'
  return `# ${input.knowledgeBase.name} · RAG 问答报告\n\n- 生成时间：${input.generatedAt}\n- 知识库：${input.knowledgeBase.name}\n- 知识库 ID：${input.knowledgeBase.id}\n\n## 问题\n\n${input.question}\n\n## 回答\n\n${input.answer}\n\n## 执行流程\n\n${workflow}\n\n## 引用来源\n\n${citations}\n`
}
