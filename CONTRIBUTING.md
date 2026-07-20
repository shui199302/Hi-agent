# 贡献指南

感谢参与 Hi-agent。项目强调本地优先、可审计执行、用户隔离和显式安全边界。提交代码前请先阅读
`README.md`、`AGENTS.md`、`docs/ARCHITECTURE.md` 和 `SECURITY.md`。

## 开发环境

推荐使用仓库自带的安装脚本，它会把 Python、Node.js、pnpm、浏览器和依赖放在项目的
`.tools/` 或各子项目虚拟环境中：

```bash
cp .env.example .env
./scripts/bootstrap.sh
```

Windows x64 使用项目内 PowerShell 安装流程：

```powershell
Copy-Item .env.example .env
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

启动开发服务：

```bash
make dev
```

后端默认运行于 `http://127.0.0.1:8787`，Vite 开发服务器默认运行于
`http://127.0.0.1:5173`。不要把开发认证模式或未加固的服务暴露到公网。

## 建议流程

1. 从小而明确的问题开始，先确认现有行为和测试覆盖。
2. 创建独立分支，保持一次变更只解决一个主题。
3. 实现代码、测试和必要文档；新增环境变量时同步更新 `.env.example`。
4. 先运行受影响模块的定向测试，再按风险扩大验证范围。
5. 提交前查看 `git diff`，排除密钥、运行数据、构建产物和无关改动。

## 代码规范

### Python

- 支持 Python 3.12，使用类型标注并通过严格 Mypy 检查。
- 遵循 Ruff 配置；保持导入排序和 120 字符行宽。
- API 参数与响应使用 Pydantic schema，领域失败使用稳定的 `HiAgentError` 错误码。
- 数据访问必须带所有权约束；跨用户资源应表现为 404，不泄露资源存在性。
- 外部进程使用固定可执行文件和参数数组，不把不可信内容拼进 shell 命令。

### Vue 与 TypeScript

- 使用 Vue 3 Composition API 和项目已有组件/样式模式。
- API 类型集中维护，前端展示状态必须覆盖加载、空数据、错误和禁用场景。
- 用户可见文字以中文为主；无障碍标签、键盘操作和移动端布局不应退化。
- 新增交互优先补 Vitest，关键用户路径补 Playwright。

### Agent、RAG、MCP 与 Skills

- Agent Run 必须保留可追踪事件、审批状态、配置快照和确定的终态。
- 检索内容和工具输出都视为不可信数据，不允许覆盖系统指令。
- 引用必须能回溯到文件、页码（可用时）和块信息。
- 只读、联网、写入和执行风险不能降级；写入/执行继续要求人工审批。
- Skill 采用标准目录结构，元数据应简短明确；不要在加载指令时自动执行脚本。

## 测试

按改动范围选择：

```bash
make backend-test
make web-test
PYTHONPATH=mcp_servers/src backend/.venv/bin/pytest -q mcp_servers/tests
make build
```

提交重要的跨层或发布相关变更前运行：

```bash
make verify
```

测试应离线、可重复，并避免真实模型费用。只有真实 RAG 验收可以使用本地下载的嵌入模型。
修复缺陷时，优先先增加能复现问题的回归测试。

## 提交与合并请求

提交信息建议使用简洁的祈使句，可采用 `feat:`、`fix:`、`docs:`、`test:`、`refactor:` 等前缀。
合并请求应说明：

- 问题与解决方案；
- 安全、兼容性或数据迁移影响；
- 已运行的验证命令及结果；
- UI 改动的截图或录屏；
- 尚未覆盖的限制。

破坏性 API、配置或持久化格式变化必须显式标注，并提供迁移或回退说明。
