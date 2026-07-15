#!/usr/bin/env python3
"""Exercise the installed HTTP API, SSE replay, mock model, and optional approval resume."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


class ApiClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                body = response.read()
                if expect_json:
                    return json.loads(body.decode("utf-8")) if body else None
                return body.decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {detail}") from exc

    def wait_for(self, run_id: str, statuses: set[str], timeout: float = 12) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.request(f"/api/v1/runs/{run_id}")
            if run["status"] in statuses:
                return run
            time.sleep(0.05)
        raise RuntimeError(f"run {run_id} did not reach {sorted(statuses)}")


def check_contract(client: ApiClient) -> None:
    health = client.request("/api/v1/health")
    status = client.request("/api/v1/system/status")
    openapi = client.request("/openapi.json")
    if health.get("status") != "ok" or status.get("status") != "ok":
        raise RuntimeError("health or system status is not OK")
    required = {
        "/api/v1/models",
        "/api/v1/agents",
        "/api/v1/knowledge-bases",
        "/api/v1/mcp/servers",
        "/api/v1/skills",
        "/api/v1/sessions",
        "/api/v1/runs",
        "/api/v1/system/status",
    }
    missing = sorted(required - set(openapi.get("paths", {})))
    if missing:
        raise RuntimeError(f"OpenAPI is missing paths: {missing}")
    html = client.request("/", expect_json=False)
    if "<title>Hi-agent" not in html:
        raise RuntimeError("FastAPI did not serve the built Hi-agent web console")


def run_mock_flow(client: ApiClient, expect_approval: bool) -> None:
    suffix = uuid.uuid4().hex[:10]
    model_id = agent_id = session_id = None
    try:
        if expect_approval:
            servers = client.request("/api/v1/mcp/servers")
            workspace = next((item for item in servers if item["name"] == "workspace"), None)
            if workspace is None:
                raise RuntimeError("installed workspace MCP seed is missing")
            probe = client.request(
                f"/api/v1/mcp/servers/{workspace['id']}/probe",
                method="POST",
            )
            if probe["status"] != "online" or len(probe["tools"]) != 5:
                raise RuntimeError(f"bundled MCP discovery failed: {probe}")
            if any(tool["risk"] != "read" for tool in probe["tools"]):
                raise RuntimeError("bundled read-only MCP tools were not classified as read")

        model = client.request(
            "/api/v1/models",
            method="POST",
            payload={
                "name": f"smoke-model-{suffix}",
                "base_url": "http://mock.local/v1",
                "model": "mock-model",
                "mock": True,
            },
        )
        model_id = model["id"]
        agent = client.request(
            "/api/v1/agents",
            method="POST",
            payload={
                "name": f"smoke-agent-{suffix}",
                "model_endpoint_id": model_id,
                "skills": ["data-analysis"] if expect_approval else [],
            },
        )
        agent_id = agent["id"]
        session = client.request(
            "/api/v1/sessions",
            method="POST",
            payload={"title": f"smoke-session-{suffix}", "agent_id": agent_id},
        )
        session_id = session["id"]
        accepted = client.request(
            f"/api/v1/sessions/{session_id}/runs",
            method="POST",
            payload={"message": "请回复安装冒烟测试"},
        )
        if not accepted["events_url"].endswith(f"/runs/{accepted['run_id']}/events"):
            raise RuntimeError("run response has an invalid events_url")
        completed = client.wait_for(accepted["run_id"], {"completed", "failed"})
        if completed["status"] != "completed" or "Mock 模型回答" not in completed["output"]:
            raise RuntimeError(f"mock run failed: {completed}")

        events = client.request(f"/api/v1/runs/{accepted['run_id']}/event-log")
        event_types = {item["type"] for item in events}
        if not {"model_delta", "completed"}.issubset(event_types):
            raise RuntimeError(f"mock run emitted incomplete events: {sorted(event_types)}")
        replay = client.request(
            f"/api/v1/runs/{accepted['run_id']}/events?after={events[0]['id']}",
            expect_json=False,
        )
        if "event: completed" not in replay:
            raise RuntimeError("SSE replay did not include the terminal event")

        if expect_approval:
            approval_run = client.request(
                f"/api/v1/sessions/{session_id}/runs",
                method="POST",
                payload={
                    "message": '[[tool:skill.data-analysis.profile_csv {"input":"missing.csv"}]]'
                },
            )
            waiting = client.wait_for(approval_run["run_id"], {"waiting_approval", "failed"})
            if waiting["status"] != "waiting_approval":
                raise RuntimeError(f"execute-risk tool did not request approval: {waiting}")
            approvals = client.request(f"/api/v1/runs/{approval_run['run_id']}/approvals")
            pending = next(item for item in approvals if item["status"] == "pending")
            client.request(
                f"/api/v1/runs/{approval_run['run_id']}/approvals/{pending['id']}",
                method="POST",
                payload={"decision": "reject", "reason": "installation smoke test"},
            )
            resumed = client.wait_for(approval_run["run_id"], {"completed", "failed"})
            if resumed["status"] != "completed":
                raise RuntimeError(f"rejected approval did not return control to the model: {resumed}")
    finally:
        if session_id:
            client.request(f"/api/v1/sessions/{session_id}", method="DELETE")
        if agent_id:
            client.request(f"/api/v1/agents/{agent_id}", method="DELETE")
        if model_id:
            client.request(f"/api/v1/models/{model_id}", method="DELETE")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--expect-approval", action="store_true")
    args = parser.parse_args()
    client = ApiClient(args.base_url)
    check_contract(client)
    run_mock_flow(client, args.expect_approval)
    print("Hi-agent API smoke OK: static UI, REST, mock Run, SSE replay, persistence")
    if args.expect_approval:
        print(
            "Hi-agent MCP/approval smoke OK: stdio discovery/call policy, execute-risk "
            "interruption, rejection, checkpoint resume"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
