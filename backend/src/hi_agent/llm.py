"""OpenAI-compatible streaming chat client and deterministic test model."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import Settings, get_settings
from .errors import ServiceUnavailableError


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LlmFinal:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class LlmEvent:
    kind: str
    content: str = ""
    final: LlmFinal | None = None


class _RetryableModelStatus(Exception):
    pass


class ChatModel:
    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LlmEvent]:
        raise NotImplementedError


class MockChatModel(ChatModel):
    """Offline deterministic model; a marker can request a tool in integration tests."""

    _tool_marker = re.compile(r"\[\[tool:([a-zA-Z0-9_.-]+)(?:\s+(.+?))?\]\]")

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LlmEvent]:
        last_user = next((item["content"] for item in reversed(messages) if item.get("role") == "user"), "")
        marker = self._tool_marker.search(str(last_user))
        tool_messages = [item for item in messages if item.get("role") == "tool"]
        if marker and not tool_messages:
            arguments: dict[str, Any] = {}
            if marker.group(2):
                try:
                    arguments = json.loads(marker.group(2))
                except json.JSONDecodeError:
                    arguments = {"input": marker.group(2)}
            yield LlmEvent(
                kind="final",
                final=LlmFinal(
                    content="",
                    tool_calls=[ToolCall(id="mock-tool-call", name=marker.group(1), arguments=arguments)],
                ),
            )
            return
        answer = (
            f"工具执行结果：{tool_messages[-1]['content']}"
            if tool_messages
            else f"Mock 模型回答：{last_user}"
        )
        for offset in range(0, len(answer), 8):
            delta = answer[offset : offset + 8]
            await asyncio.sleep(0)
            yield LlmEvent(kind="delta", content=delta)
        yield LlmEvent(kind="final", final=LlmFinal(content=answer))


class OpenAICompatibleChatModel(ChatModel):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key_env: str,
        timeout_seconds: float,
        settings: Settings | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.settings = settings or get_settings()

    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[LlmEvent]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        api_key = self.settings.resolve_secret(self.api_key_env)
        headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        content_parts: list[str] = []
        tool_parts: dict[int, dict[str, str]] = {}
        partial_received = False
        for attempt in range(3):
            try:
                timeout = httpx.Timeout(self.timeout_seconds, connect=min(10.0, self.timeout_seconds))
                async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client, client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    response_status = int(getattr(response, "status_code", 200))
                    if response_status == 429 or response_status >= 500:
                        raise _RetryableModelStatus(f"HTTP {response_status}")
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if raw == "[DONE]":
                            break
                        if not raw:
                            continue
                        packet = json.loads(raw)
                        choices = packet.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        if text := delta.get("content"):
                            partial_received = True
                            content_parts.append(text)
                            yield LlmEvent(kind="delta", content=text)
                        tool_deltas = delta.get("tool_calls") or []
                        if tool_deltas:
                            partial_received = True
                        for call in tool_deltas:
                            index = int(call.get("index", 0))
                            current = tool_parts.setdefault(
                                index,
                                {"id": "", "name": "", "arguments": ""},
                            )
                            current["id"] += call.get("id") or ""
                            function = call.get("function") or {}
                            current["name"] += function.get("name") or ""
                            current["arguments"] += function.get("arguments") or ""
                break
            except (httpx.TransportError, _RetryableModelStatus, OSError) as exc:
                if partial_received or attempt == 2:
                    raise ServiceUnavailableError(
                        "MODEL_UNAVAILABLE",
                        "模型服务不可用，未静默切换到其他服务",
                        base_url=self.base_url,
                        model=self.model,
                        reason=str(exc),
                    ) from exc
                await asyncio.sleep(0.25 * (2**attempt))
            except (httpx.HTTPStatusError, json.JSONDecodeError) as exc:
                raise ServiceUnavailableError(
                    "MODEL_UNAVAILABLE",
                    "模型服务不可用，未静默切换到其他服务",
                    base_url=self.base_url,
                    model=self.model,
                    reason=str(exc),
                ) from exc
        calls: list[ToolCall] = []
        for index in sorted(tool_parts):
            item = tool_parts[index]
            try:
                arguments = json.loads(item["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {"_raw": item["arguments"]}
            calls.append(
                ToolCall(
                    id=item["id"] or f"tool-call-{index}",
                    name=item["name"],
                    arguments=arguments,
                )
            )
        yield LlmEvent(kind="final", final=LlmFinal(content="".join(content_parts), tool_calls=calls))


def build_chat_model(snapshot: dict[str, Any], settings: Settings | None = None) -> ChatModel:
    endpoint = snapshot.get("model_endpoint")
    if not endpoint:
        raise ServiceUnavailableError("MODEL_UNAVAILABLE", "Agent 未配置模型端点")
    if not endpoint.get("enabled", True):
        raise ServiceUnavailableError("MODEL_DISABLED", "模型端点已禁用")
    if endpoint.get("mock"):
        return MockChatModel()
    if not endpoint.get("model"):
        raise ServiceUnavailableError("MODEL_UNAVAILABLE", "模型名称未配置")
    return OpenAICompatibleChatModel(
        base_url=str(endpoint["base_url"]),
        model=str(endpoint["model"]),
        api_key_env=str(endpoint.get("api_key_env", "HI_AGENT_LLM_API_KEY")),
        timeout_seconds=float(endpoint.get("timeout_seconds", 120.0)),
        settings=settings,
    )
