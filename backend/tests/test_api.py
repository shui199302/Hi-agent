from __future__ import annotations

import sqlite3
import time
from io import BytesIO
from typing import Any

from fastapi.testclient import TestClient
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from hi_agent.config import Settings
from hi_agent.database import session_factory
from hi_agent.main import create_app
from hi_agent.models import RunCheckpoint
from hi_agent.ocr import OcrPage


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


def test_common_mcp_presets_are_seeded_disabled_and_protected(client: TestClient) -> None:
    response = client.get("/api/v1/mcp/servers")
    assert response.status_code == 200, response.text
    servers = {item["name"]: item for item in response.json()}
    expected = {
        "filesystem",
        "git",
        "fetch",
        "time",
        "memory",
        "sequential-thinking",
        "github-readonly",
    }
    assert expected <= servers.keys()
    assert all(servers[name]["builtin"] for name in expected)
    assert all(not servers[name]["enabled"] for name in expected)
    assert all(servers[name]["description"] and servers[name]["source_url"] for name in expected)
    assert "@2026.7.4" in servers["filesystem"]["args"][1]
    assert servers["github-readonly"]["env_refs"] == {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_TOKEN"
    }

    preset_id = servers["filesystem"]["id"]
    renamed = client.patch(f"/api/v1/mcp/servers/{preset_id}", json={"name": "renamed"})
    assert renamed.status_code == 409
    assert renamed.json()["error"]["code"] == "MCP_PRESET_BUILTIN"
    removed = client.delete(f"/api/v1/mcp/servers/{preset_id}")
    assert removed.status_code == 409
    assert removed.json()["error"]["code"] == "MCP_PRESET_BUILTIN"

    enabled = client.patch(f"/api/v1/mcp/servers/{preset_id}", json={"enabled": True})
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True


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
    assert (
        client.get("/api/v1/knowledge-bases/query", params={"name_exact": "城市资料", "status": "ready"}).json()[
            "total"
        ]
        == 0
    )

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

    for report_format, content_type in (
        ("md", "text/markdown"),
        ("docx", "application/vnd.openxmlformats-officedocument"),
        ("pdf", "application/pdf"),
    ):
        report = client.post("/api/v1/rag/reports", json={"run_id": accepted["run_id"], "format": report_format})
        assert report.status_code == 200, report.text
        assert content_type in report.headers["content-type"]
        assert report.headers["content-disposition"].endswith(f'.{report_format}"')
        if report_format == "md":
            assert "RAG 问答报告" in report.text and "guide.md" in report.text
        elif report_format == "pdf":
            assert "RAG" in (PdfReader(BytesIO(report.content)).pages[0].extract_text() or "")
    summary = client.get("/api/v1/observability/summary")
    assert summary.status_code == 200
    assert summary.json()["total_runs"] >= 1
    trace = summary.json()["recent_runs"][0]
    assert trace["agent_name"] and trace["project_name"]
    assert trace["model_id"] == "mock-model"
    assert {"provider", "session_title", "citation_count", "input_chars", "output_chars"} <= trace.keys()


