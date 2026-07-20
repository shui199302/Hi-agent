export type Id = string

export interface UserProfile {
  id: Id
  username: string
  phone?: string | null
  role: 'admin' | 'user' | string
  status: string
  wechat_nickname?: string | null
  avatar_url?: string | null
  created_at: string
  last_login_at?: string | null
}

export interface AuthConfig {
  mode: 'development' | 'production'
  mock_phone_enabled: boolean
  mock_wechat_enabled: boolean
  provider_notice: string
}

export interface AuthResult {
  user: UserProfile
  csrf_token: string
}

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

export interface ImageEndpoint {
  id: Id
  name: string
  base_url: string
  model: string
  api_key_env: string
  timeout_seconds: number
  enabled: boolean
  created_at?: string
  updated_at?: string
}

export interface Project {
  id: Id
  name: string
  description: string
  status: 'active' | 'archived'
  agent_count: number
  knowledge_base_count: number
  session_count: number
  run_count: number
  last_activity_at?: string | null
  created_at: string
  updated_at: string
}

export interface PromptTemplate {
  id: Id
  name: string
  description: string
  category: 'general' | 'rag' | 'research' | 'analysis' | 'writing' | 'coding' | 'custom'
  content: string
  variables: string[]
  tags: string[]
  builtin: boolean
  enabled: boolean
  created_at: string
  updated_at: string
}

export interface AgentConfig {
  id: Id
  project_id: Id
  name: string
  description?: string
  system_prompt: string
  model_endpoint_id?: Id | null
  knowledge_base_id?: Id | null
  skills: string[]
  mcp_servers: string[]
  tool_policy: Record<string, unknown>
  max_tool_loops?: number
  review_policy: 'off' | 'auto' | 'manual' | 'risk_based'
  review_model_endpoint_id?: Id | null
  review_max_rounds?: number
  agent_type?: 'general' | 'digital_human' | string
  builtin?: boolean
  enabled?: boolean
  /** Compatibility aliases used by older snapshots. */
  enabled_skills?: string[]
  enabled_mcp_servers?: string[]
  allow_network?: boolean
  created_at?: string
  updated_at?: string
}

export interface DigitalHumanSpec {
  version: number
  name: string
  presentation: 'feminine' | 'masculine' | 'neutral'
  skin_tone: string
  hair_style: 'short' | 'long' | 'curly' | 'bun' | 'bald'
  hair_color: string
  eye_color: string
  outfit: 'tshirt' | 'hoodie' | 'suit' | 'dress' | 'jacket'
  outfit_color: string
  accent_color: string
  accessory: 'none' | 'glasses' | 'headphones' | 'earrings'
  expression: 'smile' | 'calm' | 'confident' | 'cool'
  background: string
  seed: number
}

export interface DigitalHumanResponse {
  agent_id: Id
  agent_name: string
  description: string
  spec: DigitalHumanSpec
}

export interface KnowledgeBase {
  id: Id
  project_id: Id
  name: string
  description?: string
  document_count?: number
  chunk_count?: number
  ready_document_count?: number
  processing_document_count?: number
  failed_document_count?: number
  total_size_bytes?: number
  bound_agent_count?: number
  status?: 'empty' | 'ready' | 'processing' | 'error'
  embedding_model?: string
  chunk_size?: number
  chunk_overlap?: number
  top_k?: number
  ocr_mode?: 'off' | 'auto' | 'force'
  ocr_language?: 'ch' | 'en'
  ocr_min_chars?: number
  created_at?: string
  updated_at?: string
}

export interface PagedResult<T> {
  items: T[]
  total: number
  offset: number
  limit: number
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
  extraction_method?: 'text' | 'ocr' | 'hybrid'
  ocr_pages?: number[]
  ocr_engine?: string | null
  created_at?: string
}

export interface McpServerConfig {
  id: Id
  name: string
  description?: string
  source_url?: string | null
  setup_hint?: string
  builtin?: boolean
  transport: 'stdio' | 'streamable_http' | string
  command?: string
  args?: string[]
  url?: string
  env_refs?: Record<string, string>
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
  source: 'github' | 'clawhub'
  catalog: string
  repository: string
  ref: string
  path: string
  name: string
  description: string
  source_url: string
  has_scripts: boolean
  license?: string | null
  slug?: string | null
  version?: string | null
  publisher?: string | null
  security_verdict?: string | null
  downloads?: number | null
  instructions_preview?: string | null
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
  | 'plan_drafted'
  | 'plan_reviewed'
  | 'plan_review_required'
  | 'plan_approved'
  | 'plan_rejected'
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

export interface ArtifactItem {
  id: Id
  project_id: Id
  run_id?: Id | null
  kind: 'report' | 'presentation' | 'image' | string
  filename: string
  media_type: string
  size_bytes: number
  status: string
  metadata_json?: Record<string, unknown>
  download_url?: string
  created_at?: string
}

export interface Approval {
  id: Id
  kind?: 'tool_approval' | 'plan_review' | string
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
