# Remote Skill trust policy

- Allow HTTPS sources from configured catalogs only.
- Pin the repository and commit SHA when installing.
- Display the detected license; absence of a license is a blocking warning.
- Permit `SKILL.md`, `agents/`, `references/`, `assets/`, and `scripts/` only.
- Never execute remote scripts during preview, validation, or installation.
- Flag shell execution, network download commands, credential access, dynamic evaluation, encoded payloads, and prompt-injection language.
- Require an explicit confirmation for every installation and replacement.
- Keep installed remote Skills disabled until attached to an Agent by the user.