def test_project_owns_agents_and_knowledge_bases(client: TestClient) -> None:
    project = client.post("/api/v1/projects", json={"name": "客户交付", "description": "隔离交付资源"})
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    kb = client.post("/api/v1/knowledge-bases", json={"name": "交付资料", "project_id": project_id})
    assert kb.status_code == 201 and kb.json()["project_id"] == project_id
    model = client.post(
        "/api/v1/models",
        json={"name": "project-mock", "base_url": "http://mock.local/v1", "model": "mock", "mock": True},
    )
    agent = client.post(
        "/api/v1/agents",
        json={
            "name": "交付助手",
            "project_id": project_id,
            "model_endpoint_id": model.json()["id"],
            "knowledge_base_id": kb.json()["id"],
        },
    )
    assert agent.status_code == 201, agent.text
    detail = client.get(f"/api/v1/projects/{project_id}").json()
    assert detail["agent_count"] == 1 and detail["knowledge_base_count"] == 1
    session = client.post("/api/v1/sessions", json={"agent_id": agent.json()["id"], "title": "项目历史"})
    accepted = client.post(f"/api/v1/sessions/{session.json()['id']}/runs", json={"message": "记录项目归属"})
    assert accepted.status_code == 202, accepted.text
    assert wait_for_status(client, accepted.json()["run_id"], {"completed", "failed"})["status"] == "completed"
    target = client.post("/api/v1/projects", json={"name": "迁移目标"}).json()
    moved = client.patch(
        f"/api/v1/agents/{agent.json()['id']}",
        json={"project_id": target["id"], "knowledge_base_id": None},
    )
    assert moved.status_code == 200, moved.text
    old_detail = client.get(f"/api/v1/projects/{project_id}").json()
    new_detail = client.get(f"/api/v1/projects/{target['id']}").json()
    assert (old_detail["session_count"], old_detail["run_count"]) == (1, 1)
    assert (new_detail["agent_count"], new_detail["session_count"], new_detail["run_count"]) == (1, 0, 0)
    archived = client.patch(f"/api/v1/projects/{project_id}", json={"status": "archived"})
    assert archived.status_code == 200
    blocked_run = client.post(f"/api/v1/sessions/{session.json()['id']}/runs", json={"message": "不应运行"})
    assert blocked_run.status_code == 409 and blocked_run.json()["error"]["code"] == "PROJECT_ARCHIVED"
    blocked = client.delete(f"/api/v1/projects/{project_id}")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "PROJECT_IN_USE"


def test_non_rag_run_cannot_be_exported_as_rag_report(client: TestClient) -> None:
    model = client.post(
        "/api/v1/models",
        json={"name": "plain-report-model", "base_url": "http://mock.local/v1", "model": "mock", "mock": True},
    ).json()
    agent = client.post(
        "/api/v1/agents",
        json={"name": "普通助手", "model_endpoint_id": model["id"]},
    ).json()
    session = client.post("/api/v1/sessions", json={"agent_id": agent["id"]}).json()
    accepted = client.post(f"/api/v1/sessions/{session['id']}/runs", json={"message": "普通问答"}).json()
    assert wait_for_status(client, accepted["run_id"], {"completed", "failed"})["status"] == "completed"
    report = client.post("/api/v1/rag/reports", json={"run_id": accepted["run_id"], "format": "md"})
    assert report.status_code == 409
    assert report.json()["error"]["code"] == "RAG_REPORT_NOT_RAG_RUN"


def test_project_bulk_assigns_multiple_agents(client: TestClient) -> None:
    source = client.post("/api/v1/projects", json={"name": "批量来源"}).json()
    target = client.post("/api/v1/projects", json={"name": "批量目标"}).json()
    agents = [
        client.post("/api/v1/agents", json={"name": f"批量助手{index}", "project_id": source["id"]}).json()
        for index in range(2)
    ]
    assigned = client.post(
        f"/api/v1/projects/{target['id']}/agents:assign",
        json={"agent_ids": [item["id"] for item in agents]},
    )
    assert assigned.status_code == 200, assigned.text
    assert {item["id"] for item in assigned.json()} == {item["id"] for item in agents}
    assert client.get(f"/api/v1/projects/{source['id']}").json()["agent_count"] == 0
    assert client.get(f"/api/v1/projects/{target['id']}").json()["agent_count"] == 2


