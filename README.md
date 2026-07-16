# Hi-agent

Hi-agent 是一套 localhost 单用户智能体运行平台，包含 Vue 3 中文控制台、FastAPI
REST/SSE、LangGraph、带引用的本地 RAG、MCP 客户端与示例服务器、Agent Skills，
以及独立的 Linux/NVIDIA vLLM 部署配置。

本项目为原创 clean-room 实现，采用 Apache-2.0。Datawhale Hello-Agents 仅作为
能力设计的教育参考；没有复制其代码、文档或资产，详见 [NOTICE.md](NOTICE.md)。

## 主要能力

- 固定 LangGraph 流程：加载会话 → 可选检索 → 模型决策 → 工具/审批循环 →
  整理引用 → 持久化。
- SQLite WAL 元数据、官方 LangGraph SQLite checkpointer、配置快照和重启中断标记。
- 可重连 SSE、事件回放、流式增量、取消、180 秒运行超时、最多 12 次工具循环。
- PDF、DOCX、Markdown、TXT 入库；SHA-256 去重；FastEmbed + 本地 Qdrant；
  可配置分块、重叠和 Top-K，并支持 Dense + BM25 + RRF 混合检索与整库重建。
- MCP stdio 与 Streamable HTTP；工具发现、完整初始化超时、只读/联网/写入/执行风险策略。
- 九个原创 Skills，包括知识库问答、分析写作、`find-skills` 和 `skill-creator`；远程目录安装经过允许列表、暂存、安全扫描和人工确认。
- Agent 配置版本与恢复、最近 100 次 Run 的状态/耗时/工具/RAG Trace 汇总。
- 模型端点、Agent、知识库、MCP、Skills、会话与系统状态的中文 Web 管理界面。
- Linux/NVIDIA vLLM Compose 固定 `vllm/vllm-openai:v0.23.0`；Mac 仅作为 `/v1` 客户端。

## 目录

```text
backend/       FastAPI、LangGraph、RAG、MCP 客户端、Skills 运行时和测试
web/           Vue 3 + TypeScript 控制台、Vitest 与 Playwright
skills/        标准 SKILL.md + scripts/references/assets
mcp_servers/   只读 workspace、计算器和时间 MCP 示例
deploy/        应用容器与 Linux/NVIDIA vLLM Compose
scripts/       安装、启动、诊断、冒烟和真实嵌入验收
data/          SQLite、上传、Qdrant、checkpoint 和嵌入模型（Git 忽略）
```

## macOS 安装与启动

需要约 2 GB 空间和网络连接。安装脚本在项目自己的 `.tools/` 中安装 uv、
Python 3.12、Node 22、pnpm、Playwright Chromium 和依赖，不修改 Homebrew；还会下载
约 90 MB 的中文嵌入模型，但不会下载任何大语言模型权重。

```bash
cp .env.example .env
./scripts/bootstrap.sh
./start.command
```

也可在 Finder 中双击 `start.command`，浏览器默认打开
<http://127.0.0.1:8787>；双击 `stop.command` 停止。运行数据在 `data/`，重启不会丢失。
若修改 `.env` 中的 `HI_AGENT_PORT`，启动和诊断脚本会使用新端口。

模型可在 Web 的“模型与系统”页面创建，也可通过 `.env` 初始化：

```dotenv
HI_AGENT_LLM_BASE_URL=http://127.0.0.1:8000/v1
HI_AGENT_LLM_MODEL=your-served-model-name
HI_AGENT_LLM_API_KEY=replace-with-your-token
HI_AGENT_LLM_API_KEY_ENV=HI_AGENT_LLM_API_KEY
```

数据库与 API 只保存环境变量名，不保存密钥值。密钥不会写入日志、浏览器存储或
API 响应。未配置或无法连接模型时，平台不会静默切换到云服务，而会返回
`MODEL_UNAVAILABLE` 并保留已生成内容。

## RAG 与引用

默认模型是 `BAAI/bge-small-zh-v1.5`，向量保存在本地 Qdrant，并与本地 BM25 结果通过
RRF 融合。知识库页面提供索引配置、召回通道对比和完整 RAG 问答实验台。上传限制 50 MB；
文件名、路径穿越和符号链接逃逸会被拦截。检索片段以“不可信数据”送入模型，
防止文档内容冒充系统指令。回答和 Run 终态中的 citation 包含文件名、可取得的页码、
块编号和分数。删除文档会同步删除上传文件、元数据和向量。

## MCP

