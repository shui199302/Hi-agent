# Hi-agent backend

FastAPI application for the Hi-agent local runtime. From this directory:

```bash
uv sync --all-extras --dev
uv run uvicorn hi_agent.main:app --app-dir src --host 127.0.0.1 --port 8787
```

All persistent state is stored below the project-level `data/` directory. API secrets are
referenced by environment-variable name and are never stored in the database.

