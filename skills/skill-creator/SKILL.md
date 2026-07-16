---
name: skill-creator
description: "Design, scaffold, edit, and validate Agent Skills inside the Hi-agent workspace. Use when a user asks to create a new Skill, turn a repeatable workflow into a Skill, add references or assets, or repair an invalid SKILL.md package."
---

# Skill Creator

## Workflow

1. Collect concrete trigger examples, expected outputs, safety boundaries, and reusable resources.
2. Choose a short kebab-case name and keep the Skill focused on one reusable capability.
3. Present the proposed file layout and obtain approval before writing.
4. Create only inside the configured `skills/` directory. Generate `SKILL.md` and `agents/openai.yaml`; add references, assets, or scripts only when justified.
5. Keep frontmatter to `name` and `description`. Put trigger conditions in the description and procedural guidance in the body.
6. Validate naming, paths, frontmatter, size, links, and script policy. Show the result before enabling the Skill on an Agent.

Writing, replacing, or deleting a Skill always requires approval. Never generate arbitrary shell installers, never write outside `skills/`, and never enable scripts automatically.

Read [references/authoring-checklist.md](references/authoring-checklist.md) before final validation.
