---
name: codebase-analysis
description: "Analyze an existing codebase without changing it, tracing architecture and behavior to file-and-line evidence. Use for repository orientation, dependency mapping, implementation discovery, bug-cause investigation, data-flow tracing, security review, or estimating the impact of a proposed change."
---

# Codebase Analysis

## Workflow

1. Read repository instructions and manifests first. Identify languages, entry points, generated files, and test layout.
2. Use targeted filename and symbol searches. Avoid broad dumps of vendor, build, cache, or secret-bearing directories.
3. Trace the requested path from boundary to state change and output, including configuration and error handling.
4. Compare implementation with tests and public interfaces. Distinguish observed behavior from hypothesis.
5. Report findings with clickable `path:line` evidence, affected callers, and uncertainty.

Stay read-only. Do not reveal secret values found in configuration; mention only the variable name and location. Do not execute repository scripts merely to understand them. Request approval before any command that can modify data or contact external systems.

Read [references/evidence-checklist.md](references/evidence-checklist.md) before presenting a causal or security conclusion.
