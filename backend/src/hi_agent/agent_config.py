"""Canonical Agent configuration snapshots shared by revisions and runs."""

from __future__ import annotations

from typing import Any

from .models import AgentConfig


def revision_snapshot(agent: AgentConfig) -> dict[str, Any]:
    """Return the complete mutable configuration stored by Agent revisions."""

    return {
        "project_id": agent.project_id,
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "model_endpoint_id": agent.model_endpoint_id,
        "knowledge_base_id": agent.knowledge_base_id,
        "skills": list(agent.skills),
        "mcp_servers": list(agent.mcp_servers),
        "tool_policy": dict(agent.tool_policy),
        "max_tool_loops": agent.max_tool_loops,
        "review_policy": agent.review_policy,
        "review_model_endpoint_id": agent.review_model_endpoint_id,
        "review_max_rounds": agent.review_max_rounds,
        "agent_type": agent.agent_type,
        "builtin": agent.builtin,
        "enabled": agent.enabled,
    }


def runtime_agent_snapshot(agent: AgentConfig) -> dict[str, Any]:
    """Return the stable Agent subset embedded in every Run snapshot."""

    return {
        "id": agent.id,
        "project_id": agent.project_id,
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "skills": list(agent.skills),
        "tool_policy": dict(agent.tool_policy),
        "max_tool_loops": min(agent.max_tool_loops, 12),
        "review_policy": agent.review_policy,
        "review_max_rounds": min(max(agent.review_max_rounds, 0), 3),
        "agent_type": agent.agent_type,
        "builtin": agent.builtin,
    }