首次启动会创建一个默认关闭的 `workspace` stdio 示例配置，指向安装后的
`mcp_servers/.venv/bin/hi-agent-mcp`。在“MCP 服务”页面启用、探测工具，再把它绑定到
Agent 即可使用。另见 [mcp_servers/config.example.json](mcp_servers/config.example.json)。

- stdio 使用命令和参数数组直接启动，不经过 shell。
- HTTP 只支持 Streamable HTTP；远程地址必须为 HTTPS，并同时开启全局和服务级许可。
- 第三方 MCP 的只读 annotation 默认不作为安全授权；未知工具按写入风险要求审批。
- 内置服务器仅可读取获批 workspace，屏蔽 `.env`、密钥、证书和路径逃逸。
- `env_refs` 只保存变量名，值按需从进程环境或 `.env` 读取。

## Skills 与工具审批

Skills 遵循 `SKILL.md` 和 `scripts/references/assets` 目录结构。运行时先加载元数据，
模型明确调用 `skill.<name>.load` 后才读取完整指令，并可按路径读取列出的文本资源。
脚本默认关闭。只有内置白名单 `skill.data-analysis.profile_csv` 可在
`HI_AGENT_ALLOW_SKILL_SCRIPTS=true` 时出现；它仍属于 execute 风险，必须人工批准，
使用固定 Python、固定脚本和参数数组，在超时与 `data/` 路径边界内执行。

“远程发现”默认只访问 `.env` 中 `HI_AGENT_REMOTE_SKILL_CATALOGS` 允许的 GitHub
仓库。下载内容限制文件结构、数量和体积，拦截路径穿越、二进制、密钥和危险执行模式；
发现与安装阶段绝不执行远程脚本。安装后仍需手动绑定到 Agent。可将
`HI_AGENT_ALLOW_REMOTE_SKILLS=false` 完全关闭该能力。

只读工具可自动运行；联网工具需要 Agent 明确允许；write/execute 始终请求人工审批。
拒绝审批后，结果会返回模型以寻找替代方案。

## vLLM（仅 Linux/NVIDIA）

Mac、Apple Silicon 和无 CUDA 主机不启动 vLLM。请在安装 Docker、NVIDIA Container
Toolkit 和合适驱动的 Linux 主机上执行：

```bash
cp deploy/vllm.env.example deploy/vllm.env
# 编辑 VLLM_MODEL、VLLM_SERVED_MODEL_NAME、VLLM_API_KEY 和模型对应的 parser
docker compose --env-file deploy/vllm.env -f deploy/vllm-compose.yml up -d
python3 scripts/check_vllm.py --base-url http://127.0.0.1:8000/v1 \
  --api-key 'your-token' --chat --tool-call
```

Compose 显式配置 GPU、Hugging Face 缓存、API Key、健康检查、tool parser、tensor
parallel、最大上下文和显存占用。模型权重、模型许可与显存容量由部署者负责。

## API

REST 统一前缀为 `/api/v1`，覆盖 `/models`、`/agents`、`/knowledge-bases`、
`/documents`、`/mcp/servers`、`/skills`、`/skills-remote`、`/sessions`、`/runs`、
`/observability` 和 `/system/status`。

`POST /sessions/{id}/runs` 返回 `202`、`run_id` 和 `events_url`；
`GET /runs/{id}/events` 支持 `Last-Event-ID` 或 `after` 游标。审批接口为
`POST /runs/{id}/approvals/{approval_id}`。OpenAPI：<http://127.0.0.1:8787/docs>。

## 验证与诊断

```bash
./scripts/doctor.sh       # 环境、构建产物和运行状态
./scripts/smoke.sh        # 静态页面、REST、Mock Run、SSE、审批/checkpoint
make real-rag-test        # 真实 BGE + Qdrant 入库、检索、引用和向量删除
make verify               # Ruff、Mypy、Pytest、Vitest、build、Playwright、Compose 等
```

离线单元测试使用 fake LLM 和确定性嵌入，不产生模型 API 费用。Docker Compose 在 Mac
仅做配置验收；真实 vLLM 启动与推理需要 Linux/NVIDIA 主机。

## 边界

当前仍仅绑定回环地址并面向本机单用户。远程 Skill 目录已经开放但受允许列表与审批
控制；登录/RBAC、多租户、计费、自主多智能体委派和拖拽式 LangGraph 编辑器将在后续
阶段基于现有 Trace、版本和审批基础继续实现。Web 搜索和远程 MCP 默认关闭。

## 许可

Copyright 2026 Hi-agent contributors. Licensed under Apache-2.0。
