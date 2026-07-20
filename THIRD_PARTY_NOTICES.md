# Third-party notices

Hi-agent is Apache-2.0 software. It uses independently distributed dependencies whose own
license texts and notices remain authoritative. Exact resolved versions are recorded in
`backend/uv.lock`, `mcp_servers/uv.lock`, and `web/pnpm-lock.yaml`.

## Major Python runtime dependencies

| Component | License |
| --- | --- |
| FastAPI, Pydantic, SQLAlchemy, LangGraph, MCP Python SDK, python-docx | MIT |
| Starlette, Uvicorn, HTTPX, python-dotenv | BSD-3-Clause |
| Qdrant Client, FastEmbed, python-multipart | Apache-2.0 |
| pypdf, ReportLab | BSD-3-Clause |
| PaddleOCR, PaddlePaddle | Apache-2.0 |
| pypdfium2 | Apache-2.0 / BSD-3-Clause |
| python-pptx | MIT |
| aiosqlite | MIT |

Development tooling includes Ruff (MIT), Mypy (MIT), Pytest (MIT), uv (MIT OR Apache-2.0),
and their transitive dependencies.

## Web dependencies

| Component | License |
| --- | --- |
| Vue, Vite, Vitest, ESLint, Vue Test Utils, happy-dom | MIT |
| TypeScript, Playwright | Apache-2.0 |

Node.js and pnpm are downloaded as development/runtime tooling by the bootstrap script and retain
their upstream licenses and bundled notices.

## Models and deployment images

- Embedded `NotoSansSC` font data is Copyright The Noto Project Authors and licensed under
  SIL Open Font License 1.1; the full license is included in `backend/src/hi_agent/assets/OFL.txt`.

- The default FastEmbed model `BAAI/bge-small-zh-v1.5` is delivered through FastEmbed's
  `Qdrant/bge-small-zh-v1.5` artifact and is identified there as MIT licensed.
- `vllm/vllm-openai:v0.23.0` is a separately distributed container based on vLLM (Apache-2.0).
- Any replacement embedding model or language model is separate content. Operators must review
  that model's license, acceptable-use terms, export restrictions, and hardware requirements.

This file is an inventory, not a replacement for upstream license texts. Package wheels,
JavaScript packages, downloaded tools, model caches, and container images may contain additional
transitive notices.
