# Evidence checklist

Before reporting a conclusion, confirm:

- The referenced code is reachable from an actual entry point or explicitly identified as dormant.
- Configuration defaults and environment overrides are accounted for.
- Async, retry, caching, and persistence boundaries are included in the trace.
- Tests support the interpretation or their absence is noted.
- Generated and third-party code is not mistaken for project-owned behavior.
- A suspected defect has a concrete trigger, observable effect, and tight location.
- Security impact separates capability, exploit preconditions, and user-controlled input.
