#!/usr/bin/env python3
"""Verify a vLLM OpenAI-compatible endpoint without exposing its API key."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def is_loopback(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


class Client:
    def __init__(self, base_url: str, api_key: str, timeout: float) -> None:
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base URL must be an absolute HTTP(S) URL")
        if parsed.scheme == "http" and not is_loopback(parsed.hostname):
            print("warning: API keys sent to a remote HTTP endpoint are not encrypted", file=sys.stderr)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            message = exc.read(2048).decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} from {path}: {message}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"cannot reach {path}: {exc.reason if hasattr(exc, 'reason') else exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--api-key", default=os.environ.get("VLLM_API_KEY", ""))
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--chat", action="store_true", help="also send a minimal chat completion")
    parser.add_argument("--tool-call", action="store_true", help="require one automatic tool call")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        client = Client(args.base_url, args.api_key, args.timeout)
        models = client.request("/models").get("data", [])
        model_ids = [item.get("id") for item in models if isinstance(item, dict) and item.get("id")]
        if not model_ids:
            raise RuntimeError("/models returned no model ids")
        model = args.model or model_ids[0]
        if args.model and args.model not in model_ids:
            raise RuntimeError(f"requested model {args.model!r} is not present in /models")
        print(f"models OK: {len(model_ids)} available; selected {model}")

        if args.chat or args.tool_call:
            payload: dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly OK."}],
                "temperature": 0,
                "max_tokens": 16,
            }
            if args.tool_call:
                payload["messages"] = [
                    {"role": "user", "content": "Call get_current_time for timezone UTC."}
                ]
                payload["tools"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_current_time",
                            "description": "Return the current time for a timezone",
                            "parameters": {
                                "type": "object",
                                "properties": {"timezone": {"type": "string"}},
                                "required": ["timezone"],
                            },
                        },
                    }
                ]
                payload["tool_choice"] = "auto"
            response = client.request("/chat/completions", payload)
            choices = response.get("choices", [])
            if not choices:
                raise RuntimeError("chat completion returned no choices")
            if args.tool_call:
                message = choices[0].get("message", {})
                if not message.get("tool_calls"):
                    raise RuntimeError("model did not return a tool call; check parser/model compatibility")
                print("tool-call contract OK")
            else:
                print("chat completion contract OK")
        return 0
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"vLLM check failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
