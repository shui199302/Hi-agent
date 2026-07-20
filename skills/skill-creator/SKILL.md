---
name: skill-creator
description: "在 Hi-agent 工作区中设计、搭建、编辑和校验 Agent Skill。适用于创建新 Skill、将可重复流程沉淀为 Skill、增加参考资料或资产，以及修复不合规的 SKILL.md 包。"
---

# Skill 创建器

## 工作流程

1. 收集明确的触发示例、预期输出、安全边界和可复用资源。
2. 选择简短的 kebab-case 名称，并让 Skill 聚焦于一项可复用能力。
3. 展示拟采用的文件结构，获得批准后再写入。
4. 只能在已配置的 `skills/` 目录内创建内容。生成 `SKILL.md` 和 `agents/openai.yaml`；仅在确有必要时增加参考资料、资产或脚本。
5. frontmatter 只保留 `name` 和 `description`。在描述中写明触发条件，在正文中提供操作步骤。
6. 校验名称、路径、frontmatter、文件大小、链接和脚本策略。在为 Agent 启用 Skill 前展示最终结果。

写入、替换或删除 Skill 始终需要审批。不得生成任意 Shell 安装器，不得写入 `skills/` 以外的目录，也不得自动启用脚本。

最终校验前阅读 [references/authoring-checklist.md](references/authoring-checklist.md)。