def test_prompt_template_crud_and_builtin_protection(client: TestClient) -> None:
    builtin = client.get("/api/v1/prompt-templates").json()
    assert len(builtin) >= 5 and all(item["builtin"] for item in builtin[:5])
    protected = client.patch(f"/api/v1/prompt-templates/{builtin[0]['id']}", json={"name": "不能修改"})
    assert protected.status_code == 409
    created = client.post(
        "/api/v1/prompt-templates",
        json={
            "name": "客服回复模板",
            "description": "规范客服回复",
            "category": "writing",
            "content": "你是客服助手，请准确说明处理结果并给出下一步。",
            "variables": [],
            "tags": ["客服"],
        },
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    updated = client.patch(f"/api/v1/prompt-templates/{template_id}", json={"description": "更新后的说明"})
    assert updated.status_code == 200 and updated.json()["description"] == "更新后的说明"
    assert client.delete(f"/api/v1/prompt-templates/{template_id}").status_code == 204


def test_builtin_digital_human_agent_generates_closed_avatar_spec(client: TestClient) -> None:
    agents = client.get("/api/v1/agents").json()
    designer = next(item for item in agents if item["agent_type"] == "digital_human")
    assert designer["builtin"] is True
    assert client.patch(f"/api/v1/agents/{designer['id']}", json={"name": "不能修改"}).status_code == 409
    assert client.delete(f"/api/v1/agents/{designer['id']}").status_code == 409

    generated = client.post(
        "/api/v1/digital-humans/generate",
        json={"description": "一个自信的银色短发女生，蓝色眼睛，穿绿色卫衣，戴眼镜，叫小禾"},
    )
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["agent_id"] == designer["id"]
    assert body["spec"] == {
        **body["spec"],
        "name": "小禾",
        "presentation": "feminine",
        "hair_style": "short",
        "hair_color": "#B7BCC8",
        "eye_color": "#4F79A7",
        "outfit": "hoodie",
        "outfit_color": "#2E8B68",
        "accessory": "glasses",
        "expression": "confident",
    }
    repeated = client.post("/api/v1/digital-humans/generate", json={"description": body["description"]})
    assert repeated.json()["spec"] == body["spec"]


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


def test_authentication_csrf_and_user_resource_isolation(client: TestClient) -> None:
    original = client.post(
        "/api/v1/models",
        json={"name": "隔离模型", "base_url": "http://mock.local/v1", "model": "mock", "mock": True},
    )
    assert original.status_code == 201, original.text

    other = TestClient(client.app)
    assert other.get("/api/v1/models").status_code == 401
    issued = other.post("/api/v1/auth/phone/code", json={"phone": "13900000000", "purpose": "register"})
    registered = other.post(
        "/api/v1/auth/phone/register",
        json={"phone": "13900000000", "code": issued.json()["debug_code"], "username": "隔离用户"},
    )
    assert registered.status_code == 200, registered.text
    other.headers["X-CSRF-Token"] = registered.json()["csrf_token"]
    assert other.get("/api/v1/models").json() == []
    assert len(other.get("/api/v1/prompt-templates").json()) >= 5
    assert other.get(f"/api/v1/models/{original.json()['id']}").status_code == 404
    forbidden_secret = other.post(
        "/api/v1/models",
        json={"name": "越权密钥", "base_url": "http://mock.local/v1", "model": "other", "mock": True},
    )
    assert forbidden_secret.status_code == 403
    secret_prefix = f"HI_AGENT_USER_{registered.json()['user']['id'].replace('-', '').upper()}_"
    same_name = other.post(
        "/api/v1/models",
        json={
            "name": "隔离模型",
            "base_url": "http://mock.local/v1",
            "model": "other",
            "api_key_env": f"{secret_prefix}MODEL_KEY",
            "mock": True,
        },
    )
    assert same_name.status_code == 201, same_name.text
    assert [item["id"] for item in client.get("/api/v1/models").json()] == [original.json()["id"]]

    csrf_missing = TestClient(client.app)
    csrf_missing.cookies.update(other.cookies)
    rejected = csrf_missing.post(
        "/api/v1/models",
        json={"name": "无 CSRF", "base_url": "http://mock.local/v1", "model": "mock", "mock": True},
    )
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "CSRF_INVALID"
    other.close()
    csrf_missing.close()


def test_mock_wechat_registration_profile_and_login(client: TestClient) -> None:
    challenge = client.post("/api/v1/auth/wechat/challenges", json={"purpose": "register"}).json()
    authorized = client.post(
        f"/api/v1/auth/wechat/challenges/{challenge['challenge_id']}/mock-authorize",
        json={"ticket": challenge["ticket"], "nickname": "微信测试用户", "mock_account": "api-test"},
    )
    assert authorized.status_code == 200
    completed = client.post(
        f"/api/v1/auth/wechat/challenges/{challenge['challenge_id']}/complete",
        json={"ticket": challenge["ticket"]},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["user"]["wechat_nickname"] == "微信测试用户"
    client.headers["X-CSRF-Token"] = completed.json()["csrf_token"]
    assert client.post("/api/v1/auth/logout").status_code == 204

    login = client.post("/api/v1/auth/wechat/challenges", json={"purpose": "login"}).json()
    client.post(
        f"/api/v1/auth/wechat/challenges/{login['challenge_id']}/mock-authorize",
        json={"ticket": login["ticket"], "nickname": "微信测试用户", "mock_account": "api-test"},
    )
    result = client.post(
        f"/api/v1/auth/wechat/challenges/{login['challenge_id']}/complete",
        json={"ticket": login["ticket"]},
    )
    assert result.status_code == 200, result.text
    assert result.json()["user"]["wechat_nickname"] == "微信测试用户"


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


def test_artifact_report_presentation_and_download(client: TestClient) -> None:
    project_id = client.get("/api/v1/projects").json()[0]["id"]
    missing_image_endpoint = client.post(
        "/api/v1/artifacts/images",
        json={"project_id": project_id, "prompt": "原创绿色机器人"},
    )
    assert missing_image_endpoint.status_code == 409
    assert missing_image_endpoint.json()["error"]["code"] == "IMAGE_ENDPOINT_REQUIRED"
    report = client.post(
        "/api/v1/artifacts/reports",
        json={"project_id": project_id, "title": "验收报告", "content": "第一章\n测试通过", "format": "docx"},
    )
    assert report.status_code == 201, report.text
    downloaded = client.get(f"/api/v1/artifacts/{report.json()['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"PK")
    assert downloaded.headers["x-content-type-options"] == "nosniff"

    presentation = client.post(
        "/api/v1/artifacts/presentations",
        json={
            "project_id": project_id,
            "title": "季度总结",
            "slides": [{"title": "成果", "bullets": ["完成 RAG", "完成 OCR"]}],
        },
    )
    assert presentation.status_code == 201, presentation.text
    assert presentation.json()["kind"] == "presentation"
    agent_id = create_mock_agent(client)
    chat_session = client.post("/api/v1/sessions", json={"title": "报告运行", "agent_id": agent_id}).json()
    accepted = client.post(f"/api/v1/sessions/{chat_session['id']}/runs", json={"message": "生成运行报告测试"}).json()
    wait_for_status(client, accepted["run_id"], {"completed"})
    run_report = client.post(
        "/api/v1/artifacts/run-reports",
        json={"run_id": accepted["run_id"], "format": "pdf"},
    )
    assert run_report.status_code == 201, run_report.text
    assert run_report.json()["run_id"] == accepted["run_id"]
    assert client.get(f"/api/v1/artifacts/{run_report.json()['id']}/download").content.startswith(b"%PDF")
    assert len(client.get("/api/v1/artifacts").json()) == 3


def test_scanned_pdf_uses_paddleocr_page_fallback(client: TestClient) -> None:
    kb = client.post(
        "/api/v1/knowledge-bases",
        json={"name": "扫描文档", "ocr_mode": "auto", "ocr_language": "ch", "ocr_min_chars": 30},
    )
    assert kb.status_code == 201, kb.text
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.showPage()
    pdf.save()

    rag = client.app.state.rag_service
    rag.ocr.recognize_pdf_pages = lambda *_args, **_kwargs: [OcrPage(1, "百度飞桨 OCR 识别成功")]
    uploaded = client.post(
        f"/api/v1/knowledge-bases/{kb.json()['id']}/documents",
        files={"file": ("scan.pdf", buffer.getvalue(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["extraction_method"] == "ocr"
    assert uploaded.json()["ocr_pages"] == [1]
    assert uploaded.json()["ocr_engine"] == "PaddleOCR 3.x"
