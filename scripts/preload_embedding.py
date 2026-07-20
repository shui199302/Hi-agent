#!/usr/bin/env python3
"""Download and initialize the configured FastEmbed model without any LLM weights."""

from __future__ import annotations

import os
from pathlib import Path

from fastembed import TextEmbedding


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    model_name = os.environ.get("HI_AGENT_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    cache_dir = Path(os.environ.get("HI_AGENT_EMBEDDING_CACHE", root / "data" / "models"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    model = TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))
    vector = next(iter(model.embed(["Hi-agent embedding readiness check"])))
    print(f"Embedding ready: {model_name} ({len(vector)} dimensions) in {cache_dir}")


if __name__ == "__main__":
    main()
