#!/usr/bin/env python3
"""Start Hi-agent from validated application settings without sourcing shell code."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from hi_agent.config import get_settings


def public_url(host: str, port: int) -> str:
    display_host = f"[{host}]" if ":" in host else host
    return f"http://{display_host}:{port}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reload", action="store_true", help="reload backend sources in development")
    parser.add_argument("--print-url", action="store_true", help="print the configured URL and exit")
    args = parser.parse_args()

    settings = get_settings()
    if args.print_url:
        print(public_url(settings.host, settings.port))
        return 0

    project_root = Path(__file__).resolve().parents[1]
    uvicorn.run(
        "hi_agent.main:app",
        host=settings.host,
        port=settings.port,
        reload=args.reload,
        reload_dirs=[str(project_root / "backend" / "src")] if args.reload else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
