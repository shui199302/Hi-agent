# Authoring checklist

- Folder and frontmatter names match and use kebab-case.
- Description states capability and triggering situations.
- Instructions are concise, imperative, and free of duplicated general knowledge.
- Large or optional details live in directly linked references.
- Scripts are deterministic, bounded, and disabled by default.
- No secrets, machine-specific paths, symlinks, traversal, or unreviewed network calls exist.
- `agents/openai.yaml` matches the Skill purpose.
- The package passes structural and security validation before use.
