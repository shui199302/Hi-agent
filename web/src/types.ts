export type Id = string

export interface ModelEndpoint {
  id: Id
  name: string
  base_url: string
  model: string
  api_key_env?: string
  timeout_seconds?: number
  enabled: boolean
  mock?: boolean
  is_default?: boolean
  status?: string
  created_at?: string
  updated_at?: string
}

export interface AgentConfig {
  id: Id
  name: string
  description?: string
  system_prompt: string
  model_endpoint_id?: Id | null
  knowledge_base_id?: Id | null
  skills: string[]
  mcp_servers: string[]
  tool_policy: Record<string, unknown>
  max_tool_loops?: number
  enabled?: boolean
  /** Compatibility aliases used by older snapshots. */
  enabled_skills?: string[]
  enabled_mcp_servers?: string[]
  allow_network?: boolean
  created_at?: string
  updated_at?: string
}

export interface KnowledgeBase {
  id: Id
  name: string
  description?: string
  document_count?: number
  chunk_count?: number
  embedding_model?: string
  chunk_size?: number
  chunk_overlap?: number
  top_k?: number
  created_at?: string
  updated_at?: string
}

export interface DocumentItem {
  id: Id
  knowledge_base_id?: Id
  filename: string
  media_type?: string
  size?: number
  size_bytes?: number
  sha256?: string
  status?: string
  chunk_count?: number
  error?: string | null
  created_at?: string
}

export interface McpServerConfig {
  id: Id
  name: string
  transport: 'stdio' | 'streamable_http' | string
  command?: string
  args?: string[]
  url?: string
  enabled: boolean
  allow_network?: boolean
  allow_remote?: boolean
  last_error?: string | null
  status?: string
  tool_count?: number
  tools?: McpTool[]
  created_at?: string
}

export interface McpTool {
  name: string
  description?: string
  risk?: 'read' | 'network' | 'write' | 'execute' | string
}

export interface SkillMetadata {
  name: string
  display_name?: string
  description: string
  enabled?: boolean
  has_scripts?: boolean
  scripts_enabled?: boolean
  scripts_allowed?: boolean
  valid?: boolean
  directory?: string
  error?: string | null
  version?: string
  source?: string
}

export interface RemoteSkill {
  catalog: string
  repository: string
  ref: string
  path: string
  name: string
  description: string
  source_url: string
  has_scripts: boolean
  license?: string | null
}

export interface SessionItem {
  id: Id
  title: string
  agent_id?: Id | null
  status?: string
  message_count?: number
  created_at?: string
  updated_at?: string
}

export interface ChatMessage {
  id: Id
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  created_at?: string
  citations?: Citation[]
}

export interface RunResponse {
  run_id: Id
  status: string
  events_url: string
}

export type RunEventType =
  | 'node_started'
  | 'node_finished'
  | 'retrieval'
  | 'model_delta'
  | 'tool_call'
  | 'approval_required'
  | 'citation'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | string

export interface RunEvent {
  id: number | string
  run_id: Id
  type: RunEventType
  data: Record<string, unknown>
  created_at: string
}

export interface Approval {
  id: Id
  tool_name: string
  arguments?: Record<string, unknown>
  risk?: string
  reason?: string
}

export interface Citation {
  document_id?: Id
  filename: string
  page?: number | null
  chunk_index: number
  score?: number
  content?: string
}

export interface SearchResult extends Citation {
  document_id: Id
  content: string
  score: number
  dense_score?: number | null
  lexical_score?: number | null
  channels?: string[]
}

export interface SystemStatus {
  status?: string
  version?: string
  database?: string | { status?: string }
  qdrant?: string | { status?: string }
  embedding?: string | { status?: string; model?: string }
  embedding_backend?: string
  model_configured?: boolean
  active_runs?: number
  interrupted_runs?: number
  skills?: number
  data_dir?: string
  uptime_seconds?: number
  llm?: string | { status?: string }
}
