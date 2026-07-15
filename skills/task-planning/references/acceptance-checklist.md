# Acceptance checklist

A decision-complete plan identifies:

- goal, users, success criteria, and explicit exclusions;
- current implementation and constraints discovered from the environment;
- chosen approach and rejected alternatives when the tradeoff matters;
- public APIs, schemas, configuration, and compatibility changes;
- persistence, concurrency, authorization, and error behavior;
- migrations, rollout order, rollback, and monitoring when state or production is affected;
- unit, integration, end-to-end, failure, and security test scenarios;
- defaults and assumptions that an implementer must preserve.

Omit categories that genuinely do not apply; do not invent complexity solely to fill the checklist.
