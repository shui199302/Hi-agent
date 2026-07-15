from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hi_agent.config import Settings
from hi_agent.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    skills = tmp_path / "skills"
    skill = skills / "task-planning"
    skill.mkdir(parents=True)
    (skill / "references").mkdir()
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: task-planning\n"
        "description: 将复杂任务整理为可验证的步骤。\n"
        "---\n"
        "# 任务规划\n\n先澄清目标，再列出步骤和验收条件。\n",
        encoding="utf-8",
    )
    (skill / "references" / "acceptance.md").write_text(
        "每个步骤都需要一个可验证的验收条件。\n",
        encoding="utf-8",
    )
    data_skill = skills / "data-analysis"
    script_dir = data_skill / "scripts"
    script_dir.mkdir(parents=True)
    (data_skill / "SKILL.md").write_text(
        "---\n"
        "name: data-analysis\n"
        "description: 安全分析 CSV 或 TSV 文件。\n"
        "---\n"
        "# 数据分析\n",
        encoding="utf-8",
    )
    (script_dir / "profile_csv.py").write_text(
        "import argparse, csv, json\n"
        "p=argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--root'); "
        "p.add_argument('--max-rows'); a=p.parse_args()\n"
        "with open(a.input, encoding='utf-8') as f: rows=list(csv.DictReader(f))\n"
        "print(json.dumps({'file': a.input.rsplit('/', 1)[-1], 'rows_profiled': len(rows)}))\n",
        encoding="utf-8",
    )
    data = tmp_path / "data"
    return Settings(
        data_dir=data,
        database_url=f"sqlite:///{data / 'test.sqlite3'}",
        qdrant_path=data / "qdrant",
        web_dist_dir=tmp_path / "missing-web",
        skills_dir=skills,
        embedding_backend="deterministic",
        event_poll_seconds=0.01,
        sse_heartbeat_seconds=0.05,
        run_timeout_seconds=5,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
