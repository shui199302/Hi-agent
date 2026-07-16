from __future__ import annotations

import sqlite3
import time
from typing import Any

from fastapi.testclient import TestClient

from hi_agent.config import Settings
from hi_agent.database import session_factory
from hi_agent.main import create_app
from hi_agent.models import RunCheckpoint


def wait_for_status(client: TestClient, run_id: str, expected: set[str], timeout: float = 3) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        run = response.json()
        if run["status"] in expected:
            return run
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not reach {expected}")


def create_mock_agent(client: TestClient, *, knowledge_base_id: str | None = None) -> str:
    model = client.post(
        "/api/v1/models",
        json={
            "name": f"mock-{time.monotonic_ns()}",
            "base_url": "http://mock.local/v1",
            "model": "mock-model",
            "mock": True,
        },
    )
    assert model.status_code == 201, model.text
    agent = client.post(
        "/api/v1/agents",
        json={
            "name": f"agent-{time.monotonic_ns()}",
            "model_endpoint_id": model.json()["id"],
            "knowledge_base_id": knowledge_base_id,
            "skills": ["task-planning"],
        },
    )
    assert agent.status_code == 201, agent.text
    return agent.json()["id"]


def test_health_crud_rag_run_and_resumable_events(client: TestClient) -> None:
    assert client.get("/api/v1/health").json()["status"] == "ok"
    kb_response = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "城市资料", "chunk_size": 100, "chunk_overlap": 20, "top_k": 3},
    )
    assert kb_response.status_code == 201, kb_response.text
    kb_id = kb_response.json()["id"]
    upload = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        files={"file": ("guide.md", "上海是中国的重要城市。外滩位于黄浦江畔。".encode(), "text/markdown")},
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["status"] == "ready"
    assert upload.json()["chunk_count"] == 1
    kb_with_counts = client.get(f"/api/v1/knowledge-bases/{kb_id}")
    assert kb_with_counts.json()["document_count"] == 1
    assert kb_with_counts.json()["chunk_count"] == 1
    listed_kb = client.get("/api/v1/knowledge-bases").json()
    assert next(item for item in listed_kb if item["id"] == kb_id)["document_count"] == 1

    duplicate = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/documents",
        files={"file": ("copy.md", "上海是中国的重要城市。外滩位于黄浦江畔。".encode(), "text/markdown")},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DOCUMENT_DUPLICATE"

    search = client.post(f"/api/v1/knowledge-bases/{kb_id}/search", json={"query": "上海外滩"})
    assert search.status_code == 200, search.text
    assert search.json()["items"][0]["filename"] == "guide.md"
    assert "dense" in search.json()["items"][0]["channels"]
    assert "lexical" in search.json()["items"][0]["channels"]

    edited = client.patch(
        f"/api/v1/knowledge-bases/{kb_id}",
        json={"name": "城市资料库", "description": "城市文档与旅行资料"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "城市资料库"
    assert edited.json()["description"] == "城市文档与旅行资料"
    assert edited.json()["status"] == "ready"
    assert edited.json()["ready_document_count"] == 1
    assert edited.json()["total_size_bytes"] > 0

    exact_query = client.get("/api/v1/knowledge-bases/query", params={"name_exact": "城市资料库"})
    assert exact_query.status_code == 200, exact_query.text
    assert exact_query.json()["total"] == 1
    assert exact_query.json()["items"][0]["id"] == kb_id
    assert client.get(
        "/api/v1/knowledge-bases/query", params={"name_exact": "城市资料", "status": "ready"}
    ).json()["total"] == 0

    document_query = client.get(
        f"/api/v1/knowledge-bases/{kb_id}/documents/query",
        params={"filename_exact": "guide.md", "limit": 1},
    )
    assert document_query.status_code == 200, document_query.text
    assert document_query.json()["total"] == 1
    assert document_query.json()["items"][0]["filename"] == "guide.md"

    rebuilt = client.post(
        f"/api/v1/knowledge-bases/{kb_id}/reindex",
        json={"embedding_model": "test-embedding", "chunk_size": 120, "chunk_overlap": 20, "top_k": 4},
    )
    assert rebuilt.status_code == 200, rebuilt.text
    assert rebuilt.json()["chunk_size"] == 120
    assert rebuilt.json()["top_k"] == 4

    agent_id = create_mock_agent(client, knowledge_base_id=kb_id)
    revisions = client.get(f"/api/v1/agents/{agent_id}/revisions")
    assert revisions.status_code == 200
    assert revisions.json()[0]["version"] == 1
    chat = client.post("/api/v1/sessions", json={"title": "旅行", "agent_id": agent_id})
    assert chat.status_code == 201
    run_response = client.post(f"/api/v1/sessions/{chat.json()['id']}/runs", json={"message": "介绍上海外滩"})
    assert run_response.status_code == 202, run_response.text
    accepted = run_response.json()
    assert accepted["events_url"].endswith(f"/runs/{accepted['run_id']}/events")
    run = wait_for_status(client, accepted["run_id"], {"completed", "failed"})
    assert run["status"] == "completed", run
    assert "Mock 模型回答" in run["output"]
    checkpoint_path = client.app.state.settings.checkpoints_path
    assert checkpoint_path.is_file()
    with sqlite3.connect(checkpoint_path) as connection:
        checkpoint_count = connection.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?",
            (accepted["run_id"],),
        ).fetchone()[0]
    assert checkpoint_count > 0

    log = client.get(f"/api/v1/runs/{accepted['run_id']}/event-log").json()
    types = [item["type"] for item in log]
    assert {"retrieval", "model_delta", "citation", "completed"}.issubset(types)
    first_id = log[0]["id"]
    replay = client.get(f"/api/v1/runs/{accepted['run_id']}/events?after={first_id}")
    assert replay.status_code == 200
    assert replay.headers["content-type"].startswith("text/event-stream")
    assert f"id: {first_id}" not in replay.text.splitlines()
    assert "event: completed" in replay.text
    assert '"run_id"' in replay.text

    summary = client.get("/api/v1/observability/summary")
    assert summary.status_code == 200
    assert summary.json()["total_runs"] >= 1


def test_create_skill_requires_confirmation_and_stays_in_skill_root(client: TestClient) -> None:
    payload = {
        "name": "customer-support",
        "description": "Handle repeatable customer support triage and evidence-backed response drafting.",
        "instructions": "# Workflow\n\n1. Classify the request.\n2. Draft and verify the response.",
        "display_name": "客户支持",
        "short_description": "分类并处理客户支持请求",
        "default_prompt": "处理这个客户支持请求。",
        "confirm": False,
    }
    rejected = client.post("/api/v1/skills", json=payload)
    assert rejected.status_code == 409
    payload["confirm"] = True
    created = client.post("/api/v1/skills", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "customer-support"
    assert (client.app.state.settings.skills_dir / "customer-support" / "SKILL.md").is_file()


def test_session_allows_only_one_active_run_and_approval_resume(
    client: TestClient,
) -> None:
    agent_id = create_mock_agent(client)
    session_id = client.post("/api/v1/sessions", json={"title": "审批", "agent_id": agent_id}).json()["id"]
    manager = client.app.state.run_manager

    async def fake_discover(_: str, __: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "name": "mcp.fake.write_note",
                "description": "测试写操作",
                "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
                "risk": "write",
                "kind": "fake",
            }
        ]

    async def fake_execute(
        _: str, __: dict[str, Any], arguments: dict[str, Any], ___: dict[str, Any]
    ) -> dict[str, Any]:
        return {"written": arguments["text"]}

    manager._discover_tools = fake_discover
    manager._execute_tool = fake_execute
    created = client.post(
        f"/api/v1/sessions/{session_id}/runs",
        json={"message": '[[tool:mcp.fake.write_note {"text":"ok"}]]'},
    )
    assert created.status_code == 202
    run_id = created.json()["run_id"]
    waiting = wait_for_status(client, run_id, {"waiting_approval", "failed"})
    assert waiting["status"] == "waiting_approval", waiting
    filtered_runs = client.get(f"/api/v1/runs?session_id={session_id}")
    assert filtered_runs.status_code == 200
    assert any(item["id"] == run_id and item["status"] == "waiting_approval" for item in filtered_runs.json())

    conflict = client.post(f"/api/v1/sessions/{session_id}/runs", json={"message": "不能并发"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "SESSION_RUN_CONFLICT"

    approvals = client.get(f"/api/v1/runs/{run_id}/approvals").json()
    assert len(approvals) == 1
    decision = client.post(
        f"/api/v1/runs/{run_id}/approvals/{approvals[0]['id']}",
        json={"decision": "approve", "reason": "测试批准"},
    )
    assert decision.status_code == 200, decision.text
    refreshed_approvals = client.get(f"/api/v1/runs/{run_id}/approvals")
    assert refreshed_approvals.status_code == 200
    assert refreshed_approvals.json()[0]["status"] == "approved"
    final = wait_for_status(client, run_id, {"completed", "failed"})
    assert final["status"] == "completed", final
    assert "written" in final["output"]

    retryable = client.post(
        f"/api/v1/sessions/{session_id}/runs",
        json={"message": '[[tool:mcp.fake.write_note {"text":"retry"}]]'},
    )
    retryable_id = retryable.json()["run_id"]
    waiting_again = wait_for_status(client, retryable_id, {"waiting_approval", "failed"})
    assert waiting_again["status"] == "waiting_approval"
    pending = client.get(f"/api/v1/runs/{retryable_id}/approvals").json()[0]
    with session_factory()() as db:
        checkpoint = db.get(RunCheckpoint, retryable_id)
        assert checkpoint is not None
        db.delete(checkpoint)
        db.commit()
    failed_resume = client.post(
        f"/api/v1/runs/{retryable_id}/approvals/{pending['id']}",
        json={"decision": "approve"},
    )
    assert failed_resume.status_code == 409
    assert failed_resume.json()["error"]["code"] == "CHECKPOINT_NOT_FOUND"
    still_pending = client.get(f"/api/v1/runs/{retryable_id}/approvals").json()[0]
    assert still_pending["status"] == "pending"
    assert client.get(f"/api/v1/runs/{retryable_id}").json()["status"] == "waiting_approval"


def test_validation_and_not_found_are_structured(client: TestClient) -> None:
    invalid = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "bad", "chunk_size": 100, "chunk_overlap": 100},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    missing = client.get("/api/v1/documents/not-a-real-id")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"


def test_spa_fallback_never_swallows_unknown_api(settings: Settings) -> None:
    settings.web_dist_dir.mkdir(parents=True)
    (settings.web_dist_dir / "index.html").write_text("<!doctype html><title>Hi-agent SPA</title>", encoding="utf-8")
    app = create_app(settings)
    with TestClient(app) as standalone:
        assert "Hi-agent SPA" in standalone.get("/workspace").text
        unknown = standalone.get("/api/v1/does-not-exist")
        assert unknown.status_code == 404
        assert unknown.headers["content-type"].startswith("application/json")
        assert unknown.json()["error"]["code"] == "API_NOT_FOUND"
