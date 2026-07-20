# 变更记录

本项目的重要变更记录在此文件中。格式参考 Keep a Changelog；正式发布后使用语义化版本号。

## [Unreleased]

### Security

- 扩充 Git 忽略规则，排除本地环境文件、IDE 和开发助手状态；移除 vLLM 的公开默认 Token，要求
  部署时显式配置 `VLLM_API_KEY`。

### Added

- 新增 Windows 10/11 x64 的项目内 PowerShell 安装、诊断、启动和停止流程，并在 README 中补充
  安装选项、执行策略、日志、代理及 Windows/WSL2 vLLM 边界说明。
- 增加编码 Agent 工作约束、贡献指南、安全策略和架构文档。
- 增加默认禁用、固定版本的常用 MCP 预置：Filesystem、Git、Fetch、Time、Memory、
  Sequential Thinking 和 GitHub Read-only，并为已有数据库幂等补齐。
- 新增“设置”菜单，将 MCP、Skills、模型与系统、提示词模板集中为二级入口；恢复并强化“运行监测”导航名称。
- 新增不可变的“数字人形象设计师”内置 Agent 与工作台，支持从文字描述本地生成、动态展示和导出
  受控的 2D SVG 卡通形象。
- 启动器会在前端构建、后端源码或 `.env` 发生变化时自动重新构建或重启，避免新增 API 被旧进程
  继续提供服务而返回路径不存在。
- 将数字人工作台迁入“设置”；将原“生成文件”升级为位于运行监测上方的“内容生成”工作台，
  支持图片、通用文档、PPTX、智能体终态 Run 报告和统一文件归档下载。
- 精简工程结构：统一 Agent Revision/Run 快照生成，拆分内容生成 API 与公共 API 辅助函数，集中前端
  hash 导航，并消除内容生成、运行监测页面激活时的重复请求。

## 0.1.0 - 初始基线

### Added

- 提供 FastAPI、LangGraph、SQLite、RAG、MCP 和 Agent Skills 本地运行平台。
- 提供 Vue 3 中文控制台、SSE Run 流、人工工具审批和运行观测。
- 提供项目级 Agent/知识库管理、多用户隔离、报告与制品生成。
- 提供 macOS 本地安装脚本与 Linux/NVIDIA vLLM 部署配置。
