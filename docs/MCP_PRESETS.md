# MCP 预置服务

Hi-agent 为初始化管理员预置一组常用 MCP 服务。所有预置均默认禁用，应用启动不会下载或执行
第三方代码；只有管理员主动点击“探测工具”或启用后发生实际调用时，`npx`、`uvx` 或 Docker
才会按固定版本获取并运行对应服务。

| 名称 | 能力 | 固定版本 | 运行要求 |
| --- | --- | --- | --- |
| `workspace` | 项目只读文件、文本搜索、计算、时间 | 随 Hi-agent | 已由安装脚本提供 |
| `filesystem` | 受限目录读取、搜索、编辑和移动 | 2026.7.4 | Node.js / npx |
| `git` | Git 状态、差异、日志、分支和提交 | 2026.7.10 | uv / uvx |
| `fetch` | 网页抓取并转换为 Markdown | 2026.7.10 | uv / uvx、网络 |
| `time` | 当前时间和跨时区换算 | 2026.7.10 | uv / uvx |
| `memory` | 本地知识图谱记忆 | 2026.1.26 | Node.js / npx |
| `sequential-thinking` | 分步、修订和分支推理 | 2026.7.4 | Node.js / npx |
| `github-readonly` | GitHub 仓库、Issue、PR 只读查询 | 1.0.5 | Docker、`GITHUB_TOKEN`、网络 |

## 使用方式

1. 在“模型与系统”确认需要的运行工具已安装；项目安装脚本已提供 npx 和 uvx，GitHub 预置另需 Docker。
2. 对需要密钥的服务，只在 `.env` 中填写变量值。GitHub 预置读取 `GITHUB_TOKEN`，数据库仅保存变量名。
3. 在“MCP 服务”页面选择一个预置，先查看路径、联网范围和提示，再点击“探测工具”。
4. 确认工具清单后启用服务，并在 Agent 配置中绑定它。

内置预置可以停用和调整参数，但不能删除或改名。启动时会补齐缺少的内置预置，不覆盖已有同名配置。

## 安全说明

- 除项目自带 `workspace` 外，第三方 MCP 的 annotations 不作为授权依据；工具默认按写入风险要求审批。
- `filesystem` 默认可访问当前项目且包含写入能力。若只需阅读，优先使用经过信任的 `workspace`。
- `fetch` 上游明确提示其可以访问本机或内网地址，存在 SSRF/内部信息暴露风险；仅在明确 URL 范围时批准。
- `memory` 将数据保存到 `data/mcp-memory.jsonl`，内容可能包含对话信息，不要提交或公开该文件。
- `github-readonly` 在容器内启用上游只读模式，但仍应使用最小权限、可轮换的 GitHub Token。
- 第一次探测第三方 stdio 预置可能联网下载固定制品；在离线环境中会明确失败，不会切换其他来源。

## 上游来源

- [Model Context Protocol 官方参考服务器](https://github.com/modelcontextprotocol/servers)
- [GitHub 官方 MCP Server](https://github.com/github/github-mcp-server)
- [MCP 官方服务器概念](https://modelcontextprotocol.io/docs/learn/server-concepts)
