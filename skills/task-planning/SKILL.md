---
name: task-planning
description: "Produce a decision-complete, implementation-ready plan grounded in the current environment. Use for software changes, migrations, integrations, operational work, or any multi-step task that needs scope, interfaces, edge cases, tests, rollout, and acceptance criteria before execution."
---

# Task Planning

## Workflow

1. Inspect the current environment, repository instructions, interfaces, tests, and deployment constraints before proposing changes.
2. State the goal and observable success criteria. Separate confirmed facts, user choices, and assumptions.
3. Resolve high-impact ambiguities with the user; choose and record safe defaults for minor gaps.
4. Describe the implementation by behavior and subsystem, including public interfaces, data flow, state transitions, and compatibility.
5. Cover failure modes, security boundaries, migrations, rollback, observability, and rollout where relevant.
6. Define tests and acceptance scenarios that prove the requested outcome.

Keep the plan concise but leave no implementation decision unresolved. Do not perform mutations while the user is asking only for a plan.

Read [references/acceptance-checklist.md](references/acceptance-checklist.md) before finalizing a plan.
