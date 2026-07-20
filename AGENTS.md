# AGENTS.md

本文件约束在 Hi-agent 仓库中工作的编码 Agent，作用域为整个仓库。若子目录以后出现更具体的
`AGENTS.md`，以距离目标文件最近的规则为准。

## 项目目标

Hi-agent 是本地优先的多用户智能体运行平台。核心组合为 FastAPI、LangGraph、SQLite、
Qdrant/FastEmbed、MCP、Agent Skills，以及 Vue 3 + TypeScript 控制台。默认运行边界是本机回环
地址；不得引入隐式云服务回退。

开始修改前先阅读：

- `README.md`：能力、安装、配置和验收入口。
- `docs/ARCHITECTURE.md`：组件边界、执行链路和数据流。
- `CONTRIBUTING.md`：开发流程和测试要求。
- `SECURITY.md`：凭据、文件、联网、工具审批和漏洞处理规则。

## 仓库地图

| 路径 | 职责 |
| --- | --- |
| `backend/src/hi_agent/` | API、认证、持久化、LangGraph 运行时、RAG、MCP、Skills 与制品 |
| `backend/tests/` | 后端服务和 API 测试 |
| `web/src/` | Vue 控制台、API 客户端和单元测试 |
| `web/e2e/` | Playwright 端到端测试 |
| `mcp_servers/` | 内置只读 MCP 示例及协议测试 |
| `skills/` | 内置 Skill 的 `SKILL.md`、引用、脚本和资源 |
| `scripts/` | 安装、启动、诊断、冒烟和真实 RAG 验收 |
| `deploy/` | 应用及 Linux/NVIDIA vLLM Compose 配置 |
| `data/`、`logs/` | 本地运行状态；除 `.gitkeep` 外不得提交 |

## 工作规则

1. 修改前检查 `git status --short`，保留用户已有改动，不重置、不覆盖无关文件。
2. 优先做最小、可回滚的改动；不要顺带重构与任务无关的代码。
3. Python 目标版本为 3.12，保持 Ruff、Mypy strict 和现有 Pydantic/SQLAlchemy 风格。
4. Web 使用 Vue 3、TypeScript 和 pnpm；保持严格类型，避免用 `any` 绕过接口约束。
5. API 统一放在 `/api/v1` 下；错误继续使用稳定的错误码和统一错误结构。
6. 涉及数据库模型、Agent 配置或 Run 状态时，考虑旧数据迁移、用户归属、配置快照和重启恢复。
7. 涉及 SSE 时，保持事件持久化、单调游标、重连回放、终态和取消语义。
8. 涉及 RAG 时，保持知识库所有权校验、引用可追溯、检索文本不可信和向量删除一致性。
9. 涉及 MCP、Skill 脚本、文件或网络时，保持风险分级、人工审批、参数数组和路径边界；禁止通过 shell 拼接不可信输入。
10. 密钥只从进程环境或 `.env` 按变量名解析；不得写入数据库、日志、前端存储、测试快照或提交内容。
11. 新功能同时补充测试和用户可见文档；行为变化记录在 `CHANGELOG.md` 的 `Unreleased` 下。
12. 不手工编辑生成物和依赖目录，例如 `web/dist/`、`node_modules/`、`.tools/`、缓存及运行数据。

## 常用命令

首次安装：

```bash
cp .env.example .env
./scripts/bootstrap.sh
```

开发与定向验证：

```bash
make dev
make backend-test
make web-test
make build
PYTHONPATH=mcp_servers/src backend/.venv/bin/pytest -q mcp_servers/tests
```

完整验证：

```bash
make verify
```

`make verify` 包含真实嵌入/RAG、浏览器、Compose 配置与冒烟检查，耗时和环境要求高于单元测试。
只修改文档时，至少检查链接、命令和 `git diff --check`；无需为纯文档改动运行完整测试套件。

## 变更完成标准

- 需求已由测试或可复现的手工步骤验证。
- 新增配置同步更新 `.env.example`，且默认值保持本地优先、失败关闭。
- 前后端契约和 TypeScript/Pydantic 类型一致。
- 不包含凭据、用户数据、模型权重、构建产物或无关格式化。
- 最终说明列出改动、验证命令和任何未验证风险。
